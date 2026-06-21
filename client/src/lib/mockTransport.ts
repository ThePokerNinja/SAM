import type { PersonaId, SamPhase, Transport, TurnTiming } from "./transport";

const PERSONAS: PersonaId[] = ["samuel", "schedule", "design", "sales"];

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/**
 * Simulates the STT -> brain -> TTS turn loop with realistic per-stage timings so the
 * TierController + LatencyHUD are reviewable with no backend or keys. Most turns land inside
 * the <800ms budget; ~1 in 12 is a "slow turn" to exercise p95 + the latency guard.
 */
export class MockTransport implements Transport {
  private phaseHandlers = new Set<(p: SamPhase) => void>();
  private turnHandlers = new Set<(t: TurnTiming) => void>();
  private phase: SamPhase = "idle";
  private timers: ReturnType<typeof setTimeout>[] = [];
  private personaIdx = 0;
  private connected = false;

  async connect(): Promise<void> {
    this.connected = true;
    this.setPhase("idle");
  }

  disconnect(): void {
    this.connected = false;
    this.timers.forEach(clearTimeout);
    this.timers = [];
    this.setPhase("idle");
  }

  setTalking(start: boolean): void {
    if (!this.connected) return;
    if (start) {
      this.setPhase("listening");
      return;
    }
    // user released — run a simulated turn
    this.runTurn();
  }

  private runTurn(): void {
    const slow = Math.random() < 1 / 12;
    const turnDetectMs = rand(180, 320) * (slow ? 1.8 : 1);
    const sttMs = rand(40, 140);
    const brainTtftMs = rand(180, 420) * (slow ? 1.7 : 1);
    const ttsTtfbMs = rand(90, 190);
    const netMs = rand(25, 80);
    const v2vMs = turnDetectMs + sttMs + brainTtftMs + ttsTtfbMs + netMs;
    const persona = PERSONAS[this.personaIdx % PERSONAS.length];
    this.personaIdx++;

    this.setPhase("thinking");
    this.timers.push(
      setTimeout(() => {
        this.setPhase("speaking");
        for (const h of this.turnHandlers) {
          h({ turnDetectMs, sttMs, brainTtftMs, ttsTtfbMs, netMs, v2vMs, persona });
        }
        // speak for a beat, then return to idle
        this.timers.push(setTimeout(() => this.setPhase("idle"), rand(1200, 2600)));
      }, v2vMs),
    );
  }

  private setPhase(p: SamPhase): void {
    this.phase = p;
    for (const h of this.phaseHandlers) h(p);
  }

  onPhase(cb: (p: SamPhase) => void): () => void {
    this.phaseHandlers.add(cb);
    cb(this.phase);
    return () => this.phaseHandlers.delete(cb);
  }

  onTurn(cb: (t: TurnTiming) => void): () => void {
    this.turnHandlers.add(cb);
    return () => this.turnHandlers.delete(cb);
  }

  getPeerConnection(): RTCPeerConnection | null {
    return null;
  }
}
