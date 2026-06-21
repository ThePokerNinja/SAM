import { useCallback, useEffect, useRef, useState } from "react";
import { RoomContext } from "@livekit/components-react";
import "@livekit/components-styles";
import { Room, RoomEvent } from "livekit-client";
import { TierBadge } from "./components/TierBadge";
import { VoicePortal } from "./components/VoicePortal";
import { BrandIntro } from "./components/BrandIntro";
import { useTierController } from "./hooks/useTierController";
import {
  bootstrapPortalAccessFromUrl,
  clearPortalAccessKey,
  getPortalAccessKey,
} from "./lib/portalAccess";
import {
  connectSam,
  fetchTokenHealth,
  PortalAccessDeniedError,
} from "./lib/samRoom";
import { SAMUEL_DEFINITION } from "./brand/brand";

type Status = "idle" | "connecting" | "live" | "error" | "denied";

bootstrapPortalAccessFromUrl();

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState<string>("");
  const [revealed, setRevealed] = useState(false);
  const [attempt, setAttempt] = useState(0); // remount the intro back to candle on retry
  const [portalAccessRequired, setPortalAccessRequired] = useState(false);
  const roomRef = useRef<Room | null>(null);

  const { preset, lastReason } = useTierController(null);

  useEffect(() => {
    fetchTokenHealth().then((h) => setPortalAccessRequired(h.portalAccessRequired));
  }, []);

  const start = useCallback((): boolean => {
    if (portalAccessRequired && !getPortalAccessKey()) {
      setStatus("denied");
      setError("");
      return false;
    }

    setStatus("connecting");
    setError("");

    (async () => {
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
        if (e instanceof PortalAccessDeniedError) {
          clearPortalAccessKey();
          setStatus("denied");
          setError("");
          return;
        }
        setError(String((e as Error)?.message || e));
        setStatus("error");
        setAttempt((n) => n + 1);
      }
    })();

    return true;
  }, [portalAccessRequired]);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  const showIntro = !revealed || status !== "live";
  const accessDenied = status === "denied";

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
            accessDenied={accessDenied}
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
