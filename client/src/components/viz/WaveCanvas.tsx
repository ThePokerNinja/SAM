import { useEffect, useRef } from "react";
import { stateRgb, vizEnergy } from "./stateColors";

interface Props {
  state: string;
  volume: number;
  className?: string;
}

/** Horizontal flowing wave bands � brand gold/cyan, audio-reactive. */
export function WaveCanvas({ state, volume, className }: Props) {
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
      const st = stateRef.current;
      const [r, g, b] = stateRgb(st);
      const vol = volRef.current;
      const energy = vizEnergy(st, vol, t);

      c.clearRect(0, 0, w, h);
      c.globalCompositeOperation = "lighter";

      const glow = c.createRadialGradient(cx, cy, 0, cx, cy, base * 0.9);
      glow.addColorStop(0, `rgba(${r},${g},${b},${0.12 * energy})`);
      glow.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = glow;
      c.fillRect(0, 0, w, h);

      const bands = 5;
      for (let i = 0; i < bands; i++) {
        const phase = t * (1.2 + i * 0.15) + i * 0.9;
        const amp = base * (0.06 + 0.14 * energy) * (1 - i * 0.12);
        const yOff = (i - (bands - 1) / 2) * base * 0.14;
        c.beginPath();
        const steps = 48;
        for (let s = 0; s <= steps; s++) {
          const px = (s / steps) * w;
          const nx = s / steps;
          const wave =
            Math.sin(nx * Math.PI * 4 + phase) * amp +
            Math.sin(nx * Math.PI * 7 - phase * 1.3) * amp * 0.35;
          const py = cy + yOff + wave;
          if (s === 0) c.moveTo(px, py);
          else c.lineTo(px, py);
        }
        c.strokeStyle = `rgba(${r},${g},${b},${(0.35 + 0.45 * energy) * (1 - i * 0.1)})`;
        c.lineWidth = Math.max(1.5, base * 0.018) * dpr;
        c.shadowBlur = base * 0.08;
        c.shadowColor = `rgba(${r},${g},${b},0.8)`;
        c.stroke();
      }
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
