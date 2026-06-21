import { ACTIVE_TIERS, PRESETS } from "./presets";
import { FpsSampler, NetSampler } from "./signals";
import type {
  TierChangeHandler,
  TierChangeReason,
  TierControllerOptions,
  TierId,
  TierPreset,
  TierSignals,
} from "./types";

const WARN_V2V_MS = 1450; // latency hard-floor line (KPI ceiling is 1500)

// Higher TierId = more degraded. Scoring returns the most-constrained tier a signal implies.
function scoreFps(fps: number): TierId {
  if (fps >= 55) return 1;
  if (fps >= 35) return 2;
  if (fps >= 22) return 3;
  return 4;
}

function scoreNet(s: TierSignals): TierId {
  const scores: TierId[] = [];
  if (s.bitrateBps != null) {
    if (s.bitrateBps > 2_500_000) scores.push(1);
    else if (s.bitrateBps > 1_000_000) scores.push(2);
    else if (s.bitrateBps > 300_000) scores.push(3);
    else scores.push(4);
  }
  if (s.rttMs != null) {
    if (s.rttMs < 120) scores.push(1);
    else if (s.rttMs < 250) scores.push(2);
    else if (s.rttMs < 450) scores.push(3);
    else scores.push(4);
  }
  if (s.lossPct != null) {
    if (s.lossPct < 1) scores.push(1);
    else if (s.lossPct < 3) scores.push(2);
    else if (s.lossPct < 8) scores.push(3);
    else scores.push(4);
  }
  if (scores.length === 0 && s.effectiveType) {
    switch (s.effectiveType) {
      case "4g":
        scores.push(1);
        break;
      case "3g":
        scores.push(3);
        break;
      case "2g":
      case "slow-2g":
        scores.push(4);
        break;
    }
  }
  return scores.length ? (Math.max(...scores) as TierId) : 1;
}

function scoreLatency(v2vP95: number | null): TierId {
  if (v2vP95 == null) return 1;
  if (v2vP95 < 1000) return 1;
  if (v2vP95 < 1250) return 2;
  if (v2vP95 < WARN_V2V_MS) return 3;
  return 4;
}

const clampActive = (t: TierId): TierId =>
  Math.min(Math.max(t, ACTIVE_TIERS[0]), ACTIVE_TIERS[ACTIVE_TIERS.length - 1]) as TierId;

export class TierController {
  private opts: Required<Omit<TierControllerOptions, "now">> & { now: () => number };
  private signals: TierSignals = {
    fps: 60,
    fpsMin1s: 60,
    bitrateBps: null,
    rttMs: null,
    lossPct: null,
    v2vP95Ms: null,
    audioRisk: false,
  };
  private current: TierId;
  private manual: TierId | null = null;
  private downCount = 0;
  private upCount = 0;
  // -Infinity so the first tier change is never blocked by the cooldown gate.
  private lastChangeAt = -Infinity;
  private handlers = new Set<TierChangeHandler>();
  private fpsSampler = new FpsSampler();
  private netSampler = new NetSampler();
  private intervalId: ReturnType<typeof setInterval> | null = null;

  constructor(options: TierControllerOptions = {}) {
    this.opts = {
      tickMs: options.tickMs ?? 1000,
      downgradeTicks: options.downgradeTicks ?? 3,
      upgradeTicks: options.upgradeTicks ?? 8,
      cooldownMs: options.cooldownMs ?? 4000,
      upgradeCooldownMs: options.upgradeCooldownMs ?? 10000,
      startTier: options.startTier ?? 2,
      now: options.now ?? (() => Date.now()),
    };
    this.current = clampActive(this.opts.startTier);
  }

  start(pc?: RTCPeerConnection): void {
    this.fpsSampler.start();
    this.netSampler.attach(pc ?? null);
    if (this.intervalId == null && typeof setInterval !== "undefined") {
      this.intervalId = setInterval(() => void this.sampleAndTick(), this.opts.tickMs);
    }
  }

  stop(): void {
    this.fpsSampler.stop();
    if (this.intervalId != null) clearInterval(this.intervalId);
    this.intervalId = null;
  }

  /** Pull live samples then evaluate. Used by the interval; tests call tick() directly. */
  private async sampleAndTick(): Promise<void> {
    const net = await this.netSampler.refresh();
    this.signals = {
      ...this.signals,
      fps: this.fpsSampler.fps,
      fpsMin1s: this.fpsSampler.fpsMin1s,
      bitrateBps: net.bitrateBps,
      rttMs: net.rttMs,
      lossPct: net.lossPct,
      effectiveType: net.effectiveType,
    };
    this.tick();
  }

  /** Merge externally-sourced signals (audio health, measured v2v p95, or test input). */
  setSignals(partial: Partial<TierSignals>): void {
    this.signals = { ...this.signals, ...partial };
  }

  /** One evaluation step. Public so tests can drive it deterministically. */
  tick(): void {
    // Hard floor - bypasses all hysteresis & cooldown. Speech wins, instantly.
    if (this.signals.audioRisk) {
      this.applyTier(clampActive(Math.max(this.current, 3) as TierId), "hardFloor:audio", true);
      return;
    }
    if (this.signals.v2vP95Ms != null && this.signals.v2vP95Ms >= WARN_V2V_MS) {
      this.applyTier(clampActive(4), "hardFloor:latency", true);
      return;
    }

    if (this.manual != null) return; // manual override suspends auto (hard floor already handled)

    const fpsT = scoreFps(this.signals.fps);
    const netT = scoreNet(this.signals);
    const latT = scoreLatency(this.signals.v2vP95Ms);
    const desired = clampActive(Math.max(fpsT, netT, latT) as TierId);
    const reason: TierChangeReason =
      desired === latT && desired > fpsT && desired > netT
        ? "latency"
        : netT >= fpsT
          ? "net"
          : "fps";

    if (desired > this.current) {
      // downgrade - fast
      this.upCount = 0;
      this.downCount++;
      if (this.downCount >= this.opts.downgradeTicks && this.canChange()) {
        this.applyTier(desired, reason, false); // may jump multiple tiers
        this.downCount = 0;
      }
    } else if (desired < this.current) {
      // upgrade - slow + extra cooldown, one step at a time
      this.downCount = 0;
      this.upCount++;
      const cooled = this.opts.now() - this.lastChangeAt >= this.opts.upgradeCooldownMs;
      if (this.upCount >= this.opts.upgradeTicks && cooled) {
        this.applyTier((this.current - 1) as TierId, "upgrade", false);
        this.upCount = 0;
      }
    } else {
      this.downCount = 0;
      this.upCount = 0;
    }
  }

  private canChange(): boolean {
    return this.opts.now() - this.lastChangeAt >= this.opts.cooldownMs;
  }

  private applyTier(next: TierId, reason: TierChangeReason, force: boolean): void {
    if (next === this.current) {
      if (force) this.lastChangeAt = this.opts.now();
      return;
    }
    if (!force && !this.canChange()) return;
    const prev = PRESETS[this.current];
    this.current = next;
    this.lastChangeAt = this.opts.now();
    const nextPreset = PRESETS[next];
    for (const h of this.handlers) h(nextPreset, prev, reason);
  }

  setManual(tier: TierId | "auto"): void {
    if (tier === "auto") {
      this.manual = null;
      return;
    }
    this.manual = tier;
    this.applyTier(tier, "manual", true);
  }

  onChange(cb: TierChangeHandler): () => void {
    this.handlers.add(cb);
    return () => this.handlers.delete(cb);
  }

  getTier(): TierId {
    return this.current;
  }

  getPreset(): TierPreset {
    return PRESETS[this.current];
  }

  getSignals(): TierSignals {
    return { ...this.signals };
  }
}
