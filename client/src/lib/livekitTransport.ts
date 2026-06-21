import type { SamPhase, Transport, TurnTiming } from "./transport";

/**
 * Real LiveKit transport — STUB for Phase 4.
 *
 * Phase 5 (Speed POC) wires this up:
 *  - fetch a LiveKit token from worker/server/token_server.py
 *  - connect via `livekit-client` Room.connect(VITE_LIVEKIT_URL, token)
 *  - publish the mic track; subscribe to Samuel's audio track
 *  - read RTCPeerConnection from the room engine for NetSampler
 *  - map LiveKit data-channel events (turn start/end, per-stage TTFB) to TurnTiming
 *
 * Until then this throws if selected, so mock mode is the only runnable path.
 */
export class LiveKitTransport implements Transport {
  async connect(): Promise<void> {
    throw new Error(
      "LiveKitTransport is a Phase 5 stub. Run with VITE_USE_MOCK=1 (the default).",
    );
  }
  disconnect(): void {}
  setTalking(_start: boolean): void {}
  onPhase(_cb: (p: SamPhase) => void): () => void {
    return () => {};
  }
  onTurn(_cb: (t: TurnTiming) => void): () => void {
    return () => {};
  }
  getPeerConnection(): RTCPeerConnection | null {
    return null;
  }
}
