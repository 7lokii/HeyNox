/** Modo WhatsApp: ligar/desligar, ler o QR e escolher um grupo.
 *
 *  A ligação é por dispositivo ligado (não oficial). O Nox só responde no
 *  grupo escolhido e só a mensagens que começam por @Nox (ou a todas, no modo
 *  "todas"); o backend garante isso, não este componente.
 */

import type { WhatsAppState } from "../types";

const LABELS: Record<string, string> = {
  off: "desligado",
  starting: "a ligar",
  qr: "lê o código",
  connected: "ligado",
  error: "erro",
};

interface Props {
  state: WhatsAppState | null;
  busy: boolean;
  onToggle: (on: boolean) => void;
  onSelect: (jid: string) => void;
  onMode: (mode: string) => void;
  onRefresh: () => void;
}

export function WhatsAppPanel({
  state,
  busy,
  onToggle,
  onSelect,
  onMode,
  onRefresh,
}: Props) {
  const status = state?.status ?? "off";
  const enabled = Boolean(state?.enabled);
  const selected = state?.selected ?? null;
  const groups = state?.groups ?? [];
  const missing = selected !== null && !groups.some((group) => group.jid === selected.jid);
  const mode = state?.mode ?? "mentions";
  const showBody = enabled || status === "error";

  return (
    <section className={`whatsapp ${status}`}>
      <div className="whatsapp-head">
        <span className="whatsapp-title">WhatsApp</span>
        <span className={`whatsapp-state ${status}`}>{LABELS[status] ?? status}</span>
        <label className="switch wa-switch" title={enabled ? "Desligar o modo" : "Ligar o modo"}>
          <input
            type="checkbox"
            checked={enabled}
            disabled={busy}
            onChange={(event) => onToggle(event.target.checked)}
          />
          <span className="wa-switch-label">{enabled ? "ligado" : "desligado"}</span>
        </label>
      </div>

      {showBody && (
        <div className="whatsapp-body">
          {status === "starting" && <p className="muted">a abrir a sessão…</p>}

          {status === "qr" &&
            (state?.qr ? (
              <>
                <img
                  className="whatsapp-qr"
                  src={state.qr}
                  alt="Código QR para ligar o WhatsApp"
                />
                <p className="muted">
                  WhatsApp → Dispositivos ligados → Ligar dispositivo. Este PC fica
                  ligado ao número.
                </p>
              </>
            ) : (
              <p className="muted">a gerar o código…</p>
            ))}

          {status === "connected" && (
            <>
              <p className="muted">
                Ligado{state?.me ? ` como +${state.me}` : ""}. Escolhe o grupo onde
                queres o Nox:
              </p>
              <div className="whatsapp-row">
                <select
                  value={selected?.jid ?? ""}
                  disabled={busy}
                  onChange={(event) => onSelect(event.target.value)}
                >
                  <option value="">— nenhum —</option>
                  {missing && selected && (
                    <option value={selected.jid}>{selected.name} (fora da lista)</option>
                  )}
                  {groups.map((group) => (
                    <option key={group.jid} value={group.jid}>
                      {group.name}
                    </option>
                  ))}
                </select>
                <button type="button" className="ghost" disabled={busy} onClick={onRefresh}>
                  Atualizar
                </button>
              </div>
              <div className="whatsapp-mode">
                <span>responder a</span>
                <button
                  type="button"
                  className={mode === "mentions" ? "active" : ""}
                  aria-pressed={mode === "mentions"}
                  disabled={busy}
                  onClick={() => onMode("mentions")}
                >
                  @Nox
                </button>
                <button
                  type="button"
                  className={mode === "all" ? "active" : ""}
                  aria-pressed={mode === "all"}
                  disabled={busy}
                  onClick={() => onMode("all")}
                >
                  todas
                </button>
              </div>
              {selected ? (
                mode === "all" ? (
                  <p className="muted">Responde a todas as mensagens do grupo escolhido.</p>
                ) : (
                  <p className="muted">
                    Só responde a mensagens que começam por @Nox. As tuas também
                    contam, porque o agente usa o mesmo número.
                  </p>
                )
              ) : (
                <p className="muted">Sem grupo escolhido, não responde a nada.</p>
              )}
              <p className="muted">
                As respostas começam por <strong>Nox:</strong> para o grupo saber que é o
                agente.
              </p>
            </>
          )}

          {status === "connected" && state?.error && <p className="bad">{state.error}</p>}

          {status === "error" && (
            <p className="bad">{state?.error || "não consegui ligar ao WhatsApp"}</p>
          )}

          <p className="whatsapp-warn">
            Ligação não oficial. O WhatsApp pode bloquear o número; se usares o
            principal, é um risco teu. O modo não fala em voz alta nem tem acesso às
            ferramentas.
          </p>
        </div>
      )}
    </section>
  );
}
