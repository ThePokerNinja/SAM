export type RGB = [number, number, number];

/** Gold = speaking/thinking; cyan = listening. Shared across all canvas treatments. */
export const STATE_RGB: Record<string, RGB> = {
  speaking: [245, 181, 133],
  thinking: [236, 177, 129],
  listening: [96, 200, 232],
  connecting: [120, 140, 160],
  initializing: [120, 140, 160],
  disconnected: [70, 80, 92],
};

export function stateRgb(state: string): RGB {
  return STATE_RGB[state] ?? STATE_RGB.disconnected;
}

export function vizEnergy(state: string, volume: number, t: number): number {
  const speaking = state === "speaking";
  const active = speaking || state === "thinking" || state === "listening";
  const breathe = 0.5 + 0.5 * Math.sin(t * (active ? 1.6 : 0.8));
  const surge = speaking
    ? volume * 1.4
    : state === "listening"
      ? 0.18 + 0.1 * breathe
      : 0.08 * breathe;
  return Math.min(1, 0.18 + 0.4 * breathe * (active ? 1 : 0.4) + surge);
}
