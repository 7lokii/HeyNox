/** Configuração inicial. Aparece uma vez, quando ainda não há chave de modelo.
 *
 *  Não tem botão de fechar de propósito: sem chave o Nox não passa de respostas
 *  locais, e um utilizador novo não saberia porque é que ele "não funciona".
 */

import { useState } from "react";
import { api } from "../api";
import { SettingsForm } from "../components/SettingsForm";
import type { SettingsDraft, SettingsPayload } from "../types";

interface Props {
  payload: SettingsPayload;
  onReady: () => void;
}

export function Setup({ payload, onReady }: Props) {
  const [draft, setDraft] = useState<SettingsDraft>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const provider = payload.providers.find(
    (item) => item.id === (draft.provider ?? payload.values.provider),
  );
  const hasKey =
    payload.secrets[provider?.key_env ?? payload.values.key_env]?.set ||
    Boolean(draft.api_key?.trim()) ||
    provider?.needs_key === false;

  async function finish() {
    setSaving(true);
    setError("");
    try {
      await api.saveSettings(draft);
      onReady();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "não consegui gravar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="setup">
      <header className="setup-head">
        <div className="brand">
          <span className="mark">◈</span>NOX
        </div>
        <p>
          Primeira configuração. Fica tudo gravado dentro da app, em{" "}
          <code>{payload.paths.data}</code>. Não há nada para editar à mão.
        </p>
      </header>

      <div className="setup-body">
        <SettingsForm
          providers={payload.providers}
          values={payload.values}
          secrets={payload.secrets}
          draft={draft}
          onChange={setDraft}
        />
      </div>

      <footer className="setup-foot">
        <span className="muted">versão {payload.version}</span>
        {error && <span className="bad">{error}</span>}
        <button
          type="button"
          className="primary"
          disabled={saving || !hasKey}
          title={hasKey ? "Guardar e abrir o Nox" : "Falta a chave do modelo"}
          onClick={() => void finish()}
        >
          {saving ? "a gravar..." : "Guardar e abrir"}
        </button>
      </footer>
    </div>
  );
}
