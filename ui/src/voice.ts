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
const outputListeners = new Set<LevelsListener>();

/** Bandas do microfone local, para o anel azul do reactor. */
export function subscribeVoiceInput(listener: LevelsListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Bandas da voz do Nox a sair neste dispositivo, para o anel vermelho.
 *
 * O serviço não tem placa de som: o MP3 toca aqui. Sem medir esta reprodução
 * o anel vermelho não tinha matéria e ficava a pulsar sozinho.
 */
export function subscribeVoiceOutput(listener: LevelsListener): () => void {
  outputListeners.add(listener);
  return () => {
    outputListeners.delete(listener);
  };
}

function publish(levels: number[]): void {
  for (const listener of listeners) listener(levels);
}

/** Em que passo do ciclo de voz estamos.
 *
 * O reactor pintava-se pelos niveis do microfone, e o ruido ambiente mantinha o
 * anel azul mesmo sem ninguem a falar. A cor segue o passo, nao o som: branco à
 * espera, azul a gravar o pedido, vermelho a falar.
 */
export type VoicePhase = "wait" | "record";

type PhaseListener = (fase: VoicePhase) => void;

const phaseListeners = new Set<PhaseListener>();
let phase: VoicePhase = "wait";

export function getVoicePhase(): VoicePhase {
  return phase;
}

export function subscribeVoicePhase(listener: PhaseListener): () => void {
  listener(phase);
  phaseListeners.add(listener);
  return () => {
    phaseListeners.delete(listener);
  };
}

function publishPhase(fase: VoicePhase): void {
  if (phase === fase) return;
  phase = fase;
  for (const listener of phaseListeners) listener(fase);
}

function publishOutput(levels: number[]): void {
  for (const listener of outputListeners) listener(levels);
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
  private mode: VoicePhase = "wait";
  private speechMs = 0;
  private silenceMs = 0;
  private recordMs = 0;
  private lastPublish = 0;
  private paused = false;
  private busy = false;
  private closed = false;
  private unlock: (() => void) | null = null;

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
      // Um WebView pode criar o contexto suspenso por não haver gesto. Isto
      // não é uma falha do microfone: o primeiro toque no ecrã desbloqueia-o.
      // Não se espera pela promessa: sem gesto ela pode ficar pendente e o
      // arranque nunca chegava a ligar o processador.
      void context.resume().catch(() => undefined);
      context.addEventListener("statechange", () => {
        if (this.closed || context.state !== "running") return;
        if (this.unlock) {
          document.removeEventListener("pointerdown", this.unlock);
          this.unlock = null;
        }
        this.callbacks.onStatus("a ouvir");
      });
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
      if (context.state === "running") {
        this.callbacks.onStatus("a ouvir");
      } else {
        this.showUnlock();
      }
    } catch (error) {
      if (this.closed) return;
      this.fail(voiceMessage(error), isMicrophoneDenied(error));
    }
  }

  stop(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.unlock) {
      document.removeEventListener("pointerdown", this.unlock);
      this.unlock = null;
    }
    this.processor?.disconnect();
    this.source?.disconnect();
    this.analyser?.disconnect();
    this.closeStream();
    if (this.context) {
      void this.context.close().catch(() => undefined);
      this.context = null;
    }
    publish(ZERO_LEVELS);
    publishOutput(ZERO_LEVELS);
    this.callbacks.onSpeaking(false);
    this.callbacks.onStatus("parado");
  }

  private closeStream(): void {
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
  }

  /** O Chrome/WebView bloqueia o áudio até haver um gesto. Não se pede um
   *  botão: o primeiro toque em qualquer sítio do HUD serve. */
  private showUnlock(): void {
    if (this.unlock || this.closed) return;
    this.callbacks.onStatus("toca para ativar a voz");
    const unlock = () => {
      document.removeEventListener("pointerdown", unlock);
      this.unlock = null;
      void this.context
        ?.resume()
        .then(() => {
          if (!this.closed && this.context?.state === "running") {
            this.callbacks.onStatus("a ouvir");
          }
        })
        .catch(() => undefined);
    };
    this.unlock = unlock;
    document.addEventListener("pointerdown", unlock);
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
          publishPhase("record");
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
    publish(bandsFrom(this.frequencies));
  }

  private async finish(): Promise<void> {
    if (this.busy || this.closed) return;
    this.busy = true;
    this.paused = true;
    const chunks = this.chunks;
    const duration = this.recordMs;
    this.mode = "wait";
    publishPhase("wait");
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

    // Não anunciar «a pensar» antes de o servidor confirmar a wake word:
    // o ruído ambiente chega aqui e não pode parecer um pedido. O estado
    // continua «a ouvir» até haver uma resposta para falar.
    try {
      const data = await api.voiceTurn(pcm.buffer);
      if (this.closed) return;
      // O Vosk pode recusar antes de haver transcrição. Nesse caso `text`
      // vem vazio, mas a resposta certa é «diz Nox», não «não ouvi».
      if (data.wake === false) {
        // Numa sala com conversa, voltar a «a ouvir» depois de uma recusa
        // parecia uma ativação. Sem a palavra, o estado fica no pedido.
        this.callbacks.onStatus(data.hint || "diz «Nox» para falar");
        await delay(1100);
        this.resume();
        return;
      }
      if (!data.text) {
        // A ativação pode ser válida mesmo sem transcrição: um "Nox" curto
        // passa no Vosk e o Whisper pode devolver vazio. Nesse caso o servidor
        // manda o pedido seguinte; não é "não ouvi".
        this.callbacks.onStatus(data.hint || "não ouvi");
        await delay(data.hint ? 1100 : 700);
        this.resume();
        return;
      }
      if (!data.answer) {
        this.callbacks.onStatus(data.hint || "não ouvi");
        await delay(data.hint ? 1100 : 700);
        if (!this.closed) this.callbacks.onStatus("a ouvir");
        this.resume();
        return;
      }
      this.callbacks.onTurn();
      if (data.answer) await this.speak(data.answer, data.audio, data.audio_mime);
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
    publishPhase("wait");
    this.speechMs = 0;
    this.silenceMs = 0;
    this.recordMs = 0;
    this.preRoll = [];
    void this.context?.resume().catch(() => undefined);
  }

  private async speak(
    answer: string,
    audio: string,
    mime?: string,
  ): Promise<void> {
    this.callbacks.onSpeaking(true);
    this.callbacks.onStatus("a falar");
    let played = false;
    if (audio) played = await playAudio(audio, mime || "audio/mpeg", this.context);
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

function inAndroidWebView(): boolean {
  return Boolean((window as NoxWindow).NoxSec);
}

export function voiceMessage(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case "NotAllowedError":
        return "microfone bloqueado. Autoriza o microfone para o NoxSec.";
      case "NotFoundError":
        return "não encontrei um microfone neste dispositivo.";
      case "NotReadableError":
        return inAndroidWebView()
          ? "o WebView não abriu o microfone. Autoriza-o no Android e fecha outras apps que o estejam a usar."
          : "o microfone está ocupado por outra app. Fecha-a e tenta de novo.";
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

function base64Blob(value: string, mime = "audio/mpeg"): Blob {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/** Agrupa o analisador em BANDS bandas, a mesma escala do anel. */
function bandsFrom(frequencies: Uint8Array): number[] {
  const step = Math.max(1, Math.floor(frequencies.length / BANDS));
  const levels = new Array<number>(BANDS).fill(0);
  for (let i = 0; i < BANDS; i += 1) {
    let sum = 0;
    for (let j = 0; j < step; j += 1) sum += frequencies[i * step + j] ?? 0;
    levels[i] = sum / step / 255;
  }
  return levels;
}

/** Mede o áudio que está a sair, para o anel vermelho seguir a voz real. */
function meterPlayback(
  audio: HTMLAudioElement,
  context: AudioContext | null,
): { stop: () => void } | null {
  if (!context) return null;
  let source: MediaElementAudioSourceNode;
  let analyser: AnalyserNode;
  try {
    source = context.createMediaElementSource(audio);
    analyser = context.createAnalyser();
  } catch {
    // WebView sem suporte: o som toca, o anel fica na animação de reserva.
    return null;
  }
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.75;
  const frequencies = new Uint8Array(new ArrayBuffer(analyser.frequencyBinCount));
  source.connect(analyser);
  analyser.connect(context.destination);
  void context.resume().catch(() => undefined);

  let frame = 0;
  let last = 0;
  const tick = () => {
    const now = performance.now();
    if (now - last >= 80) {
      last = now;
      analyser.getByteFrequencyData(frequencies);
      publishOutput(bandsFrom(frequencies));
    }
    frame = requestAnimationFrame(tick);
  };
  tick();

  return {
    stop: () => {
      cancelAnimationFrame(frame);
      try {
        source.disconnect();
        analyser.disconnect();
      } catch {
        // Já desligado.
      }
      publishOutput(ZERO_LEVELS);
    },
  };
}

async function playAudio(
  value: string,
  mime: string,
  context: AudioContext | null,
): Promise<boolean> {
  const url = URL.createObjectURL(base64Blob(value, mime));
  try {
    const audio = new Audio(url);
    audio.preload = "auto";
    const meter = meterPlayback(audio, context);
    return await new Promise<boolean>((resolve) => {
      const done = (played: boolean) => {
        meter?.stop();
        resolve(played);
      };
      audio.onended = () => done(true);
      audio.onerror = () => done(false);
      void audio.play().then(
        () => undefined,
        () => done(false),
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
