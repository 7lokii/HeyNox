/** Painel de aprovações. Só aparece quando há um pedido pendente.
 *
 *  A decisão é enviada ao backend e o painel é limpo pelo refresh seguinte: o
 *  pedido pode ter expirado entretanto, e a fonte da verdade é o servidor.
 */

import { useState } from "react";
import { api } from "../api";
import type { Approval } from "../types";

interface Props {
  items: Approval[];
  onDecided: () => void;
}

export function Approvals({ items, onDecided }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  if (items.length === 0) return null;

  const decide = async (id: string, approved: boolean) => {
    setBusy(id);
    try {
      await api.decide(id, approved);
    } catch {
      // Pedido expirado ou já decidido: o refresh limpa o painel.
    } finally {
      setBusy(null);
      onDecided();
    }
  };

  return (
    <div className="approvals">
      <div className="approvals-head">
        <span>Aprovação necessária</span>
        <span className="count">{items.length}</span>
      </div>
      {items.map((item) => (
        <div className="approval" key={item.id}>
          <div className="approval-title">{item.summary}</div>
          <pre className="approval-detail">{item.detail || item.action}</pre>
          <div className="approval-actions">
            <button
              type="button"
              className="approve"
              disabled={busy === item.id}
              onClick={() => void decide(item.id, true)}
            >
              Aprovar
            </button>
            <button
              type="button"
              className="reject"
              disabled={busy === item.id}
              onClick={() => void decide(item.id, false)}
            >
              Recusar
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
