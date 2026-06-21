import { useEffect, useRef } from "react";
import { stateRgb, vizEnergy } from "./stateColors";

interface Props {
  state: string;
  volume: number;
  className?: string;
}

/** Radial spokes from center — circular spectrum, audio-reactive. */
export function RadialCanvas({ state, volume, className }: Props) {
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
    const bars = 36;

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
      const speaking = st === "speaking";

      c.clearRect(0, 0, w, h);
      c.globalCompositeOperation = "lighter";

      const inner = base * 0.12;
      const maxLen = base * (0.38 + 0.22 * energy);

      for (let i = 0; i < bars; i++) {
        const angle = (i / bars) * Math.PI * 2 - Math.PI / 2;
        const wobble = Math.sin(t * 2.4 + i * 0.45) * 0.15;
        const barVol = speaking ? vol * (0.6 + 0.4 * Math.sin(i * 0.8 + t * 3)) : energy * 0.5;
        const len = inner + maxLen * Math.max(0.15, barVol + wobble * energy);
        const x1 = cx + Math.cos(angle) * inner;
        const y1 = cy + Math.sin(angle) * inner;
        const x2 = cx + Math.cos(angle) * len;
        const y2 = cy + Math.sin(angle) * len;
        c.beginPath();
        c.moveTo(x1, y1);
        c.lineTo(x2, y2);
        c.strokeStyle = `rgba(${r},${g},${b},${0.25 + 0.55 * (barVol + 0.2)})`;
        c.lineWidth = Math.max(1.5, base * 0.014) * dpr;
        c.shadowBlur = base * 0.06;
        c.shadowColor = `rgba(${r},${g},${b},0.7)`;
        c.stroke();
      }

      c.beginPath();
      c.arc(cx, cy, inner * 0.85, 0, Math.PI * 2);
      c.fillStyle = `rgba(${r},${g},${b},${0.35 + 0.4 * energy})`;
      c.shadowBlur = base * 0.15;
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
