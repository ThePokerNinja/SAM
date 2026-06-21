// Transport abstraction so the UI is identical whether driven by the MockTransport
// (Phase 4, no backend) or the real LiveKit pipeline (Phase 5).

export type SamPhase = "idle" | "listening" | "thinking" | "speaking";

export type PersonaId = "samuel" | "schedule" | "design" | "sales";

/** Per-turn latency breakdown — drives the LatencyHUD and the controller's latency guard. */
export interface TurnTiming {
  turnDetectMs: number;
  sttMs: number;
  brainTtftMs: number;
  ttsTtfbMs: number;
  netMs: number;
  /** voice-to-voice: user end-of-speech -> first agent audio. */
  v2vMs: number;
  persona: PersonaId;
}

export interface Transport {
  connect(): Promise<void>;
  disconnect(): void;
  /** Simulate / drive push-to-talk. start=true begins listening, start=false ends the turn. */
  setTalking(start: boolean): void;
  onPhase(cb: (phase: SamPhase) => void): () => void;
  onTurn(cb: (timing: TurnTiming) => void): () => void;
  /** The live RTCPeerConnection, when one exists (null for mock). */
  getPeerConnection(): RTCPeerConnection | null;
}
