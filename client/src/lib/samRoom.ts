// Connects the browser to a fresh LiveKit room and publishes the mic. The agent worker
// (registered with no agent_name) auto-dispatches Samuel into whatever room we join.
import { Room } from "livekit-client";
import {
  getPortalAccessKey,
  PORTAL_ACCESS_HEADER,
} from "./portalAccess";

export interface SamSession {
  room: Room;
  roomName: string;
}

export class PortalAccessDeniedError extends Error {
  constructor() {
    super("access_denied");
    this.name = "PortalAccessDeniedError";
  }
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

export async function fetchTokenHealth(): Promise<{
  portalAccessRequired: boolean;
}> {
  const base = tokenBase();
  if (!base) return { portalAccessRequired: false };
  try {
    const res = await fetch(base + "/health", { headers: { Accept: "application/json" } });
    if (!res.ok) return { portalAccessRequired: false };
    const data = (await res.json()) as { portalAccessRequired?: boolean };
    return { portalAccessRequired: Boolean(data.portalAccessRequired) };
  } catch {
    return { portalAccessRequired: false };
  }
}

export async function connectSam(): Promise<SamSession> {
  const base = tokenBase();
  const headers: Record<string, string> = { Accept: "application/json" };
  const access = getPortalAccessKey();
  if (access) headers[PORTAL_ACCESS_HEADER] = access;

  const res = await fetch(base + "/token", {
    method: "POST",
    headers,
  });
  if (res.status === 403) throw new PortalAccessDeniedError();
  if (!res.ok) throw new Error(`token request failed (${res.status})`);
  const data = (await res.json()) as { token: string; url: string; room: string };
  if (!data.token || !data.url) throw new Error("token server returned no token/url");

  const room = new Room({ adaptiveStream: true, dynacast: true });
  await room.connect(data.url, data.token);
  await room.localParticipant.setMicrophoneEnabled(true);
  return { room, roomName: data.room };
}
