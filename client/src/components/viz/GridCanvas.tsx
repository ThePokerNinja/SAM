import { useEffect, useRef } from "react";
import { stateRgb, vizEnergy } from "./stateColors";

interface Props {
  state: string;
  volume: number;
  className?: string;
}

/** Pulsing dot grid � center blooms on voice energy. */
export function GridCanvas({ state, volume, className }: Props) {
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
    const cols = 10;
    const rows = 10;

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

      const gridW = base * 1.5;
      const gridH = base * 1.5;
      const cellW = gridW / cols;
      const cellH = gridH / rows;
      const startX = cx - gridW / 2;
      const startY = cy - gridH / 2;

      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          const px = startX + col * cellW + cellW / 2;
          const py = startY + row * cellH + cellH / 2;
          const dx = (col - (cols - 1) / 2) / cols;
          const dy = (row - (rows - 1) / 2) / rows;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const ripple = Math.sin(dist * 8 - t * 2.5) * 0.5 + 0.5;
          const centerBoost = Math.max(0, 1 - dist * 2.2) * vol;
          const alpha = Math.min(1, (0.08 + ripple * 0.25 * energy + centerBoost * 0.7) * (1 - dist * 0.35));
          const radius = Math.max(1, base * 0.022 * (0.6 + alpha));
          c.beginPath();
          c.arc(px, py, radius * dpr, 0, Math.PI * 2);
          c.fillStyle = `rgba(${r},${g},${b},${alpha})`;
          if (alpha > 0.35) {
            c.shadowBlur = base * 0.04;
            c.shadowColor = `rgba(${r},${g},${b},0.9)`;
          }
          c.fill();
        }
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
