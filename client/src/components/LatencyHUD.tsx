import type { TurnTiming } from "../lib/transport";
import type { TierSignals } from "../tier/types";

interface Props {
  turns: TurnTiming[];
  signals: TierSignals;
}

function percentile(values: number[], p: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return Math.round(sorted[idx]);
}

const fmt = (n: number | null, unit = "ms") => (n == null ? "—" : `${n}${unit}`);

// On-screen proof of the KPI: rolling v2v p50/p95 against the 800/1500 lines,
// plus the last turn's per-stage breakdown and live tier signals (spec §6).
export function LatencyHUD({ turns, signals }: Props) {
  const v2v = turns.map((t) => t.v2vMs);
  const p50 = percentile(v2v, 50);
  const p95 = percentile(v2v, 95);
  const last = turns[turns.length - 1];

  const p50ok = p50 != null && p50 <= 800;
  const p95ok = p95 != null && p95 <= 1500;

  return (
    <div className="hud">
      <div className="hud-row hud-row--kpi">
        <div className={`hud-kpi ${p50ok ? "ok" : "bad"}`}>
          <span className="hud-kpi-label">v2v p50</span>
          <span className="hud-kpi-val">{fmt(p50)}</span>
          <span className="hud-kpi-budget">≤ 800</span>
        </div>
        <div className={`hud-kpi ${p95ok ? "ok" : "bad"}`}>
          <span className="hud-kpi-label">v2v p95</span>
          <span className="hud-kpi-val">{fmt(p95)}</span>
          <span className="hud-kpi-budget">≤ 1500</span>
        </div>
        <div className="hud-kpi">
          <span className="hud-kpi-label">turns</span>
          <span className="hud-kpi-val">{turns.length}</span>
        </div>
      </div>

      <div className="hud-stages">
        <span>detect {fmt(last ? Math.round(last.turnDetectMs) : null)}</span>
        <span>stt {fmt(last ? Math.round(last.sttMs) : null)}</span>
        <span>brain {fmt(last ? Math.round(last.brainTtftMs) : null)}</span>
        <span>tts {fmt(last ? Math.round(last.ttsTtfbMs) : null)}</span>
        <span>net {fmt(last ? Math.round(last.netMs) : null)}</span>
      </div>

      <div className="hud-signals">
        <span>fps {Math.round(signals.fps)}</span>
        <span>
          bw {signals.bitrateBps ? `${(signals.bitrateBps / 1e6).toFixed(1)}M` : "—"}
        </span>
        <span>rtt {fmt(signals.rttMs)}</span>
        <span>loss {signals.lossPct != null ? `${signals.lossPct.toFixed(1)}%` : "—"}</span>
        {signals.audioRisk && <span className="hud-flag">AUDIO RISK</span>}
      </div>
    </div>
  );
}
