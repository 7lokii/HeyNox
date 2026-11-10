/** O reactor: o anel de espectro que desenha o áudio real.
 *
 *  Duas fontes. A saída do Nox (ciano, a crescer para fora) vem de
 *  `/api/levels.levels`; o microfone (verde, a crescer para dentro) vem de
 *  `/api/levels.input`. Nada disto é animação de enfeite: se o Nox está calado,
 *  o anel quase pára.
 */

import { useEffect, useRef } from "react";
import { api } from "../api";

const BANDS = 48;
const POLL_MS = 90;
const TICKS = 72;

interface Props {
  /** O HUD mostra o estado vindo daqui e de `/api/state`. */
  onStatus: (status: string) => void;
}

export function Spectrum({ onStatus }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const target = useRef<number[]>(new Array<number>(BANDS).fill(0));
  const current = useRef<number[]>(new Array<number>(BANDS).fill(0));
  const inputTarget = useRef<number[]>(new Array<number>(BANDS).fill(0));
  const inputCurrent = useRef<number[]>(new Array<number>(BANDS).fill(0));
  const onStatusRef = useRef(onStatus);

  useEffect(() => {
    onStatusRef.current = onStatus;
  }, [onStatus]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let alive = true;
    let frame = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let phase = 0;
    let ratio = window.devicePixelRatio || 1;

    const resize = () => {
      ratio = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const ring = (
      cx: number,
      cy: number,
      radius: number,
      width: number,
      alpha: number,
      dash: number[],
      rotation: number,
    ) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(rotation);
      ctx.beginPath();
      ctx.setLineDash(dash);
      ctx.lineWidth = width;
      ctx.strokeStyle = `rgba(34, 211, 238, ${alpha})`;
      ctx.arc(0, 0, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    };

    const segment = (
      cx: number,
      cy: number,
      angle: number,
      from: number,
      to: number,
      haloColor: string,
      haloAlpha: number,
      haloWidth: number,
      coreColor: string,
      coreAlpha: number,
    ) => {
      const x1 = cx + Math.cos(angle) * from;
      const y1 = cy + Math.sin(angle) * from;
      const x2 = cx + Math.cos(angle) * to;
      const y2 = cy + Math.sin(angle) * to;

      ctx.beginPath();
      ctx.lineCap = "round";
      ctx.strokeStyle = `rgba(${haloColor}, ${haloAlpha})`;
      ctx.lineWidth = haloWidth;
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      ctx.beginPath();
      ctx.strokeStyle = `rgba(${coreColor}, ${coreAlpha})`;
      ctx.lineWidth = 2;
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const radius = Math.min(w, h) * 0.5;
      const base = radius * 0.6;
      phase += 0.006;

      const glow = ctx.createRadialGradient(cx, cy, base * 0.2, cx, cy, radius);
      glow.addColorStop(0, "rgba(34, 211, 238, 0.12)");
      glow.addColorStop(0.55, "rgba(34, 211, 238, 0.04)");
      glow.addColorStop(1, "rgba(4, 7, 13, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fill();

      ring(cx, cy, base * 1.3, 1, 0.1, [2, 10], phase * 0.35);
      ring(cx, cy, base * 1.16, 1, 0.16, [30, 8], -phase * 0.5);
      ring(cx, cy, base * 0.88, 1, 0.14, [], 0);

      ctx.save();
      ctx.translate(cx, cy);
      for (let i = 0; i < TICKS; i += 1) {
        const angle = (i / TICKS) * Math.PI * 2;
        const inner = base * 1.16;
        const outer = inner + (i % 6 === 0 ? 9 : 4);
        ctx.beginPath();
        ctx.strokeStyle = `rgba(34, 211, 238, ${i % 6 === 0 ? 0.16 : 0.06})`;
        ctx.lineWidth = 1;
        ctx.moveTo(Math.cos(angle) * inner, Math.sin(angle) * inner);
        ctx.lineTo(Math.cos(angle) * outer, Math.sin(angle) * outer);
        ctx.stroke();
      }
      ctx.restore();

      const idle = 0.045 + 0.03 * Math.sin(phase * 2.2);
      const speaking = target.current.some((value) => value > 0.02);
      const listening = inputTarget.current.some((value) => value > 0.02);

      // Espelhado no eixo vertical: meia volta mostra o espectro, a outra metade
      // repete-o. É o que dá o desenho simétrico em vez de um gráfico torto.
      for (let i = 0; i < BANDS; i += 1) {
        const band = i < BANDS / 2 ? i : BANDS - 1 - i;
        const value = speaking
          ? current.current[band]
          : idle * (0.6 + 0.4 * Math.sin(phase * 1.6 + band * 0.42));
        const angle = (i / BANDS) * Math.PI * 2 - Math.PI / 2;
        const inner = base * 1.02;
        const length = 5 + value * base * 0.62;
        segment(
          cx,
          cy,
          angle,
          inner,
          inner + length,
          "34, 211, 238",
          0.06 + value * 0.22,
          7,
          "165, 243, 252",
          0.35 + value * 0.65,
        );
      }

      // Anel interior: o microfone. Verde, a crescer para dentro, para não se
      // confundir com a voz do Nox.
      ring(cx, cy, base * 0.8, 1, listening ? 0.22 : 0.08, [], 0);
      for (let i = 0; i < BANDS; i += 1) {
        const band = i < BANDS / 2 ? i : BANDS - 1 - i;
        const value = listening ? inputCurrent.current[band] : 0;
        if (value < 0.01) continue;
        const angle = (i / BANDS) * Math.PI * 2 - Math.PI / 2;
        const outer = base * 0.8;
        segment(
          cx,
          cy,
          angle,
          outer,
          outer - (4 + value * base * 0.34),
          "52, 211, 153",
          0.1 + value * 0.3,
          6,
          "167, 243, 208",
          0.35 + value * 0.65,
        );
      }

      for (let i = 0; i < BANDS; i += 1) {
        current.current[i] += (target.current[i] - current.current[i]) * 0.28;
        inputCurrent.current[i] +=
          (inputTarget.current[i] - inputCurrent.current[i]) * 0.38;
      }

      if (alive) frame = requestAnimationFrame(draw);
    };

    const poll = async () => {
      try {
        const data = await api.levels();
        if (!alive) return;
        if (Array.isArray(data.levels) && data.levels.length === BANDS) {
          target.current = data.levels;
        }
        if (Array.isArray(data.input) && data.input.length === BANDS) {
          inputTarget.current = data.input;
        }
        onStatusRef.current(data.status);
      } catch {
        // Sem ligação: a animação continua com o último valor.
      }
      if (alive) timer = setTimeout(poll, POLL_MS);
    };

    resize();
    window.addEventListener("resize", resize);
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    draw();
    void poll();

    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      if (timer) clearTimeout(timer);
      observer.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <section className="reactor">
      <canvas ref={canvasRef} />
      <div className="core">
        <div className="core-title">NOX</div>
        <div className="core-sub">local · pt-PT</div>
      </div>
    </section>
  );
}
