import { describe, expect, it } from "vitest";
import { TierController } from "./TierController";
import type { TierId, TierSignals } from "./types";

// A controllable clock so cooldowns are deterministic.
function makeClock(start = 0) {
  let t = start;
  return { now: () => t, advance: (ms: number) => (t += ms) };
}

const GOOD: Partial<TierSignals> = {
  fps: 60,
  bitrateBps: 5_000_000,
  rttMs: 40,
  lossPct: 0,
  v2vP95Ms: 700,
  audioRisk: false,
};

function run(c: TierController, signals: Partial<TierSignals>, ticks: number) {
  c.setSignals(signals);
  for (let i = 0; i < ticks; i++) c.tick();
}

describe("TierController", () => {
  it("starts at the configured tier", () => {
    const c = new TierController({ startTier: 1 });
    expect(c.getTier()).toBe(1);
  });

  it("downgrades only after the sustained-downgrade window (~3 ticks)", () => {
    const clock = makeClock();
    const c = new TierController({ startTier: 1, now: clock.now });
    c.setSignals(GOOD);
    c.setSignals({ fps: 25 }); // SD-ish fps
    c.tick(); // 1
    expect(c.getTier()).toBe(1);
    c.tick(); // 2
    expect(c.getTier()).toBe(1);
    c.tick(); // 3 - now downgrades
    expect(c.getTier()).toBe(3);
  });

  it("worst signal wins (net can force a downgrade even with great fps)", () => {
    const clock = makeClock();
    const c = new TierController({ startTier: 1, now: clock.now });
    run(c, { ...GOOD, fps: 60, bitrateBps: 200_000 }, 3); // bitrate -> tier 4
    expect(c.getTier()).toBe(4);
  });

  it("upgrades slowly: needs headroom ticks AND cooldown, one step at a time", () => {
    const clock = makeClock();
    const c = new TierController({
      startTier: 1,
      now: clock.now,
      upgradeTicks: 8,
      upgradeCooldownMs: 10000,
    });
    // First force a downgrade so there's a recorded last-change time (at t=0).
    run(c, { ...GOOD, fps: 25 }, 3);
    expect(c.getTier()).toBe(3);
    // Great signals but upgrade cooldown (10s) not yet elapsed.
    run(c, GOOD, 8);
    expect(c.getTier()).toBe(3);
    clock.advance(10000);
    run(c, GOOD, 8);
    expect(c.getTier()).toBe(2); // stepped up exactly one tier
  });

  it("audio risk forces an immediate downgrade, bypassing hysteresis", () => {
    const clock = makeClock();
    const c = new TierController({ startTier: 1, now: clock.now });
    c.setSignals({ ...GOOD, audioRisk: true });
    c.tick(); // single tick, no waiting
    expect(c.getTier()).toBeGreaterThanOrEqual(3);
  });

  it("latency breach forces Lifeboat immediately", () => {
    const c = new TierController({ startTier: 1 });
    c.setSignals({ ...GOOD, v2vP95Ms: 1500 });
    c.tick();
    expect(c.getTier()).toBe(4);
  });

  it("emits onChange with a reason", () => {
    const clock = makeClock();
    const c = new TierController({ startTier: 1, now: clock.now });
    const changes: Array<{ to: TierId; reason: string }> = [];
    c.onChange((next, _prev, reason) => changes.push({ to: next.id, reason }));
    run(c, { ...GOOD, bitrateBps: 200_000 }, 3);
    expect(changes.length).toBe(1);
    expect(changes[0].to).toBe(4);
    expect(changes[0].reason).toBe("net");
  });

  it("manual override pins a tier but hard floor still wins", () => {
    const c = new TierController({ startTier: 1 });
    c.setManual(1);
    run(c, { ...GOOD, fps: 10 }, 5); // would normally downgrade
    expect(c.getTier()).toBe(1); // pinned
    c.setSignals({ audioRisk: true });
    c.tick();
    expect(c.getTier()).toBeGreaterThanOrEqual(3); // hard floor overrides manual
  });
});
