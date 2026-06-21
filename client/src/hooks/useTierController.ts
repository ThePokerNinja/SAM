import { useEffect, useMemo, useRef, useState } from "react";
import { TierController } from "../tier/TierController";
import type { TierPreset, TierSignals } from "../tier/types";

export function useTierController(pc: RTCPeerConnection | null) {
  const controller = useMemo(() => new TierController({ startTier: 2 }), []);
  const [preset, setPreset] = useState<TierPreset>(controller.getPreset());
  const [signals, setSignals] = useState<TierSignals>(controller.getSignals());
  const [lastReason, setLastReason] = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const off = controller.onChange((next, _prev, reason) => {
      setPreset(next);
      setLastReason(reason);
    });
    controller.start(pc ?? undefined);
    // mirror live signals into React state for the HUD
    pollRef.current = setInterval(() => setSignals(controller.getSignals()), 500);
    return () => {
      off();
      controller.stop();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [controller, pc]);

  return { controller, preset, signals, lastReason };
}
