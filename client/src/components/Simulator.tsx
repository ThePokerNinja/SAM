import type { TierController } from "../tier/TierController";

// Dev-only panel: inject signals so reviewers can watch the TierController react
// (the real fps/network samplers run automatically; this overrides them for demo).
export function Simulator({ controller }: { controller: TierController }) {
  return (
    <div className="sim">
      <div className="sim-title">Signal simulator (dev)</div>
      <div className="sim-grid">
        <button onClick={() => controller.setSignals({ fps: 60, bitrateBps: 5e6, rttMs: 40, lossPct: 0 })}>
          Strong (→ Studio)
        </button>
        <button onClick={() => controller.setSignals({ fps: 40, bitrateBps: 1.8e6, rttMs: 180 })}>
          Mid (→ HD)
        </button>
        <button onClick={() => controller.setSignals({ fps: 26, bitrateBps: 0.6e6, rttMs: 320 })}>
          Weak (→ SD)
        </button>
        <button onClick={() => controller.setSignals({ fps: 15, bitrateBps: 0.2e6, rttMs: 600, lossPct: 10 })}>
          Collapsing (→ Lifeboat)
        </button>
        <button className="sim-danger" onClick={() => controller.setSignals({ audioRisk: true })}>
          Audio risk (hard floor)
        </button>
        <button onClick={() => controller.setSignals({ audioRisk: false })}>Clear audio risk</button>
        <button onClick={() => controller.setManual("auto")}>Auto</button>
        <button onClick={() => controller.setManual(1)}>Pin Studio</button>
      </div>
      <p className="sim-note">
        Downgrades take ~3 ticks (3s); upgrades need ~8s of headroom + cooldown. Hard floor is
        instant.
      </p>
    </div>
  );
}
