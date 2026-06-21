// Signal samplers: FPS (requestAnimationFrame) and network (WebRTC getStats / navigator).
// These feed TierSignals to the controller. Pure browser APIs; safe no-ops under SSR/tests.

export class FpsSampler {
  private ema = 60;
  private frames = 0;
  private windowStart = 0;
  private worst = 60;
  private lastWorst = 60;
  private rafId: number | null = null;
  private running = false;
  private last = 0;

  start(): void {
    if (this.running || typeof requestAnimationFrame === "undefined") return;
    this.running = true;
    this.windowStart = performance.now();
    this.last = this.windowStart;
    const tick = (t: number) => {
      if (!this.running) return;
      const dt = t - this.last;
      this.last = t;
      if (dt > 0) {
        const instant = 1000 / dt;
        this.worst = Math.min(this.worst, instant);
      }
      this.frames++;
      if (t - this.windowStart >= 1000) {
        const windowFps = (this.frames * 1000) / (t - this.windowStart);
        this.ema = this.ema * 0.7 + windowFps * 0.3;
        this.lastWorst = this.worst;
        this.frames = 0;
        this.worst = 120;
        this.windowStart = t;
      }
      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);
  }

  stop(): void {
    this.running = false;
    if (this.rafId != null && typeof cancelAnimationFrame !== "undefined") {
      cancelAnimationFrame(this.rafId);
    }
    this.rafId = null;
  }

  get fps(): number {
    return this.ema;
  }

  get fpsMin1s(): number {
    return this.lastWorst;
  }
}

interface NetStats {
  bitrateBps: number | null;
  rttMs: number | null;
  lossPct: number | null;
  effectiveType?: string;
}

/**
 * Reads outgoing bitrate / RTT / loss from a live RTCPeerConnection when present,
 * else falls back to navigator.connection. Call refresh() on the controller tick.
 */
export class NetSampler {
  private pc: RTCPeerConnection | null = null;
  private latest: NetStats = { bitrateBps: null, rttMs: null, lossPct: null };
  private prevPacketsSent = 0;
  private prevPacketsLost = 0;

  attach(pc: RTCPeerConnection | null): void {
    this.pc = pc;
  }

  async refresh(): Promise<NetStats> {
    const conn = (navigator as Navigator & { connection?: { effectiveType?: string } })
      .connection;
    const effectiveType = conn?.effectiveType;

    if (!this.pc || typeof this.pc.getStats !== "function") {
      this.latest = { bitrateBps: null, rttMs: null, lossPct: null, effectiveType };
      return this.latest;
    }

    try {
      const report = await this.pc.getStats();
      let bitrate: number | null = null;
      let rtt: number | null = null;
      let loss: number | null = null;

      report.forEach((s: Record<string, unknown>) => {
        if (s.type === "candidate-pair" && (s.nominated || s.state === "succeeded")) {
          if (typeof s.availableOutgoingBitrate === "number") {
            bitrate = s.availableOutgoingBitrate;
          }
          if (typeof s.currentRoundTripTime === "number") {
            rtt = (s.currentRoundTripTime as number) * 1000;
          }
        }
        if (s.type === "outbound-rtp" && s.kind === "audio") {
          const sent = (s.packetsSent as number) ?? 0;
          const lost = (s.packetsLost as number) ?? 0;
          const dSent = sent - this.prevPacketsSent;
          const dLost = lost - this.prevPacketsLost;
          if (dSent > 0) loss = Math.max(0, (dLost / (dSent + dLost)) * 100);
          this.prevPacketsSent = sent;
          this.prevPacketsLost = lost;
        }
      });

      this.latest = { bitrateBps: bitrate, rttMs: rtt, lossPct: loss, effectiveType };
    } catch {
      this.latest = { bitrateBps: null, rttMs: null, lossPct: null, effectiveType };
    }
    return this.latest;
  }

  get value(): NetStats {
    return this.latest;
  }
}
