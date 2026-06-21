// Connects the browser to a fresh LiveKit room and publishes the mic. The agent worker
// (registered with no agent_name) auto-dispatches Samuel into whatever room we join.
import { Room } from "livekit-client";

export interface SamSession {
  room: Room;
  roomName: string;
}

/** Base URL of the token server. Set VITE_TOKEN_URL in prod; defaults to local dev. */
export function tokenBase(): string {
  const fromEnv = import.meta.env.VITE_TOKEN_URL as string | undefined;
  if (fromEnv && fromEnv.length) return fromEnv.replace(/\/$/, "");
  const h = typeof location !== "undefined" ? location.hostname : "";
  if (h === "localhost" || h === "127.0.0.1") return "http://127.0.0.1:8788";
  // Prod fallbacks when VITE_TOKEN_URL was not injected at build (override via env on Render).
  if (h === "voice.michaelstewman.com" || h.endsWith(".onrender.com")) {
    return "https://sam-token.onrender.com";
  }
  return "";
}

export async function connectSam(): Promise<SamSession> {
  const base = tokenBase();
  const res = await fetch(base + "/token", {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`token request failed (${res.status})`);
  const data = (await res.json()) as { token: string; url: string; room: string };
  if (!data.token || !data.url) throw new Error("token server returned no token/url");

  const room = new Room({ adaptiveStream: true, dynacast: true });
  await room.connect(data.url, data.token);
  await room.localParticipant.setMicrophoneEnabled(true);
  return { room, roomName: data.room };
}
