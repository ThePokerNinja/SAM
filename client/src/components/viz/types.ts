export type VizTreatment = "aura" | "wave" | "radial" | "bar" | "grid";

export const VIZ_TREATMENTS: VizTreatment[] = ["aura", "wave", "radial", "bar", "grid"];

export const VIZ_LABELS: Record<VizTreatment, string> = {
  aura: "Aura",
  wave: "Wave",
  radial: "Radial",
  bar: "Bar",
  grid: "Grid",
};

const STORAGE_KEY = "sam-viz-treatment";

export function readVizTreatment(): VizTreatment {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && VIZ_TREATMENTS.includes(v as VizTreatment)) return v as VizTreatment;
  } catch {
    /* private mode */
  }
  return "aura";
}

export function storeVizTreatment(t: VizTreatment): void {
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* ignore */
  }
}
