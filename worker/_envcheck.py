import os
from pathlib import Path

vals = {}
p = Path(".env")
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        vals[k.strip()] = v.strip()

REQUIRED = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ELEVENLABS_API_KEY", "SAM_VOICE_ID"]
BRAIN = ["GROQ_API_KEY", "OPENAI_API_KEY"]
OPTIONAL = ["ELEVENLABS_MODEL", "GROQ_MODEL", "OPENAI_MODEL", "RM_API_BASE_URL"]

def status(k):
    v = vals.get(k, "")
    placeholder = v.startswith("wss://your-") or v.endswith("your-project.livekit.cloud")
    return "SET" if v and not placeholder else ("PLACEHOLDER" if placeholder else "missing")

print("required (needed to start console/dev):")
for k in REQUIRED:
    print(f"  {k:22} {status(k)}")
print("brain (need at least one):")
for k in BRAIN:
    print(f"  {k:22} {status(k)}")
print("optional:")
for k in OPTIONAL:
    print(f"  {k:22} {status(k)}")

missing = [k for k in REQUIRED if status(k) != "SET"]
has_brain = any(status(k) == "SET" for k in BRAIN)
print()
if missing:
    print("BLOCKERS:", ", ".join(missing))
if not has_brain:
    print("BLOCKER: no brain key (set GROQ_API_KEY or OPENAI_API_KEY)")
if not missing and has_brain:
    print("READY: all required keys present.")
