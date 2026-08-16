"""Automated full-audio LiveKit benchmark driver (SAM-060/061/063).

The driver is an external participant: it publishes deterministic fixture audio
and measures Samuel's returned audio at the room boundary. This includes
transport, STT, endpointing, LLM, TTS, and playback delivery.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import wave
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from livekit import api, rtc


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
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
            await self.wait_event("audio_stopped", after=started, timeout_s=timeout_s)
        except TimeoutError:
            await asyncio.sleep(1.0)
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def close(self) -> None:
        for task in list(self._monitor_tasks):
            task.cancel()
        if self._monitor_tasks:
            await asyncio.gather(*self._monitor_tasks, return_exceptions=True)
        await self.room.disconnect()

    async def _monitor_audio(self, track: rtc.RemoteAudioTrack) -> None:
        stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=self.sample_rate,
            num_channels=1,
            frame_size_ms=20,
        )
        speaking = False
        silent_frames = 0
        async for event in stream:
            active = pcm_rms(event.frame.data) >= self.silence_rms
            now = time.perf_counter()
            if active:
                silent_frames = 0
                if not speaking:
                    speaking = True
                    await self.events.put(("audio_started", now))
            elif speaking:
                silent_frames += 1
                if silent_frames == 6:
                    await self.events.put(("audio_paused", now))
                if silent_frames >= 40:
                    speaking = False
                    silent_frames = 0
                    await self.events.put(("audio_stopped", now))

    async def publish_fixture(self, fixture: AudioFixture) -> tuple[float, float]:
        sample_rate, frames = read_pcm_frames(fixture.path)
        if sample_rate != self.sample_rate:
            raise ValueError(
                f"{fixture.path} sample rate {sample_rate} does not match {self.sample_rate}"
            )
        samples_per_frame = self.sample_rate * 20 // 1000
        started = time.perf_counter()
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
                last_voice_at = time.perf_counter()
            await asyncio.sleep(0.02)
        silence = b"\x00" * (samples_per_frame * 2)
        for _ in range(60):
            await self.source.capture_frame(
                rtc.AudioFrame(
                    data=silence,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    samples_per_channel=samples_per_frame,
                )
            )
            await asyncio.sleep(0.02)
        return started, last_voice_at

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

    async def measure_turn(
        self,
        fixture: AudioFixture,
        *,
        turn_mode: str,
        timeout_s: float = 15.0,
    ) -> AudioTurnResult:
        try:
            event_start = len(self.bench_events)
            speech_start, speech_end = await self.publish_fixture(fixture)
            deadline = time.perf_counter() + timeout_s
            audio_start: float | None = None
            while audio_start is None:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError("timed out waiting for audio_started")
                kind, timestamp = await asyncio.wait_for(self.events.get(), remaining)
                if kind == "audio_started" and timestamp >= speech_start:
                    audio_start = timestamp
            cut_off = audio_start < speech_end
            result = AudioTurnResult(
                fixture.id,
                fixture.kind,
                turn_mode,
                round(max(0.0, audio_start - speech_end) * 1000.0, 1),
                cut_off=cut_off,
            )
            try:
                await self.wait_event("audio_stopped", after=audio_start, timeout_s=30.0)
            except TimeoutError:
                pass
            turn_events = self.bench_events[event_start:]
            result.assistant_text = " ".join(
                str(event.get("text", ""))
                for event in turn_events
                if event.get("type") == "assistant_message"
            ).strip()
            result.tool_calls = tuple(
                str(name)
                for event in turn_events
                if event.get("type") == "tool_calls"
                for name in event.get("names", [])
            )
            return result
        except Exception as exc:  # noqa: BLE001 - each fixture is an independent sample
            return AudioTurnResult(
                fixture.id,
                fixture.kind,
                turn_mode,
                None,
                error=type(exc).__name__,
            )

    async def measure_barge_in(
        self,
        *,
        prompt: AudioFixture,
        interruption: AudioFixture,
        turn_mode: str,
    ) -> AudioTurnResult:
        try:
            _speech_start, speech_end = await self.publish_fixture(prompt)
            started = await self.wait_event("audio_started", after=speech_end, timeout_s=15.0)
            await asyncio.sleep(0.4)
            interrupt_start = time.perf_counter()
            await self.publish_fixture(interruption)
            stopped = await self.wait_event(
                "audio_paused", after=interrupt_start, timeout_s=4.0
            )
            return AudioTurnResult(
                interruption.id,
                "barge_in",
                turn_mode,
                round((started - speech_end) * 1000.0, 1),
                barge_in_ms=round((stopped - interrupt_start) * 1000.0, 1),
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
            _speech_start, speech_end = await self.publish_fixture(prompt)
            started = await self.wait_event("audio_started", after=speech_end, timeout_s=15.0)
            await asyncio.sleep(0.4)
            decoy_start = time.perf_counter()
            await self.publish_fixture(decoy)
            false_trigger = False
            try:
                stopped = await self.wait_event(
                    "audio_stopped",
                    after=decoy_start,
                    timeout_s=2.5,
                )
                false_trigger = stopped - decoy_start <= 2.5
            except TimeoutError:
                pass
            return AudioTurnResult(
                decoy.id,
                "decoy",
                turn_mode,
                round((started - speech_end) * 1000.0, 1),
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
