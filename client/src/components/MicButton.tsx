import type { SamPhase } from "../lib/transport";

interface Props {
  phase: SamPhase;
  onDown: () => void;
  onUp: () => void;
}

const LABEL: Record<SamPhase, string> = {
  idle: "Hold to talk to Sam",
  listening: "Listening… (release to send)",
  thinking: "Sam is thinking…",
  speaking: "Sam is speaking…",
};

export function MicButton({ phase, onDown, onUp }: Props) {
  const busy = phase === "thinking" || phase === "speaking";
  return (
    <button
      className={`mic-btn phase-${phase}`}
      disabled={busy}
      onPointerDown={(e) => {
        e.preventDefault();
        if (!busy) onDown();
      }}
      onPointerUp={(e) => {
        e.preventDefault();
        if (phase === "listening") onUp();
      }}
      onPointerLeave={() => {
        if (phase === "listening") onUp();
      }}
    >
      {LABEL[phase]}
    </button>
  );
}
