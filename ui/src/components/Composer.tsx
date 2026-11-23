/** Rodapé: escrever ao Nox e ligar/desligar a voz. */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";

interface Props {
  voice: boolean;
  voiceError: string;
  onSent: () => void;
  onVoice: (on: boolean) => void;
}

export function Composer({ voice, voiceError, onSent, onVoice }: Props) {
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
    <footer className="composer">
      {voiceError ? (
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
  );
}
