// Brand palette derived from business_cards_v2 / ms.com brand assets.
// Gold gradient stops are the literal card vectors; cyan is the voice-energy
// accent from voice.gif. Everything sits on deep navy.

export type RGB = [number, number, number];

export const BRAND = {
  navy: "#0b0e12",
  navyDeep: "#06080b",
  cyan: "#60c8e8",
  cyanRgb: [96, 200, 232] as RGB,
  chrome: "#dfe7ef",
  white: "#ffffff",
  // Dark gold -> warm peach (Adobe card gradient).
  goldStops: ["#A69557", "#BB9D64", "#D8A975", "#ECB181", "#F5B585"] as const,
  goldOffsets: [0, 0.2079, 0.5398, 0.8158, 1] as const,
  goldHot: "#FFE8C2", // hottest part of the flame core
  gold: "#ECB181", // representative mid gold for flat fills/CSS
};

export function hexToRgb(hex: string): RGB {
  const h = hex.replace("#", "");
  const n = parseInt(
    h.length === 3
      ? h
          .split("")
          .map((c) => c + c)
          .join("")
      : h,
    16,
  );
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function rgbToCss([r, g, b]: RGB, a = 1): string {
  return `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${a})`;
}

export function lerpRgb(a: RGB, b: RGB, t: number): RGB {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

const GOLD_RGB: RGB[] = BRAND.goldStops.map(hexToRgb);

/** Sample the brand gold gradient at t in [0,1] -> RGB. */
export function sampleGold(t: number): RGB {
  const x = Math.max(0, Math.min(1, t));
  const offs = BRAND.goldOffsets;
  for (let i = 0; i < offs.length - 1; i++) {
    if (x <= offs[i + 1]) {
      const span = offs[i + 1] - offs[i] || 1;
      return lerpRgb(GOLD_RGB[i], GOLD_RGB[i + 1], (x - offs[i]) / span);
    }
  }
  return GOLD_RGB[GOLD_RGB.length - 1];
}

/** Paint the gold gradient onto a canvas linear/radial gradient object. */
export function applyGoldStops(grad: CanvasGradient): CanvasGradient {
  BRAND.goldStops.forEach((hex, i) => grad.addColorStop(BRAND.goldOffsets[i], hex));
  return grad;
}
