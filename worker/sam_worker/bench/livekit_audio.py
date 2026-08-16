"""Automated full-audio LiveKit benchmark driver (SAM-060/061/063).

The driver is an external participant: it publishes deterministic fixture audio
and measures Samuel's returned audio at the room boundary. This includes
transport, STT, endpointing, LLM, TTS, and playback delivery.
"""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import time
import wave
from array import array
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from livekit import api, rtc

# audio_paused fires once 6 of the last 8 remote frames (20ms) are silent.
# That detection lag is added to every barge-in sample and must be subtracted.
AUDIO_FRAME_MS = 20
AUDIO_PAUSE_WINDOW = 8
AUDIO_PAUSE_SILENT_COUNT = 6
# Six silent frames are required; the event timestamp is the 6th frame, so
# elapsed time from the first silent frame is five frame intervals.
AUDIO_PAUSED_LAG_S = (AUDIO_PAUSE_SILENT_COUNT - 1) * (AUDIO_FRAME_MS / 1000.0)


@dataclass(frozen=True)
class AudioFixture:
    id: str
    path: Path
    kind: str
    transcript: str


@dataclass
class AudioTurnResult:
    fixture_id: str
    kind: str
    turn_mode: str
    v2v_ms: float | None
    barge_in_ms: float | None = None
    cut_off: bool = False
    false_trigger: bool = False
    assistant_text: str = ""
    tool_calls: tuple[str, ...] = ()
    heard_audio: bool = False
    agent_event_types: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PublishTiming:
    """Wall-clock marks from one fixture publish."""

    publish_start: float
    first_voice_at: float
    last_voice_at: float


def compute_barge_in_ms(first_voice_at: float, paused_at: float) -> float:
    """Barge-in latency from first voiced interrupt frame to detected pause.

    Subtracts the rolling-silence monitor's known detection lag so the number
    reflects agent interruption, not the harness hysteresis.
    """
    raw_s = paused_at - first_voice_at
    return round(max(0.0, raw_s - AUDIO_PAUSED_LAG_S) * 1000.0, 1)


def load_manifest(path: Path | str) -> list[AudioFixture]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    return [
        AudioFixture(
            id=str(row["id"]),
            path=(source.parent / row["file"]).resolve(),
            kind=str(row["kind"]),
            transcript=str(row["transcript"]),
        )
        for row in payload["fixtures"]
    ]


def read_pcm_frames(path: Path, *, frame_ms: int = 20) -> tuple[int, list[bytes]]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1 or wav.getcomptype() != "NONE":
            raise ValueError(f"{path} must be mono 16-bit PCM WAV")
        sample_rate = wav.getframerate()
        samples_per_frame = sample_rate * frame_ms // 1000
        frames: list[bytes] = []
        while data := wav.readframes(samples_per_frame):
            expected = samples_per_frame * 2
            if len(data) < expected:
                data += b"\x00" * (expected - len(data))
            frames.append(data)
    return sample_rate, frames


def pcm_rms(data: bytes | memoryview) -> float:
    samples = array("h")
    samples.frombytes(bytes(data))
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def mint_token(api_key: str, api_secret: str, *, room: str, identity: str) -> str:
    grant = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grant)
        .to_jwt()
    )


class LiveKitAudioDriver:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        sample_rate: int = 16000,
        silence_rms: float = 180.0,
        participant_identity_prefix: str = "",
        debug_audio_path: Path | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.sample_rate = sample_rate
        self.silence_rms = silence_rms
        self.participant_identity_prefix = participant_identity_prefix
        self.room = rtc.Room()
        self.source = rtc.AudioSource(sample_rate, 1, queue_size_ms=100)
        self.track = rtc.LocalAudioTrack.create_audio_track("bench-fixture", self.source)
        self.events: asyncio.Queue[tuple[str, float]] = asyncio.Queue()
        self.bench_events: list[dict[str, Any]] = []
        self._monitor_tasks: set[asyncio.Task] = set()
        self.audio_track_ready = asyncio.Event()
        self._speaking = False
        self._paused = False
        self._silence_window: deque[bool] = deque(maxlen=40)
        self._debug_audio_path = debug_audio_path
        self._trace_rows: list[dict[str, Any]] = []
        self._turn_rms: list[float] = []
        self._turn_trace_id = 0

    async def connect(self) -> None:
        @self.room.on("track_subscribed")
        def _track_subscribed(track, _publication, participant) -> None:
            if track.kind != rtc.TrackKind.KIND_AUDIO:
                return
            if participant.identity == self.room.local_participant.identity:
                return
            if (
                self.participant_identity_prefix
                and not participant.identity.startswith(self.participant_identity_prefix)
            ):
                return
            task = asyncio.create_task(self._monitor_audio(track))
            self._monitor_tasks.add(task)
            task.add_done_callback(self._monitor_tasks.discard)
            self.audio_track_ready.set()

        @self.room.on("data_received")
        def _data_received(packet: rtc.DataPacket) -> None:
            if packet.topic != "sam-bench":
                return
            try:
                payload = json.loads(bytes(packet.data).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if isinstance(payload, dict):
                self.bench_events.append(
                    {"received_at": time.perf_counter(), **payload}
                )

        await self.room.connect(self.url, self.token)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_MICROPHONE
        await self.room.local_participant.publish_track(self.track, options)

    async def wait_ready(self, *, timeout_s: float = 30.0) -> None:
        await asyncio.wait_for(self.audio_track_ready.wait(), timeout_s)

    async def wait_initial_greeting(self, *, timeout_s: float = 20.0) -> None:
        """Let the auto-dispatched agent finish its greeting before fixture one."""
        try:
            started = await self.wait_event("audio_started", after=0.0, timeout_s=timeout_s)
            stopped = await self.wait_event("audio_stopped", after=started, timeout_s=timeout_s)
            await self.wait_audio_quiet(after=stopped, quiet_s=3.0, timeout_s=timeout_s)
        except TimeoutError:
            await asyncio.sleep(1.0)
        self.reset_turn_state()

    def reset_turn_state(self) -> None:
        """Re-arm audio detection and discard events from the preceding turn."""
        if self._turn_rms:
            ordered = sorted(self._turn_rms)
            p95_index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
            self._trace(
                "rms_summary",
                frame_count=len(ordered),
                minimum=round(ordered[0], 3),
                median=round(statistics.median(ordered), 3),
                p95=round(ordered[p95_index], 3),
                maximum=round(ordered[-1], 3),
            )
        self._turn_trace_id += 1
        self._turn_rms = []
        self._speaking = False
        self._paused = False
        self._silence_window.clear()
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._trace("state_reset")

    def _trace(self, event: str, **details: Any) -> None:
        if self._debug_audio_path is None:
            return
        self._trace_rows.append(
            {
                "at": time.time(),
                "event": event,
                "turn_id": self._turn_trace_id,
                **details,
            }
        )

    def _flush_trace(self) -> None:
        if self._debug_audio_path is None or not self._trace_rows:
            return
        self._debug_audio_path.parent.mkdir(parents=True, exist_ok=True)
        with self._debug_audio_path.open("a", encoding="utf-8") as stream:
            for row in self._trace_rows:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        self._trace_rows.clear()

    async def close(self) -> None:
        self.reset_turn_state()
        for task in list(self._monitor_tasks):
            task.cancel()
        if self._monitor_tasks:
            await asyncio.gather(*self._monitor_tasks, return_exceptions=True)
        await self.room.disconnect()
        self._flush_trace()

    async def _monitor_audio(self, track: rtc.RemoteAudioTrack) -> None:
        for attempt in range(2):
            try:
                stream = rtc.AudioStream.from_track(
                    track=track,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    frame_size_ms=20,
                )
                self._trace("monitor_started", attempt=attempt + 1)
                async for event in stream:
                    rms = pcm_rms(event.frame.data)
                    self._turn_rms.append(rms)
                    self._trace("rms", value=round(rms, 3))
                    await self._process_audio_level(rms >= self.silence_rms, time.perf_counter())
                self._trace("monitor_ended", attempt=attempt + 1)
            except asyncio.CancelledError:
                self._trace("monitor_cancelled", attempt=attempt + 1)
                raise
            except Exception as exc:  # noqa: BLE001 - preserve benchmark diagnostics
                self._trace(
                    "monitor_error",
                    attempt=attempt + 1,
                    error=type(exc).__name__,
                    message=str(exc)[:200],
                )
            if attempt == 0:
                await asyncio.sleep(0.1)
        self.audio_track_ready.clear()
        self._trace("monitor_stopped")

    async def _process_audio_level(self, active: bool, now: float) -> None:
        """Advance the rolling audio state machine for one remote frame."""
        if not self._speaking:
            if active:
                self._speaking = True
                self._paused = False
                self._silence_window.clear()
                await self.events.put(("audio_started", now))
                self._trace("audio_started", monotonic_at=now)
            return

        self._silence_window.append(not active)
        recent = tuple(self._silence_window)
        if (
            not self._paused
            and len(recent) >= AUDIO_PAUSE_WINDOW
            and sum(recent[-AUDIO_PAUSE_WINDOW:]) >= AUDIO_PAUSE_SILENT_COUNT
        ):
            self._paused = True
            await self.events.put(("audio_paused", now))
            self._trace("audio_paused", monotonic_at=now)
        elif self._paused and len(recent) >= 4 and sum(recent[-4:]) <= 1:
            self._paused = False
            self._trace("audio_resumed", monotonic_at=now)

        if len(recent) == self._silence_window.maxlen and sum(recent) >= 36:
            self._speaking = False
            self._paused = False
            self._silence_window.clear()
            await self.events.put(("audio_stopped", now))
            self._trace("audio_stopped", monotonic_at=now)

    async def publish_fixture(
        self,
        fixture: AudioFixture,
        *,
        reset: bool = True,
    ) -> PublishTiming:
        if reset:
            self.reset_turn_state()
        sample_rate, frames = read_pcm_frames(fixture.path)
        if sample_rate != self.sample_rate:
            raise ValueError(
                f"{fixture.path} sample rate {sample_rate} does not match {self.sample_rate}"
            )
        samples_per_frame = self.sample_rate * AUDIO_FRAME_MS // 1000
        started = time.perf_counter()
        first_voice_at: float | None = None
        last_voice_at = started
        for data in frames:
            await self.source.capture_frame(
                rtc.AudioFrame(
                    data=data,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    samples_per_channel=samples_per_frame,
                )
            )
            if pcm_rms(data) >= self.silence_rms:
                now = time.perf_counter()
                if first_voice_at is None:
                    first_voice_at = now
                last_voice_at = now
            await asyncio.sleep(AUDIO_FRAME_MS / 1000.0)
        silence = b"\x00" * (samples_per_frame * 2)
        # Keep sending real silence long enough for STT endpointing to finalize;
        # stopping frame delivery at 1.2s can leave Deepgram's transcript open.
        for _ in range(200):
            await self.source.capture_frame(
                rtc.AudioFrame(
                    data=silence,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    samples_per_channel=samples_per_frame,
                )
            )
            await asyncio.sleep(AUDIO_FRAME_MS / 1000.0)
        return PublishTiming(started, first_voice_at or started, last_voice_at)

    async def wait_event(
        self,
        kind: str,
        *,
        after: float,
        timeout_s: float,
    ) -> float:
        deadline = time.perf_counter() + timeout_s
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {kind}")
            event_kind, timestamp = await asyncio.wait_for(self.events.get(), remaining)
            if event_kind == kind and timestamp >= after:
                return timestamp

    async def wait_audio_quiet(
        self,
        *,
        after: float,
        quiet_s: float,
        timeout_s: float,
    ) -> None:
        """Wait until remote audio has not restarted for ``quiet_s`` seconds."""
        overall_deadline = time.perf_counter() + timeout_s
        last_stop = after
        while True:
            remaining = overall_deadline - time.perf_counter()
            if remaining <= 0:
                return
            try:
                restarted = await self.wait_event(
                    "audio_started",
                    after=last_stop,
                    timeout_s=min(quiet_s, remaining),
                )
            except TimeoutError:
                return
            try:
                last_stop = await self.wait_event(
                    "audio_stopped",
                    after=restarted,
                    timeout_s=max(0.1, overall_deadline - time.perf_counter()),
                )
            except TimeoutError:
                return

    async def measure_turn(
        self,
        fixture: AudioFixture,
        *,
        turn_mode: str,
        timeout_s: float = 15.0,
    ) -> AudioTurnResult:
        event_start = len(self.bench_events)
        result = AudioTurnResult(fixture.id, fixture.kind, turn_mode, None)
        try:
            published = await self.publish_fixture(fixture)
            deadline = time.perf_counter() + timeout_s
            audio_start: float | None = None
            while audio_start is None:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for audio_started")
                kind, timestamp = await asyncio.wait_for(self.events.get(), remaining)
                if kind == "audio_started" and timestamp >= published.publish_start:
                    audio_start = timestamp
            cut_off = audio_start < published.last_voice_at
            result.v2v_ms = round(max(0.0, audio_start - published.last_voice_at) * 1000.0, 1)
            result.cut_off = cut_off
            result.heard_audio = True
            try:
                stopped = await self.wait_event(
                    "audio_stopped", after=audio_start, timeout_s=30.0
                )
                await self.wait_audio_quiet(after=stopped, quiet_s=8.0, timeout_s=30.0)
            except TimeoutError:
                pass
            await asyncio.sleep(0.5)
        except Exception as exc:  # noqa: BLE001 - each fixture is an independent sample
            result.error = type(exc).__name__
        finally:
            turn_events = self.bench_events[event_start:]
            messages: list[str] = []
            for event in turn_events:
                if event.get("type") != "assistant_message":
                    continue
                text = str(event.get("text", "")).strip()
                if text and (not messages or text != messages[-1]):
                    messages.append(text)
            result.assistant_text = " ".join(messages)
            result.tool_calls = tuple(
                str(name)
                for event in turn_events
                if event.get("type") == "tool_calls"
                for name in event.get("names", [])
            )
            result.agent_event_types = tuple(
                dict.fromkeys(
                    str(event.get("type", ""))
                    for event in turn_events
                    if event.get("type")
                )
            )
        return result

    async def measure_barge_in(
        self,
        *,
        prompt: AudioFixture,
        interruption: AudioFixture,
        turn_mode: str,
    ) -> AudioTurnResult:
        try:
            prompt_timing = await self.publish_fixture(prompt)
            started = await self.wait_event(
                "audio_started", after=prompt_timing.last_voice_at, timeout_s=15.0
            )
            await asyncio.sleep(0.4)
            interrupt_timing = await self.publish_fixture(interruption, reset=False)
            stopped = await self.wait_event(
                "audio_paused", after=interrupt_timing.first_voice_at, timeout_s=4.0
            )
            return AudioTurnResult(
                interruption.id,
                "barge_in",
                turn_mode,
                round((started - prompt_timing.last_voice_at) * 1000.0, 1),
                barge_in_ms=compute_barge_in_ms(interrupt_timing.first_voice_at, stopped),
            )
        except Exception as exc:  # noqa: BLE001
            return AudioTurnResult(
                interruption.id,
                "barge_in",
                turn_mode,
                None,
                error=type(exc).__name__,
            )

    async def measure_decoy(
        self,
        *,
        prompt: AudioFixture,
        decoy: AudioFixture,
        turn_mode: str,
    ) -> AudioTurnResult:
        """Return whether a short backchannel incorrectly stopped a long response."""
        try:
            prompt_timing = await self.publish_fixture(prompt)
            started = await self.wait_event(
                "audio_started", after=prompt_timing.last_voice_at, timeout_s=15.0
            )
            await asyncio.sleep(0.4)
            decoy_timing = await self.publish_fixture(decoy, reset=False)
            false_trigger = False
            try:
                stopped = await self.wait_event(
                    "audio_stopped",
                    after=decoy_timing.first_voice_at,
                    timeout_s=2.5,
                )
                false_trigger = stopped - decoy_timing.first_voice_at <= 2.5
            except TimeoutError:
                pass
            return AudioTurnResult(
                decoy.id,
                "decoy",
                turn_mode,
                round((started - prompt_timing.last_voice_at) * 1000.0, 1),
                false_trigger=false_trigger,
            )
        except Exception as exc:  # noqa: BLE001
            return AudioTurnResult(
                decoy.id,
                "decoy",
                turn_mode,
                None,
                error=type(exc).__name__,
            )
