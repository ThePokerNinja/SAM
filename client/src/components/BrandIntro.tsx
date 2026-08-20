import { useCallback, useEffect, useRef, useState } from "react";
import { CandleFlame } from "./CandleFlame";

type Phase = "candle" | "igniting" | "dark" | "bright" | "settle" | "done";

interface Props {
  /** External readiness gate: the final reveal waits until Sam is ready. */
  ready: boolean;
  /** Fired when the user clicks the candle. Return false to deny (no ignite animation). */
  onIgnite?: () => boolean | void;
  /** Fired once the reveal finishes and the portal beneath is interactive. */
  onRevealed?: () => void;
  /** Owner Google sign-in is required before the candle can ignite. */
  needsSignIn?: boolean;
  /** Quiet status under the Google button after a failed return. */
  signInHint?: string;
  /** Starts owner authentication through rm_api's Google OAuth flow. */
  onGoogleSignIn?: () => void;
  /** Card artwork shown during the bright lead-up. */
  cardSrc?: string;
}

const MIN_BRIGHT_MS = 1300; // keep the card on screen at least this long

/**
 * Cinematic intro: a single gold candle flame in the dark. Click anywhere to
 * ignite -> the room dips dark -> blooms to light while the business card leads
 * up -> settles into the portal. No text.
 */
export function BrandIntro({
  ready,
  onIgnite,
  onRevealed,
  needsSignIn = false,
  signInHint = "",
  onGoogleSignIn,
  cardSrc = "/brand/card.svg",
}: Props) {
  const [phase, setPhase] = useState<Phase>("candle");
  const [boost, setBoost] = useState(0);
  const brightStart = useRef(0);
  const readyRef = useRef(ready);
  readyRef.current = ready;

  const ignite = useCallback(() => {
    if (phase !== "candle") return;
    if (needsSignIn) {
      onGoogleSignIn?.();
      return;
    }
    const ok = onIgnite?.();
    if (ok === false) return;
    setPhase("igniting");
  }, [phase, needsSignIn, onIgnite, onGoogleSignIn]);

  // Flare the flame up during ignite.
  useEffect(() => {
    if (phase !== "igniting") return;
    let raf = 0;
    const t0 = performance.now();
    const tick = () => {
      const k = Math.min(1, (performance.now() - t0) / 600);
      setBoost(k * 1.3);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const to = window.setTimeout(() => setPhase("dark"), 620);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(to);
    };
  }, [phase]);

  // Dark dip -> bright bloom.
  useEffect(() => {
    if (phase !== "dark") return;
    const to = window.setTimeout(() => {
      brightStart.current = performance.now();
      setPhase("bright");
    }, 360);
    return () => window.clearTimeout(to);
  }, [phase]);

  // Hold the bright/card lead-up until Sam is ready, then settle.
  useEffect(() => {
    if (phase !== "bright") return;
    let to = 0;
    const trySettle = () => {
      if (!readyRef.current) return;
      const elapsed = performance.now() - brightStart.current;
      to = window.setTimeout(() => setPhase("settle"), Math.max(0, MIN_BRIGHT_MS - elapsed));
    };
    trySettle();
    const poll = window.setInterval(trySettle, 120);
    return () => {
      window.clearTimeout(to);
      window.clearInterval(poll);
    };
  }, [phase, ready]);

  // Fade the overlay out, hand control to the portal.
  useEffect(() => {
    if (phase !== "settle") return;
    const to = window.setTimeout(() => {
      setPhase("done");
      onRevealed?.();
    }, 700);
    return () => window.clearTimeout(to);
  }, [phase, onRevealed]);

  return (
    <div
      className={`brand-intro phase-${phase}${needsSignIn ? " needs-signin" : ""}`}
      role={phase === "candle" && !needsSignIn ? "button" : undefined}
      aria-label={phase === "candle" && !needsSignIn ? "Begin" : undefined}
      tabIndex={phase === "candle" && !needsSignIn ? 0 : -1}
      onClick={needsSignIn ? undefined : ignite}
      onKeyDown={(e) => {
        if (phase === "candle" && !needsSignIn && (e.key === "Enter" || e.key === " ")) {
          ignite();
        }
      }}
    >
      <div className="bi-candle">
        <CandleFlame boost={boost} className="bi-candle-canvas" />
      </div>
      {needsSignIn && (
        <div className="bi-sign-in">
          <button
            type="button"
            className="bi-google-sign-in"
            onClick={(event) => {
              event.stopPropagation();
              onGoogleSignIn?.();
            }}
          >
            Continue with Google
          </button>
          {signInHint ? <p className="bi-sign-in-hint">{signInHint}</p> : null}
        </div>
      )}
      <div className="bi-card" aria-hidden="true">
        <img src={cardSrc} alt="" draggable={false} />
      </div>
      <div className="bi-flash" aria-hidden="true" />
      <div className="bi-dark" aria-hidden="true" />
    </div>
  );
}
