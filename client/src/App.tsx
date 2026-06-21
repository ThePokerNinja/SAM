import { useCallback, useEffect, useRef, useState } from "react";
import { RoomContext } from "@livekit/components-react";
import "@livekit/components-styles";
import { Room, RoomEvent } from "livekit-client";
import { TierBadge } from "./components/TierBadge";
import { VoicePortal } from "./components/VoicePortal";
import { BrandIntro } from "./components/BrandIntro";
import { useTierController } from "./hooks/useTierController";
import { connectSam } from "./lib/samRoom";
import { SAMUEL_DEFINITION } from "./brand/brand";

type Status = "idle" | "connecting" | "live" | "error";

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState<string>("");
  const [revealed, setRevealed] = useState(false);
  const [attempt, setAttempt] = useState(0); // remount the intro back to candle on retry
  const roomRef = useRef<Room | null>(null);

  // Tier controller drives only the visual choice here (fps-based; no raw pc needed).
  const { preset, lastReason } = useTierController(null);

  const start = useCallback(async () => {
    setStatus("connecting");
    setError("");
    try {
      const { room: r } = await connectSam();
      roomRef.current = r;
      r.on(RoomEvent.Disconnected, () => {
        setStatus("idle");
        setRoom(null);
        roomRef.current = null;
        setRevealed(false);
        setAttempt((n) => n + 1);
      });
      setRoom(r);
      setStatus("live");
    } catch (e) {
      setError(String((e as Error)?.message || e));
      setStatus("error");
      setAttempt((n) => n + 1); // send the intro back to the candle
    }
  }, []);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  const showIntro = !revealed || status !== "live";

  return (
    <div className="app">
      {revealed && status === "live" && (
        <header className="app-header app-header--floating">
          <div className="brand" aria-label={SAMUEL_DEFINITION}>
            <span className="brand-mark">Samuel</span>
            <span className="brand-sub">S.A.M. � Systems Agent Model</span>
          </div>
          <TierBadge preset={preset} reason={lastReason} />
        </header>
      )}

      <main className="stage stage--full">
        {status === "live" && room && (
          <RoomContext.Provider value={room}>
            <VoicePortal />
          </RoomContext.Provider>
        )}

        {showIntro && (
          <BrandIntro
            key={attempt}
            ready={status === "live"}
            onIgnite={start}
            onRevealed={() => setRevealed(true)}
          />
        )}

        {status === "error" && (
          <div className="connect-error-overlay">
            <p className="connect-error">
              Couldn&rsquo;t connect: {error}
              <br />
              <span className="connect-error-hint">
                Check the token server (VITE_TOKEN_URL) and that the agent worker is running, then tap the flame again.
              </span>
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
