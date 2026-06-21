"""Worker configuration: env loading + per-tier model routing (ADR-2/ADR-7)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Per-tier brain model map. Mirrors the client presets; placeholders until Hermes
# confirms model selection. The worker applies memory depth + model per the tier the
# client reports over the data channel.
TIER_BRAIN_MODEL: dict[int, str] = {
    0: "hermes-realtime",
    1: "hermes-full",
    2: "gpt-4o-mini",
    3: "gpt-4o-mini",
    4: "gpt-4o-mini",
}

TIER_MEMORY_TURNS: dict[int, int] = {0: 32, 1: 24, 2: 12, 3: 6, 4: 4}


def model_for_tier(tier: int) -> str:
    return TIER_BRAIN_MODEL.get(tier, "gpt-4o-mini")


def memory_turns_for_tier(tier: int) -> int:
    return TIER_MEMORY_TURNS.get(tier, 12)


@dataclass
class Settings:
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    deepgram_api_key: str = ""
    # STT via LiveKit Inference (string model, billed through LiveKit Cloud).
    stt_model: str = "deepgram/nova-3"
    elevenlabs_api_key: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    # Brain for the POC: OpenAI gpt-4o-mini directly (ADR-2 allows converging on Hermes later).
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # Groq: OpenAI-compatible, ultra-low TTFT - candidate for the live/low tier brain.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"
    hermes_base_url: str = ""
    hermes_api_key: str = ""
    rm_api_base_url: str = "https://rainmaker-api-waqs.onrender.com"
    rm_api_token: str = ""
    token_server_port: int = 8788
    voice_ids: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            livekit_url=os.getenv("LIVEKIT_URL", ""),
            livekit_api_key=os.getenv("LIVEKIT_API_KEY", ""),
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", ""),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            stt_model=os.getenv("SAM_STT_MODEL", "deepgram/nova-3"),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_model=os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            hermes_base_url=os.getenv("HERMES_BASE_URL", ""),
            hermes_api_key=os.getenv("HERMES_API_KEY", ""),
            rm_api_base_url=os.getenv("RM_API_BASE_URL", "https://rainmaker-api-waqs.onrender.com"),
            rm_api_token=os.getenv("RM_API_TOKEN", ""),
            token_server_port=int(os.getenv("TOKEN_SERVER_PORT", "8788")),
            voice_ids={
                "samuel": os.getenv("SAM_VOICE_ID", ""),
                "schedule": os.getenv("SCHEDULE_VOICE_ID", ""),
                "design": os.getenv("DESIGN_VOICE_ID", ""),
                "sales": os.getenv("SALES_VOICE_ID", ""),
            },
        )
