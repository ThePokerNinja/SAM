// TierController types — see studios/research/sam-tiercontroller-spec.md (Rainmaker repo).

export type TierId = 0 | 1 | 2 | 3 | 4;

export type VisualMode = "full" | "simple" | "static" | "none";
export type TtsSettings = "high" | "default" | "low_latency";

/** A tier is a snapshot preset of every adaptive knob. Data, not code. */
export interface TierPreset {
  id: TierId;
  name: string;
  visual: VisualMode;
  targetFps: number;
  memoryTurns: number;
  brainModel: string;
  ttsModel: string;
  ttsSettings: TtsSettings;
  videoSend: boolean;
}

/** Raw, smoothed signals the controller scores each tick. */
export interface TierSignals {
  fps: number; // EMA over the 1s window
  fpsMin1s: number; // worst frame in the last second
  bitrateBps: number | null; // WebRTC availableOutgoingBitrate
  rttMs: number | null;
  lossPct: number | null;
  effectiveType?: string; // navigator.connection coarse fallback
  v2vP95Ms: number | null; // rolling voice-to-voice p95 (latency guard)
  audioRisk: boolean; // underrun / TTS stall — hard floor
}

export type HardFloorSub = "audio" | "latency";

export type TierChangeReason =
  | "fps"
  | "net"
  | "latency"
  | "upgrade"
  | "manual"
  | `hardFloor:${HardFloorSub}`;

export type TierChangeHandler = (
  next: TierPreset,
  prev: TierPreset,
  reason: TierChangeReason,
) => void;

export interface TierControllerOptions {
  /** Tick cadence in ms (default 1000). */
  tickMs?: number;
  /** Consecutive ticks below desired before a voluntary downgrade (default 3). */
  downgradeTicks?: number;
  /** Consecutive ticks of headroom before an upgrade (default 8). */
  upgradeTicks?: number;
  /** Min ms between any voluntary tier changes (default 4000). */
  cooldownMs?: number;
  /** Min ms after a change before an upgrade specifically (default 10000). */
  upgradeCooldownMs?: number;
  /** Tier to start in before signals settle (default 2 = HD). */
  startTier?: TierId;
  /** Pluggable clock for tests. */
  now?: () => number;
}
