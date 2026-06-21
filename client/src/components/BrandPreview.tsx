import { useEffect, useState } from "react";
import { BrandIntro } from "./BrandIntro";
import { AuraCanvas } from "./AuraCanvas";

const STATE_LABEL: Record<string, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

// Synthetic conversation loop so the portal looks alive without a live worker.
const CYCLE: Array<{ state: string; ms: number }> = [
  { state: "listening", ms: 2600 },
  { state: "thinking", ms: 1500 },
  { state: "speaking", ms: 4200 },
];

/**
 * Standalone brand review (open with ?preview=1). Runs the full candle -> reveal
 * sequence and a self-animating mock portal - no LiveKit worker required.
 */
export function BrandPreview() {
  const [ready, setReady] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [demoState, setDemoState] = useState("listening");
  const [runId, setRunId] = useState(0);

  // After ignite, pretend Sam connects ~1.4s later.
  const onIgnite = () => {
    window.setTimeout(() => setReady(true), 1400);
  };

  // Cycle the synthetic agent state once revealed.
  useEffect(() => {
    if (!revealed) return;
    let i = 0;
    let to = 0;
    const step = () => {
      setDemoState(CYCLE[i].state);
      to = window.setTimeout(() => {
        i = (i + 1) % CYCLE.length;
        step();
      }, CYCLE[i].ms);
    };
    step();
    return () => window.clearTimeout(to);
  }, [revealed]);

  const replay = () => {
    setRevealed(false);
    setReady(false);
    setDemoState("listening");
    setRunId((n) => n + 1);
  };

  return (
    <div className="preview-root">
      {/* Mock portal sits beneath the intro overlay. */}
      <div className={`portal-stage state-${demoState} preview-portal`}>
        <img src="/brand/rainmaker-mark.png" className="portal-mark" alt="" draggable={false} />

        <div className="viz-wrap">
          <AuraCanvas state={demoState} volume={demoState === "speaking" ? 0.6 : 0} />
        </div>

        <div className="portal-brand">
          <img src="/brand/signature-gold.png" className="portal-wordmark" alt="Michael Stewman" draggable={false} />
        </div>

        <div className="portal-status" aria-live="polite">
          {STATE_LABEL[demoState] ?? demoState}
        </div>
        <p className="portal-caption">
          {demoState === "speaking"
            ? "Atlantis is holding its breakout - I moved your stop up to lock the gain."
            : demoState === "thinking"
              ? ""
              : ""}
        </p>
      </div>

      <BrandIntro key={runId} ready={ready} onIgnite={onIgnite} onRevealed={() => setRevealed(true)} />

      {revealed && (
        <button className="preview-replay" onClick={replay} title="Replay intro">
          Replay intro
        </button>
      )}
    </div>
  );
}
