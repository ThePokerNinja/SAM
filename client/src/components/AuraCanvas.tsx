import { useEffect, useRef } from "react";
import { stateRgb, vizEnergy } from "./viz/stateColors";

interface Props {
  /** Agent state (drives color + motion). */
  state: string;
  /** 0..1 audio amplitude (drives the surge). */
  volume: number;
  className?: string;
}

/**
 * "Aura" - a living energy ring on a canvas. Pure renderer: it takes state +
 * volume as props so it can be driven by LiveKit (AuraVisualizer) or by a
 * synthetic loop (brand preview) without touching the room hooks.
 */
export function AuraCanvas({ state, volume, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  const volRef = useRef(0);

  stateRef.current = state;
  volRef.current += ((volume || 0) - volRef.current) * 0.25;

  useEffect(() => {
    const maybeCanvas = canvasRef.current;
    if (!maybeCanvas) return;
    const maybeCtx = maybeCanvas.getContext("2d");
    if (!maybeCtx) return;
    const cv: HTMLCanvasElement = maybeCanvas;
    const c: CanvasRenderingContext2D = maybeCtx;

    let raf = 0;
    let t = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      const size = Math.min(cv.clientWidth, cv.clientHeight) || 320;
      cv.width = size * dpr;
      cv.height = size * dpr;
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(cv);

    function draw() {
      t += 0.016;
      const w = cv.width;
      const h = cv.height;
      const cx = w / 2;
      const cy = h / 2;
      const base = Math.min(w, h) * 0.5;

      const st = stateRef.current as string;
      const [r, g, b] = stateRgb(st);
      const vol = volRef.current;
      const active = st === "speaking" || st === "thinking" || st === "listening";

      c.clearRect(0, 0, w, h);
      c.globalCompositeOperation = "lighter";

      const energy = vizEnergy(st, vol, t);

      const glow = c.createRadialGradient(cx, cy, base * 0.02, cx, cy, base * (0.45 + 0.4 * energy));
      glow.addColorStop(0, `rgba(${r},${g},${b},${0.55 * energy + 0.1})`);
      glow.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = glow;
      c.fillRect(0, 0, w, h);

      const rings = 3;
      for (let i = 0; i < rings; i++) {
        const phase = t * (0.6 + i * 0.25) + i * 1.2;
        const wobble = Math.sin(phase) * base * 0.03 * (active ? 1 : 0.4);
        const radius = base * (0.34 + i * 0.13) + wobble + base * 0.18 * energy * (i === 0 ? 1 : 0.5);
        const alpha = (0.5 - i * 0.13) * (0.5 + energy);
        c.beginPath();
        c.arc(cx, cy, Math.max(2, radius), 0, Math.PI * 2);
        c.lineWidth = Math.max(1.5, base * (0.012 + 0.02 * energy * (i === 0 ? 1 : 0.4))) * dpr;
        c.strokeStyle = `rgba(${r},${g},${b},${Math.max(0, alpha)})`;
        c.shadowBlur = base * 0.12 * (0.4 + energy);
        c.shadowColor = `rgba(${r},${g},${b},0.9)`;
        c.stroke();
      }

      c.beginPath();
      c.arc(cx, cy, base * (0.05 + 0.05 * energy), 0, Math.PI * 2);
      c.fillStyle = `rgba(${Math.min(255, r + 40)},${Math.min(255, g + 40)},${Math.min(255, b + 40)},${0.6 + 0.4 * energy})`;
      c.shadowBlur = base * 0.2;
      c.shadowColor = `rgba(${r},${g},${b},1)`;
      c.fill();

      c.shadowBlur = 0;
      c.globalCompositeOperation = "source-over";
      raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className={className ?? "aura-canvas"} aria-hidden="true" />;
}
