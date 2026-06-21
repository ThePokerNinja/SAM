import { useEffect, useMemo, useRef, useState } from "react";
import { LatencyHUD } from "./components/LatencyHUD";
import { MicButton } from "./components/MicButton";
import { SamAvatar } from "./components/SamAvatar";
import { Simulator } from "./components/Simulator";
import { TierBadge } from "./components/TierBadge";
import { useTierController } from "./hooks/useTierController";
import { createTransport } from "./lib/createTransport";
import type { PersonaId, SamPhase, TurnTiming } from "./lib/transport";

const PERSONA_LABEL: Record<PersonaId, string> = {
  samuel: "Samuel",
  schedule: "Schedule Agent",
  design: "Design Agent",
  sales: "Sales Agent",
};

const MAX_TURNS = 50;

export default function App() {
  const transport = useMemo(() => createTransport(), []);
  const [phase, setPhase] = useState<SamPhase>("idle");
  const [turns, setTurns] = useState<TurnTiming[]>([]);
  const [persona, setPersona] = useState<PersonaId>("samuel");
  const [showSim, setShowSim] = useState(true);
  const pcRef = useRef<RTCPeerConnection | null>(transport.getPeerConnection());

  const { controller, preset, signals, lastReason } = useTierController(pcRef.current);

  useEffect(() => {
    void transport.connect();
    const offPhase = transport.onPhase(setPhase);
    const offTurn = transport.onTurn((t) => {
      setPersona(t.persona);
      setTurns((prev) => {
        const next = [...prev, t].slice(-MAX_TURNS);
        // feed the latency guard: rolling v2v p95
        const v2v = next.map((x) => x.v2vMs).sort((a, b) => a - b);
        const p95 = v2v[Math.min(v2v.length - 1, Math.floor(0.95 * v2v.length))];
        controller.setSignals({ v2vP95Ms: Math.round(p95) });
        return next;
      });
    });
    return () => {
      offPhase();
      offTurn();
      transport.disconnect();
    };
  }, [transport, controller]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark">S.A.M.</span>
          <span className="brand-sub">System Agentic Model · Samuel</span>
        </div>
        <TierBadge preset={preset} reason={lastReason} />
      </header>

      <main className="stage">
        <SamAvatar phase={phase} visual={preset.visual} persona={PERSONA_LABEL[persona]} />
        <MicButton
          phase={phase}
          onDown={() => transport.setTalking(true)}
          onUp={() => transport.setTalking(false)}
        />
      </main>

      <LatencyHUD turns={turns} signals={signals} />

      <button className="sim-toggle" onClick={() => setShowSim((v) => !v)}>
        {showSim ? "Hide" : "Show"} simulator
      </button>
      {showSim && <Simulator controller={controller} />}

      <footer className="app-footer">
        Mock mode · no backend. Real LiveKit pipeline lands in Phase 5 (gated by v2v &lt; 800ms).
      </footer>
    </div>
  );
}
