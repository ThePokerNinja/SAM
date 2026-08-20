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
  consumeOAuthReturn,
  getPortalAuthToken,
  clearPortalAccessKey,
  getPortalAccessKey,
  setPortalAuthToken,
  startGoogleSignIn,
} from "./lib/portalAccess";
import {
  connectSam,
  fetchTokenHealth,
  PortalAccessDeniedError,
} from "./lib/samRoom";
import { SAMUEL_DEFINITION } from "./brand/brand";

type Status = "idle" | "connecting" | "live" | "error" | "denied";

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState<string>("");
  const [revealed, setRevealed] = useState(false);
  const [attempt, setAttempt] = useState(0); // remount the intro back to candle on retry
  const [portalAccessRequired, setPortalAccessRequired] = useState(false);
  const [googleAuthRequired, setGoogleAuthRequired] = useState(false);
  const [hasAuth, setHasAuth] = useState(false);
  const [signInHint, setSignInHint] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const startRef = useRef<() => boolean>(() => false);
  const authReadyRef = useRef(false);

  const { preset, lastReason } = useTierController(room);

  const start = useCallback((): boolean => {
    if (googleAuthRequired && !getPortalAuthToken()) {
      startGoogleSignIn();
      return false;
    }
    if (!authReadyRef.current && !getPortalAuthToken()) {
      return false;
    }
    if (portalAccessRequired && !getPortalAuthToken() && !getPortalAccessKey()) {
      startGoogleSignIn();
      return false;
    }

    setStatus("connecting");
    setError("");
    setSignInHint("");

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
          setPortalAuthToken("");
          clearPortalAccessKey();
          setHasAuth(false);
          setStatus("denied");
          setSignInHint("This Google account isn't authorized.");
          setError("");
          return;
        }
        setError(String((e as Error)?.message || e));
        setStatus("error");
        setAttempt((n) => n + 1);
      }
    })();

    return true;
  }, [googleAuthRequired, portalAccessRequired]);
  startRef.current = start;

  useEffect(() => {
    bootstrapPortalAccessFromUrl();
    const oauth = consumeOAuthReturn();
    setHasAuth(Boolean(getPortalAuthToken()));
    if (oauth === "error") {
      setSignInHint("Google sign-in didn't complete. Try again.");
    }
    fetchTokenHealth().then((h) => {
      setPortalAccessRequired(h.portalAccessRequired);
      setGoogleAuthRequired(h.googleAuthRequired);
      authReadyRef.current = true;
      setAuthReady(true);
      if (oauth === "fresh" && getPortalAuthToken()) {
        startRef.current();
      }
    });
  }, []);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  const showIntro = !revealed || status !== "live";
  const needsSignIn =
    authReady &&
    status !== "connecting" &&
    status !== "live" &&
    ((googleAuthRequired && !hasAuth) || status === "denied");

  return (
    <div className="app">
      {revealed && status === "live" && (
        <header className="app-header app-header--floating">
          <div className="brand" aria-label={SAMUEL_DEFINITION}>
            <span className="brand-mark">Samuel</span>
            <span className="brand-sub">S.A.M. — Systems Agent Model</span>
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
            needsSignIn={needsSignIn}
            signInHint={signInHint}
            onIgnite={start}
            onGoogleSignIn={startGoogleSignIn}
            onRevealed={() => setRevealed(true)}
          />
        )}

        {status === "error" && (
          <div className="connect-error-overlay">
            <p className="connect-error">
              Couldn&rsquo;t connect: {error}
              <br />
              <span className="connect-error-hint">
                Open this in Safari or Chrome, allow the microphone, then try again.
              </span>
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
