/** Definições, a qualquer momento. Mesmo formulário do arranque e, à parte,
 *  o acesso total e as atualizações, que são decisões de confiança. */

import { useEffect, useState } from "react";
import { api } from "../api";
import { SettingsForm } from "../components/SettingsForm";
import type { SettingsDraft, SettingsPayload } from "../types";

interface Props {
  onClose: () => void;
  onSaved: () => void;
  onUpdateApplied: () => void;
}

export function Settings({ onClose, onSaved, onUpdateApplied }: Props) {
  const [payload, setPayload] = useState<SettingsPayload | null>(null);
  const [draft, setDraft] = useState<SettingsDraft>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [updateMessage, setUpdateMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const [canApply, setCanApply] = useState(false);
  const [available, setAvailable] = useState("");

  useEffect(() => {
    let alive = true;
    void api
      .settings()
      .then((data) => {
        if (alive) setPayload(data);
      })
      .catch((problem) => {
        if (alive) setError(problem instanceof Error ? problem.message : "falhou a ler");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.saveSettings(draft);
      setDraft({});
      const fresh = await api.settings();
      setPayload(fresh);
      onSaved();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "não consegui gravar");
    } finally {
      setSaving(false);
    }
  }

  async function checkNow() {
    setChecking(true);
    setUpdateMessage("");
    try {
      const result = await api.checkUpdate();
      setCanApply(Boolean(result.can_apply) && Boolean(result.available));
      setAvailable(result.available ? result.latest : "");
      setUpdateMessage(
        result.error
          ? result.error
          : result.available
            ? `Há uma versão nova: ${result.latest}.`
            : `Já estás na versão mais recente (${result.current}).`,
      );
    } catch (problem) {
      setUpdateMessage(problem instanceof Error ? problem.message : "falhou a verificar");
    } finally {
      setChecking(false);
    }
  }

  async function applyNow() {
    setUpdateMessage("a descarregar e a preparar...");
    try {
      const result = await api.applyUpdate();
      if (!result.ok) {
        setUpdateMessage(result.error ?? "não consegui atualizar");
        return;
      }
      setUpdateMessage("A app vai fechar e voltar já na versão nova.");
      onUpdateApplied();
    } catch (problem) {
      setUpdateMessage(problem instanceof Error ? problem.message : "falhou a atualizar");
    }
  }

  function toggleFullAccess(on: boolean) {
    if (on && !window.confirm("Acesso total: o Nox deixa de pedir aprovação para tudo. Continuar?")) {
      return;
    }
    setDraft({ ...draft, full_access: on });
    // Aplica já: um interruptor que só vale depois de "Guardar" engana.
    void api
      .saveSettings({ full_access: on })
      .then(() => {
        onSaved();
        void api.settings().then(setPayload);
      })
      .catch(() => setError("não consegui mudar o acesso total"));
  }

  const fullAccess = draft.full_access ?? payload?.values.full_access ?? false;

  return (
    <div className="overlay" role="dialog" aria-label="Definições">
      <div className="sheet">
        <header className="sheet-head">
          <h2>Definições</h2>
          <button type="button" className="ghost close" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>

        <div className="sheet-body">
          {!payload && !error && <p className="muted">a carregar...</p>}
          {error && <p className="bad">{error}</p>}

          {payload && (
            <>
              <SettingsForm
                providers={payload.providers}
                values={payload.values}
                secrets={payload.secrets}
                draft={draft}
                onChange={setDraft}
              />

              <section className="danger">
                <h3>Acesso total</h3>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={fullAccess}
                    onChange={(event) => toggleFullAccess(event.target.checked)}
                  />
                  <span>
                    Sem pedidos de aprovação. Tudo o que ele fizer fica no registo de auditoria,
                    e o botão <strong>Parar</strong> do topo continua a mandar.
                  </span>
                </label>
              </section>

              <section>
                <h3>Atualizações</h3>
                <p className="muted">
                  versão {payload.version}
                  {available && ` · nova: ${available}`}
                </p>
                <div className="row">
                  <button
                    type="button"
                    className="ghost"
                    disabled={checking}
                    onClick={() => void checkNow()}
                  >
                    {checking ? "a verificar..." : "Verificar agora"}
                  </button>
                  {canApply && (
                    <button type="button" className="primary" onClick={() => void applyNow()}>
                      Atualizar e reiniciar
                    </button>
                  )}
                </div>
                {updateMessage && <p className="muted">{updateMessage}</p>}
              </section>

              <section>
                <h3>Onde está tudo</h3>
                <ul className="paths">
                  <li>
                    <span>dados</span>
                    <code>{payload.paths.data}</code>
                  </li>
                  <li>
                    <span>chaves</span>
                    <code>{payload.paths.env}</code>
                  </li>
                  <li>
                    <span>config</span>
                    <code>{payload.paths.config}</code>
                  </li>
                </ul>
              </section>
            </>
          )}
        </div>

        <footer className="sheet-foot">
          <span className="muted">as chaves ficam nesta máquina, nunca saem daqui</span>
          <button type="button" className="ghost" onClick={onClose}>
            Fechar
          </button>
          <button type="button" className="primary" disabled={saving} onClick={() => void save()}>
            {saving ? "a gravar..." : "Guardar"}
          </button>
        </footer>
      </div>
    </div>
  );
}
