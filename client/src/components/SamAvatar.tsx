import type { VisualMode } from "../tier/types";
import type { SamPhase } from "../lib/transport";

interface Props {
  phase: SamPhase;
  visual: VisualMode;
  persona: string;
}

// Tiered visual: "full"/"simple" stand in for the Rive avatar (wired in Phase 4/5 with a
// .riv asset), "static" is a pulsing audio ring, "none" is a text status (Lifeboat).
// The visual layer is the FIRST thing the TierController sacrifices, so each mode is cheap.
export function SamAvatar({ phase, visual, persona }: Props) {
  if (visual === "none") {
    return (
      <div className="avatar avatar--none">
        <span className="avatar-status-text">{persona} · {phase}</span>
      </div>
    );
  }

  const speaking = phase === "speaking";
  const listening = phase === "listening";
  const thinking = phase === "thinking";

  return (
    <div className={`avatar avatar--${visual} phase-${phase}`}>
      <div className="avatar-core">
        {/* Placeholder for the Rive runtime canvas (full/simple modes). */}
        <div className="avatar-orb" data-speaking={speaking} data-thinking={thinking} />
        {visual === "full" && <div className="avatar-ring avatar-ring--outer" />}
        <div className="avatar-ring avatar-ring--inner" data-active={speaking || listening} />
      </div>
      <div className="avatar-label">{persona}</div>
    </div>
  );
}
