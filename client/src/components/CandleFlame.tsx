import { useEffect, useRef } from "react";

interface Props {
  /** 0..1 extra energy (e.g. on ignite/flare or audio). Read live via ref. */
  boost?: number;
  className?: string;
}

/**
 * A single candle flame rendered on a canvas, painted with the brand gold
 * gradient. Layered noise drives a believable flicker/sway; `boost` flares the
 * flame for the ignite moment. No text, no deps - just light in the dark.
 */
export function CandleFlame({ boost = 0, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const boostRef = useRef(boost);
  boostRef.current = boost;

  useEffect(() => {
    const maybeCanvas = canvasRef.current;
    if (!maybeCanvas) return;
    const maybeCtx = maybeCanvas.getContext("2d");
    if (!maybeCtx) return;
    const cv: HTMLCanvasElement = maybeCanvas;
    const c: CanvasRenderingContext2D = maybeCtx;

    let raf = 0;
    let t = Math.random() * 1000;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const sparks = Array.from({ length: 14 }, () => ({
      x: 0,
      y: 0,
      life: Math.random(),
      seed: Math.random() * 6.28,
    }));

    function resize() {
      cv.width = Math.max(1, cv.clientWidth) * dpr;
      cv.height = Math.max(1, cv.clientHeight) * dpr;
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(cv);

    // Smooth, organic flicker from a few detuned sines.
    function flicker(time: number) {
      return (
        0.55 +
        0.22 * Math.sin(time * 9.1) +
        0.13 * Math.sin(time * 17.7 + 1.3) +
        0.1 * Math.sin(time * 27.3 + 2.1)
      );
    }

    function drawFlame(
      cx: number,
      bottomY: number,
      topY: number,
      halfW: number,
      sway: number,
    ) {
      const span = bottomY - topY;
      c.beginPath();
      c.moveTo(cx, bottomY);
      c.bezierCurveTo(
        cx - halfW,
        bottomY - span * 0.12,
        cx - halfW * 0.5 + sway * 0.4,
        topY + span * 0.5,
        cx + sway,
        topY,
      );
      c.bezierCurveTo(
        cx + halfW * 0.5 + sway * 0.4,
        topY + span * 0.5,
        cx + halfW,
        bottomY - span * 0.12,
        cx,
        bottomY,
      );
      c.closePath();
    }

    function draw() {
      t += 0.016;
      const w = cv.width;
      const h = cv.height;
      const S = Math.min(w, h);
      const cx = w / 2;
      const cy = h / 2;

      const fl = flicker(t);
      const b = Math.max(0, Math.min(1.6, boostRef.current));
      const energy = Math.min(1.4, 0.85 + (fl - 0.55) * 0.6 + b * 0.6);
      const sway = Math.sin(t * 3.3) * S * 0.012 + Math.sin(t * 7.9) * S * 0.006;

      c.clearRect(0, 0, w, h);

      // Flame geometry (teardrop centered on cx/cy).
      const flameH = S * (0.34 + 0.06 * fl) * (1 + b * 0.5);
      const halfW = S * (0.085 + 0.012 * fl) * (1 + b * 0.25);
      const bottomY = cy + flameH * 0.42;
      const topY = bottomY - flameH;

      c.globalCompositeOperation = "lighter";

      // 1) Ambient room glow.
      const halo = c.createRadialGradient(cx, cy, 0, cx, cy, S * (0.55 + 0.15 * b));
      halo.addColorStop(0, `rgba(245, 181, 133, ${0.22 * energy})`);
      halo.addColorStop(0.4, `rgba(216, 169, 117, ${0.1 * energy})`);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = halo;
      c.fillRect(0, 0, w, h);

      // 2) Outer flame body - deep gold -> warm tip.
      drawFlame(cx, bottomY, topY, halfW, sway);
      const body = c.createLinearGradient(0, bottomY, 0, topY);
      body.addColorStop(0, `rgba(166, 149, 87, ${0.85 * energy})`);
      body.addColorStop(0.45, `rgba(216, 169, 117, ${0.92 * energy})`);
      body.addColorStop(0.8, `rgba(245, 181, 133, ${0.8 * energy})`);
      body.addColorStop(1, "rgba(245, 181, 133, 0)");
      c.fillStyle = body;
      c.shadowBlur = S * 0.12 * energy;
      c.shadowColor = "rgba(236, 177, 129, 0.9)";
      c.fill();

      // 3) Hot inner core - bright peach/white.
      const coreBottom = bottomY - flameH * 0.06;
      const coreTop = coreBottom - flameH * 0.62;
      drawFlame(cx, coreBottom, coreTop, halfW * 0.5, sway * 0.7);
      const core = c.createLinearGradient(0, coreBottom, 0, coreTop);
      core.addColorStop(0, `rgba(255, 232, 194, ${0.95 * energy})`);
      core.addColorStop(0.7, `rgba(255, 244, 224, ${0.9 * energy})`);
      core.addColorStop(1, "rgba(255, 255, 255, 0)");
      c.fillStyle = core;
      c.shadowBlur = S * 0.06 * energy;
      c.shadowColor = "rgba(255, 244, 224, 1)";
      c.fill();
      c.shadowBlur = 0;

      // 4) Sparks drifting up from the flame tip.
      for (const s of sparks) {
        s.life += 0.006 + 0.004 * b;
        if (s.life > 1) {
          s.life = 0;
          s.seed = Math.random() * 6.28;
        }
        const px = cx + sway + Math.sin(s.seed + s.life * 6) * S * 0.03 * s.life;
        const py = topY - s.life * S * 0.22;
        const a = (1 - s.life) * 0.6 * energy;
        const r = Math.max(0.5, S * 0.006 * (1 - s.life));
        c.beginPath();
        c.arc(px, py, r * dpr, 0, Math.PI * 2);
        c.fillStyle = `rgba(245, 200, 150, ${a})`;
        c.fill();
      }

      c.globalCompositeOperation = "source-over";

      // 5) Wick + ember (drawn solid, below the flame).
      const wickTop = bottomY - flameH * 0.04;
      c.strokeStyle = "rgba(20, 16, 10, 0.9)";
      c.lineWidth = Math.max(1.2, S * 0.006) * dpr;
      c.beginPath();
      c.moveTo(cx, bottomY + flameH * 0.16);
      c.lineTo(cx + sway * 0.4, wickTop);
      c.stroke();
      c.beginPath();
      c.arc(cx + sway * 0.4, wickTop, S * 0.01, 0, Math.PI * 2);
      const ember = c.createRadialGradient(
        cx + sway * 0.4,
        wickTop,
        0,
        cx + sway * 0.4,
        wickTop,
        S * 0.02,
      );
      ember.addColorStop(0, `rgba(255, 200, 120, ${0.9 * energy})`);
      ember.addColorStop(1, "rgba(255, 120, 40, 0)");
      c.fillStyle = ember;
      c.fill();

      raf = requestAnimationFrame(draw);
    }
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
