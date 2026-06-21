import type { TierId, TierPreset } from "./types";

// Per-tier presets — the single source of truth (spec §1).
// brainModel ids are placeholders until Hermes confirms per-tier model routing (ADR-2).
export const PRESETS: Record<TierId, TierPreset> = {
  0: {
    id: 0,
    name: "Ultra",
    visual: "full",
    targetFps: 60,
    memoryTurns: 32,
    brainModel: "hermes-realtime", // speech-to-speech experiment slot — not MVP
    ttsModel: "eleven_flash_v2_5",
    ttsSettings: "high",
    videoSend: false,
  },
  1: {
    id: 1,
    name: "Studio",
    visual: "full",
    targetFps: 60,
    memoryTurns: 24,
    brainModel: "hermes-full",
    ttsModel: "eleven_flash_v2_5",
    ttsSettings: "high",
    videoSend: false,
  },
  2: {
    id: 2,
    name: "HD",
    visual: "simple",
    targetFps: 45,
    memoryTurns: 12,
    brainModel: "gpt-4o-mini",
    ttsModel: "eleven_flash_v2_5",
    ttsSettings: "default",
    videoSend: false,
  },
  3: {
    id: 3,
    name: "SD",
    visual: "static",
    targetFps: 30,
    memoryTurns: 6,
    brainModel: "gpt-4o-mini",
    ttsModel: "eleven_flash_v2_5",
    ttsSettings: "low_latency",
    videoSend: false,
  },
  4: {
    id: 4,
    name: "Lifeboat",
    visual: "none",
    targetFps: 0,
    memoryTurns: 4,
    brainModel: "gpt-4o-mini",
    ttsModel: "eleven_flash_v2_5",
    ttsSettings: "low_latency",
    videoSend: false,
  },
};

/** Tiers the auto-controller is allowed to select at MVP (Ultra is manual-only). */
export const ACTIVE_TIERS: TierId[] = [1, 2, 3, 4];
