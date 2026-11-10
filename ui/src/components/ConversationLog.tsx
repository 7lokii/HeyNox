/** A conversa. Cada turno rola para o fundo quando chega um novo. */

import { useEffect, useRef } from "react";
import type { Turn } from "../types";

interface Props {
  turns: Turn[];
}

export function ConversationLog({ turns }: Props) {
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [turns.length]);

  return (
    <div className="log" ref={logRef}>
      {turns.length === 0 ? (
        <div className="empty">Diz «Hey Nox» ou escreve em baixo.</div>
      ) : (
        turns.map((turn, index) => (
          <div className={`turn ${turn.role}`} key={`${turn.at}-${index}`}>
            <div className="who">{turn.role === "user" ? "tu" : "nox"}</div>
            <div className="bubble">{turn.text}</div>
          </div>
        ))
      )}
    </div>
  );
}
