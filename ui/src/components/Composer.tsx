/** Rodapé: escrever ao Nox. A voz arranca sozinha e só responde depois da
 *  wake word; aqui fica apenas a recuperação quando o microfone falha. */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";

interface Props {
  voiceError: string;
  voiceDenied: boolean;
  onSent: () => void;
  onRetry: () => void;
}

export function Composer({ voiceError, voiceDenied, onSent, onRetry }: Props) {
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

  const problem = voiceDenied || voiceError;
  const detail = voiceError || "Autoriza o microfone nas definições e tenta outra vez.";

  return (
    <div className="composer-wrap">
      {problem ? (
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
            <strong>{voiceDenied ? "Microfone bloqueado" : "Voz indisponível"}</strong>
            <span>{detail}</span>
          </div>
          <button type="button" onClick={onRetry}>
            Tentar de novo
          </button>
        </div>
      ) : null}
      <footer className="composer">
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
      </footer>
    </div>
  );
}
