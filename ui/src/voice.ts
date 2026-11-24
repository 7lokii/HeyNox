/** Voz do HUD: o microfone é o do dispositivo que abriu a página.
 *
 * O HeyNox no homelab não tem placa de som. Em vez de tentar abrir um
 * microfone no servidor, o browser grava PCM 16 kHz, envia um turno e toca o
 * MP3 que volta. O WebView da APK pede a permissão Android pela ponte `NoxSec`
 * antes de chamar `getUserMedia`.
 */

import { useEffect, useRef } from "react";
import { api } from "./api";

const BANDS = 48;
const TARGET_RATE = 16000;
const START_RMS = 0.018;
const START_MS = 160;
const SILENCE_MS = 850;
const MIN_MS = 350;
const MAX_MS = 20000;
const PRE_ROLL = 4;
const ZERO_LEVELS = new Array<number>(BANDS).fill(0);

type LevelsListener = (levels: number[]) => void;

const listeners = new Set<LevelsListener>();

/** Bandas do microfone local, para o anel azul do reactor. */
export function subscribeVoiceInput(listener: LevelsListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function publish(levels: number[]): void {
  for (const listener of listeners) listener(levels);
}

interface VoiceOptions {
  active: boolean;
  onStatus: (status: string) => void;
  onSpeaking: (speaking: boolean) => void;
  onTurn: () => void;
  onError: (message: string, permissionDenied: boolean) => void;
  onStop: () => void;
}

interface MicrophoneBridge {
  postMessage(message: string): void;
}

interface NoxWindow extends Window {
  NoxSec?: MicrophoneBridge;
  __noxsecMic?: (granted: boolean) => void;
}

interface Callbacks {
  onStatus: (status: string) => void;
  onSpeaking: (speaking: boolean) => void;
  onTurn: () => void;
  onError: (message: string, permissionDenied: boolean) => void;
  onStop: () => void;
}

/** Liga e desliga a voz quando `active` muda; o resto vive na sessão. */
export function useVoice(options: VoiceOptions): void {
  const callbacks = useRef<Callbacks>(options);

  useEffect(() => {
    callbacks.current = options;
  }, [options]);

  useEffect(() => {
    if (!options.active) return;
    const session = new VoiceSession({
      onStatus: (status) => callbacks.current.onStatus(status),
      onSpeaking: (speaking) => callbacks.current.onSpeaking(speaking),
      onTurn: () => callbacks.current.onTurn(),
      onError: (message, permissionDenied) =>
        callbacks.current.onError(message, permissionDenied),
      onStop: () => callbacks.current.onStop(),
    });
    void session.start();
    return () => session.stop();
  }, [options.active]);
}

class VoiceSession {
  private readonly callbacks: Callbacks;
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private analyser: AnalyserNode | null = null;
  private frequencies: Uint8Array<ArrayBuffer> | null = null;
  private chunks: Float32Array[] = [];
  private preRoll: Float32Array[] = [];
  private mode: "wait" | "record" = "wait";
  private speechMs = 0;
  private silenceMs = 0;
  private recordMs = 0;
  private lastPublish = 0;
  private paused = false;
  private busy = false;
  private closed = false;

  constructor(callbacks: Callbacks) {
    this.callbacks = callbacks;
  }

  async start(): Promise<void> {
    try {
      await ensureMicrophone();
      if (this.closed) return;
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("este WebView não expõe o microfone. Atualiza a app.");
      }
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      if (this.closed) {
        this.closeStream();
        return;
      }

      const context = new AudioContext();
      this.context = context;
      await context.resume();
      this.source = context.createMediaStreamSource(this.stream);
      this.analyser = context.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.75;
      this.frequencies = new Uint8Array(new ArrayBuffer(this.analyser.frequencyBinCount));
      this.source.connect(this.analyser);

      // ScriptProcessor é antigo, mas é o que existe em todos os WebViews.
      // Ligar ao destino é obrigatório para o callback disparar no Chrome.
      this.processor = context.createScriptProcessor(2048, 1, 1);
      this.processor.onaudioprocess = (event) => this.onAudio(event);
      this.source.connect(this.processor);
      this.processor.connect(context.destination);
      this.callbacks.onStatus("a ouvir");
    } catch (error) {
      if (this.closed) return;
      this.fail(voiceMessage(error), isMicrophoneDenied(error));
    }
  }

  stop(): void {
    if (this.closed) return;
    this.closed = true;
    this.processor?.disconnect();
    this.source?.disconnect();
    this.analyser?.disconnect();
    this.closeStream();
    if (this.context) {
      void this.context.close().catch(() => undefined);
      this.context = null;
    }
    publish(ZERO_LEVELS);
    this.callbacks.onSpeaking(false);
    this.callbacks.onStatus("parado");
  }

  private closeStream(): void {
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
  }

  private fail(message: string, permissionDenied: boolean): void {
    this.callbacks.onError(message, permissionDenied);
    this.callbacks.onStatus("parado");
    this.stop();
    this.callbacks.onStop();
  }

  private onAudio(event: AudioProcessingEvent): void {
    const input = event.inputBuffer.getChannelData(0);
    const block = new Float32Array(input);
    const rms = Math.sqrt(
      block.reduce((sum, value) => sum + value * value, 0) / Math.max(1, block.length),
    );
    this.publishLevels();
    if (this.paused || this.closed) return;

    const blockMs = (block.length / (this.context?.sampleRate ?? TARGET_RATE)) * 1000;
    if (this.mode === "wait") {
      this.preRoll.push(block);
      if (this.preRoll.length > PRE_ROLL) this.preRoll.shift();
      if (rms >= START_RMS) {
        this.speechMs += blockMs;
        if (this.speechMs >= START_MS) {
          this.mode = "record";
          this.chunks = [...this.preRoll];
          this.preRoll = [];
          this.recordMs = this.chunks.reduce(
            (sum, chunk) => sum + (chunk.length / (this.context?.sampleRate ?? TARGET_RATE)) * 1000,
            0,
          );
          this.silenceMs = 0;
        }
      } else {
        this.speechMs = Math.max(0, this.speechMs - blockMs);
      }
      return;
    }

    this.chunks.push(block);
    this.recordMs += blockMs;
    if (rms >= START_RMS) {
      this.silenceMs = 0;
    } else {
      this.silenceMs += blockMs;
    }
    if (this.recordMs >= MAX_MS || (this.silenceMs >= SILENCE_MS && this.recordMs >= MIN_MS)) {
      void this.finish();
    }
  }

  private publishLevels(): void {
    if (!this.analyser || !this.frequencies) return;
    const now = performance.now();
    if (now - this.lastPublish < 80) return;
    this.lastPublish = now;
    this.analyser.getByteFrequencyData(this.frequencies);
    const step = Math.max(1, Math.floor(this.frequencies.length / BANDS));
    const levels = new Array<number>(BANDS).fill(0);
    for (let i = 0; i < BANDS; i += 1) {
      let sum = 0;
      for (let j = 0; j < step; j += 1) sum += this.frequencies[i * step + j] ?? 0;
      levels[i] = sum / step / 255;
    }
    publish(levels);
  }

  private async finish(): Promise<void> {
    if (this.busy || this.closed) return;
    this.busy = true;
    this.paused = true;
    const chunks = this.chunks;
    const duration = this.recordMs;
    this.mode = "wait";
    this.chunks = [];
    this.preRoll = [];
    this.speechMs = 0;
    this.silenceMs = 0;
    this.recordMs = 0;
    publish(ZERO_LEVELS);

    if (duration < MIN_MS) {
      this.resume();
      return;
    }
    const pcm = encodePcm(chunks, this.context?.sampleRate ?? TARGET_RATE);
    if (pcm.byteLength < 3200) {
      this.resume();
      return;
    }

    this.callbacks.onStatus("a pensar");
    try {
      const data = await api.voiceTurn(pcm.buffer);
      if (this.closed) return;
      if (!data.text) {
        this.callbacks.onStatus("não ouvi");
        await delay(700);
        this.resume();
        return;
      }
      this.callbacks.onTurn();
      if (data.answer) await this.speak(data.answer, data.audio);
      if (!this.closed) {
        this.callbacks.onStatus("a ouvir");
        this.resume();
      }
    } catch (error) {
      if (this.closed) return;
      this.callbacks.onError(voiceMessage(error), false);
      this.callbacks.onStatus("a ouvir");
      await delay(900);
      this.resume();
    } finally {
      this.busy = false;
    }
  }

  private resume(): void {
    if (this.closed) return;
    this.paused = false;
    this.busy = false;
    this.mode = "wait";
    this.speechMs = 0;
    this.silenceMs = 0;
    this.recordMs = 0;
    this.preRoll = [];
    void this.context?.resume();
  }

  private async speak(answer: string, audio: string): Promise<void> {
    this.callbacks.onSpeaking(true);
    this.callbacks.onStatus("a falar");
    let played = false;
    if (audio) played = await playMp3(audio);
    if (!played && !this.closed) await speakLocally(answer);
    this.callbacks.onSpeaking(false);
  }
}

async function ensureMicrophone(): Promise<void> {
  const target = window as NoxWindow;
  if (!target.NoxSec) return;
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      delete target.__noxsecMic;
      reject(new Error("o Android não respondeu ao pedido de microfone."));
    }, 60000);
    target.__noxsecMic = (granted: boolean) => {
      window.clearTimeout(timer);
      delete target.__noxsecMic;
      if (granted) resolve();
      else reject(new Error("sem permissão para o microfone. Autoriza-o nas definições da app."));
    };
    target.NoxSec?.postMessage("microfone");
  });
}

/** A recusa veio da permissão, não da rede nem do aparelho. */
export function isMicrophoneDenied(error: unknown): boolean {
  if (error instanceof DOMException) {
    return (
      error.name === "NotAllowedError" ||
      error.name === "PermissionDeniedError" ||
      error.name === "SecurityError"
    );
  }
  if (error instanceof Error) {
    return /sem permissão|permission denied/i.test(error.message);
  }
  return false;
}

export function voiceMessage(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case "NotAllowedError":
        return "microfone bloqueado. Autoriza o microfone para o NoxSec.";
      case "NotFoundError":
        return "não encontrei um microfone neste dispositivo.";
      case "NotReadableError":
        return "o microfone está ocupado por outra app.";
      case "OverconstrainedError":
        return "o microfone não aceitou as definições pedidas.";
      default:
        return error.message || "não consegui abrir o microfone.";
    }
  }
  if (error instanceof Error) {
    const text = error.message.trim();
    try {
      const parsed = JSON.parse(text) as { error?: string; detail?: string };
      return parsed.error || parsed.detail || text;
    } catch {
      return text || "não consegui ligar a voz.";
    }
  }
  return "não consegui ligar a voz.";
}

function encodePcm(chunks: Float32Array[], from: number): Int16Array<ArrayBuffer> {
  let total = 0;
  for (const chunk of chunks) total += chunk.length;
  if (!total) return new Int16Array(0);
  const samples = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    samples.set(chunk, offset);
    offset += chunk.length;
  }
  const ratio = from / TARGET_RATE;
  const length = Math.max(1, Math.floor(samples.length / ratio));
  const pcm = new Int16Array(new ArrayBuffer(length * 2));
  for (let i = 0; i < length; i += 1) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, samples.length - 1);
    const value = samples[left] + (samples[right] - samples[left]) * (position - left);
    pcm[i] = Math.max(-1, Math.min(1, value)) * 0x7fff;
  }
  return pcm;
}

function base64Blob(value: string): Blob {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: "audio/mpeg" });
}

async function playMp3(value: string): Promise<boolean> {
  const url = URL.createObjectURL(base64Blob(value));
  try {
    const audio = new Audio(url);
    audio.preload = "auto";
    return await new Promise<boolean>((resolve) => {
      audio.onended = () => resolve(true);
      audio.onerror = () => resolve(false);
      void audio.play().then(
        () => undefined,
        () => resolve(false),
      );
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function speakLocally(text: string): Promise<void> {
  if (!("speechSynthesis" in window)) {
    await delay(Math.min(4000, 700 + text.length * 35));
    return;
  }
  await new Promise<void>((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "pt-PT";
    const timer = window.setTimeout(resolve, Math.max(1500, text.length * 80));
    utterance.onend = () => {
      window.clearTimeout(timer);
      resolve();
    };
    utterance.onerror = () => {
      window.clearTimeout(timer);
      resolve();
    };
    window.speechSynthesis.speak(utterance);
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
