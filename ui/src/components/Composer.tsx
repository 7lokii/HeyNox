/** Rodapé: escrever ao Nox e ligar/desligar a voz. */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";

interface Props {
  voice: boolean;
  voiceError: string;
  voiceDenied: boolean;
  onSent: () => void;
  onVoice: (on: boolean) => void;
}

export function Composer({ voice, voiceError, voiceDenied, onSent, onVoice }: Props) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText("");
    setSending(true);
    try {
      await api.say(value);
    } catch (error) {
      console.error(error);
    } finally {
      setSending(false);
      onSent();
    }
  };

  const toggleVoice = () => {
    onVoice(!voice);
  };

  return (
    <div className="composer-wrap">
      {voiceDenied ? (
        <div className="mic-permissao" role="alert">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 11.7 5.2M19 11a7 7 0 0 1-.9 3.4M12 18v3M8 21h8M3 3l18 18" />
          </svg>
          <div className="mic-permissao-texto">
            <strong>Microfone bloqueado</strong>
            <span>Autoriza o microfone nas definições e tenta outra vez.</span>
          </div>
          <button type="button" onClick={() => onVoice(true)} disabled={voice}>
            {voice ? "A pedir…" : "Tentar de novo"}
          </button>
        </div>
      ) : null}
      <footer className="composer">
        {!voiceDenied && voiceError ? (
          <p className="voice-erro" role="status">
            {voiceError}
          </p>
        ) : null}
        <form onSubmit={submit}>
          <input
            type="text"
            autoComplete="off"
            placeholder="Escreve ao Nox…"
            autoFocus
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button className="primary" type="submit" disabled={sending}>
            Enviar
          </button>
        </form>
        <button
          type="button"
          className="voice"
          aria-pressed={voice}
          title={voiceError}
          onClick={toggleVoice}
        >
          {voice ? "Parar" : "Ouvir"}
        </button>
      </footer>
    </div>
  );
}
