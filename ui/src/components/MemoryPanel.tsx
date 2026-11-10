/** Memória de longo prazo: o que o Nox sabe, com o botão para esquecer. */

import { api } from "../api";
import type { Fact } from "../types";

interface Props {
  facts: Fact[];
  onChanged: () => void;
}

export function MemoryPanel({ facts, onChanged }: Props) {
  const forget = async (text: string) => {
    try {
      await api.forget(text);
    } catch {
      // A memória não é crítica para a conversa; o próximo refresh repõe.
    }
    onChanged();
  };

  return (
    <details className="memory">
      <summary>
        Memória <span className="count">{facts.length}</span>
      </summary>
      <ul>
        {facts.length === 0 ? (
          <li className="hint">
            Ainda não sei nada. Diz «chamo-me …» ou «lembra-te que …».
          </li>
        ) : (
          facts.map((fact) => (
            <li key={fact.id}>
              <span className="kind">{fact.kind}</span>
              <span>{fact.text}</span>
              <button type="button" onClick={() => void forget(fact.text)}>
                esquecer
              </button>
            </li>
          ))
        )}
      </ul>
    </details>
  );
}
