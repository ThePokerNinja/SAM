import type { Room } from "livekit-client";
import type { TierPreset } from "../tier/types";

export const TIER_TOPIC = "sam-tier";
const ENCODER = new TextEncoder();

export function peerConnectionFromRoom(room: Room | null): RTCPeerConnection | null {
  if (!room) return null;
  const engine = (room as { engine?: { pcManager?: { publisher?: { pc?: RTCPeerConnection } } } })
    .engine;
  return engine?.pcManager?.publisher?.pc ?? null;
}

export function publishTierUpdate(
  room: Room | null,
  preset: TierPreset,
  reason: string,
): void {
  if (!room || room.state !== "connected") return;
  const payload = ENCODER.encode(
    JSON.stringify({
      type: "tier_update",
      tier: preset.id,
      reason,
      brainModel: preset.brainModel,
      memoryTurns: preset.memoryTurns,
    }),
  );
  room.localParticipant
    .publishData(payload, { reliable: true, topic: TIER_TOPIC })
    .catch((err) => console.warn("[tierSync] publishData failed:", err));
}
