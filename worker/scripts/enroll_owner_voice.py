"""Enroll the owner's voiceprint for Samuel's Tier-T gate (Picovoice Eagle).

One-time setup. Produces a serialized Eagle profile and prints it base64-encoded so you
can paste it into the `SAM_OWNER_VOICEPRINT` secret on the sam-agent Render service (or
write it to a file and point `SAM_OWNER_VOICEPRINT_PATH` at it).

Usage:
    pip install pveagle
    # Convert any recording to the required format first:
    #   ffmpeg -i raw.(mp3|m4a|wav) -ar 16000 -ac 1 -sample_fmt s16 owner16k.wav
    python scripts/enroll_owner_voice.py --access-key <PICOVOICE_KEY> --wav owner16k.wav
    # optional: --out owner_voiceprint.bin  (writes raw profile bytes too)

Enrollment is text-independent, so the incoming 2-hour ElevenLabs pro recording is ideal
source material - just convert a clean chunk of it to 16 kHz mono.
"""

from __future__ import annotations

import argparse
import base64
import sys
import wave


_RATE = 16000


def _read_wav_int16(path: str) -> list[int]:
    with wave.open(path, "rb") as wf:
        if wf.getframerate() != _RATE or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            sys.exit(
                "WAV must be 16000 Hz, mono, 16-bit PCM. Convert with:\n"
                f"  ffmpeg -i <input> -ar {_RATE} -ac 1 -sample_fmt s16 {path}"
            )
        import array

        data = wf.readframes(wf.getnframes())
        return array.array("h", data).tolist()


def main() -> None:
    ap = argparse.ArgumentParser(description="Enroll owner voiceprint for Eagle.")
    ap.add_argument("--access-key", required=True, help="Picovoice AccessKey")
    ap.add_argument("--wav", required=True, help="16kHz mono 16-bit WAV of the owner speaking")
    ap.add_argument("--out", help="Optional path to also write raw profile bytes")
    args = ap.parse_args()

    try:
        import pveagle
    except ImportError:
        sys.exit("pveagle not installed. Run: pip install pveagle")

    pcm = _read_wav_int16(args.wav)
    profiler = pveagle.create_profiler(access_key=args.access_key)
    chunk = profiler.min_enroll_samples
    if len(pcm) < chunk:
        sys.exit(f"Recording too short: need >= {chunk} samples (~{chunk / _RATE:.1f}s of speech).")

    pct = 0.0
    i = 0
    while pct < 100.0 and i + chunk <= len(pcm):
        pct, feedback = profiler.enroll(pcm[i : i + chunk])
        i += chunk
        print(f"  enroll {pct:5.1f}%  ({getattr(feedback, 'name', feedback)})", file=sys.stderr)

    if pct < 100.0:
        sys.exit(
            f"Enrollment only reached {pct:.1f}%. Provide a longer/cleaner recording "
            "(more continuous speech, less silence/noise)."
        )

    profile = profiler.export()
    profiler.delete()
    raw = profile.to_bytes()

    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(raw)
        print(f"Wrote raw profile -> {args.out}", file=sys.stderr)

    b64 = base64.b64encode(raw).decode("ascii")
    print("\n# Set this on sam-agent (Render env) as SAM_OWNER_VOICEPRINT:\n", file=sys.stderr)
    print(b64)


if __name__ == "__main__":
    main()
