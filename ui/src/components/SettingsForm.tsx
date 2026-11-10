/** Formulário partilhado pelo arranque e pelas definições.
 *
 *  A regra que isto serve: ninguém edita `.env` nem `config.yaml` à mão. O que
 *  se vê aqui é o que o backend guarda em `%LOCALAPPDATA%\HeyNox`.
 */

import { useEffect, useState } from "react";
import { api } from "../api";
import type { Device, Provider, SecretStatus, SettingsDraft, SettingsValues } from "../types";

interface Props {
  providers: Provider[];
  values: SettingsValues;
  secrets: Record<string, SecretStatus>;
  onChange: (draft: SettingsDraft) => void;
  draft: SettingsDraft;
}

export function SettingsForm({ providers, values, secrets, draft, onChange }: Props) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState("");
  const [testOk, setTestOk] = useState(false);

  useEffect(() => {
    let alive = true;
    void api
      .devices()
      .then((data) => {
        if (alive) setDevices(data.devices);
      })
      .catch(() => {
        if (alive) setDevices([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const provider = providers.find((item) => item.id === (draft.provider ?? values.provider));

  function pickProvider(id: string) {
    const found = providers.find((item) => item.id === id);
    if (!found) {
      onChange({ ...draft, provider: id });
      return;
    }
    onChange({
      ...draft,
      provider: found.id,
      base_url: found.base_url,
      api_format: found.api_format,
      model: found.model,
    });
  }

  async function runTest() {
    setTesting(true);
    setTestMessage("");
    try {
      const result = await api.testKey({
        provider: draft.provider ?? values.provider,
        base_url: draft.base_url ?? values.base_url,
        api_format: draft.api_format ?? values.api_format,
        model: draft.model ?? values.model,
        api_key: draft.api_key ?? "",
      });
      setTestOk(result.ok);
      setTestMessage(result.message);
    } catch (error) {
      setTestOk(false);
      setTestMessage(error instanceof Error ? error.message : "falhou");
    } finally {
      setTesting(false);
    }
  }

  const keyStatus = secrets[provider?.key_env ?? values.key_env] ?? { set: false, preview: "" };

  return (
    <div className="form">
      <section>
        <h3>Modelo</h3>
        <div className="row">
          <label className="field">
            <span>Fornecedor</span>
            <select
              value={draft.provider ?? values.provider}
              onChange={(event) => pickProvider(event.target.value)}
            >
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
              <option value="custom">Outro (endpoint próprio)</option>
            </select>
          </label>
          <label className="field">
            <span>Modelo</span>
            <input
              value={draft.model ?? values.model}
              onChange={(event) => onChange({ ...draft, model: event.target.value })}
              placeholder="claude-haiku-5-5"
            />
          </label>
        </div>
        <label className="field">
          <span>Endereço da API</span>
          <input
            value={draft.base_url ?? values.base_url}
            onChange={(event) => onChange({ ...draft, base_url: event.target.value })}
            placeholder="https://api.exemplo.com/v1"
          />
        </label>
        <label className="field">
          <span>
            Chave
            {keyStatus.set && <em className="hint"> guardada {keyStatus.preview}</em>}
          </span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={draft.api_key ?? ""}
            onChange={(event) => onChange({ ...draft, api_key: event.target.value })}
            placeholder={keyStatus.set ? "guardada, escreve para substituir" : "cola a chave aqui"}
          />
        </label>
        <div className="row">
          <button type="button" className="ghost" disabled={testing} onClick={() => void runTest()}>
            {testing ? "a testar..." : "Testar chave"}
          </button>
          {testMessage && <span className={testOk ? "ok" : "bad"}>{testMessage}</span>}
        </div>
      </section>

      <section>
        <h3>Voz</h3>
        <div className="row">
          <label className="field">
            <span>Microfone</span>
            <select
              value={draft.input_device ?? values.input_device}
              onChange={(event) => onChange({ ...draft, input_device: event.target.value })}
            >
              <option value="default">O do sistema</option>
              {devices.map((device) => (
                <option key={device.index} value={device.name}>
                  {device.name}
                </option>
              ))}
              {(draft.input_device ?? values.input_device) !== "default" &&
                !devices.some((device) => device.name === (draft.input_device ?? values.input_device)) && (
                  <option value={draft.input_device ?? values.input_device}>
                    {draft.input_device ?? values.input_device} (não está ligado)
                  </option>
                )}
            </select>
          </label>
          <label className="field narrow">
            <span>Palavra de ativação</span>
            <input
              value={draft.wake_word ?? values.wake_word}
              onChange={(event) => onChange({ ...draft, wake_word: event.target.value })}
            />
          </label>
          <label className="field narrow">
            <span>Nome</span>
            <input
              value={draft.name ?? values.name}
              onChange={(event) => onChange({ ...draft, name: event.target.value })}
            />
          </label>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={draft.voice_enabled ?? values.voice_enabled}
            onChange={(event) => onChange({ ...draft, voice_enabled: event.target.checked })}
          />
          <span>Responder em voz alta</span>
        </label>
        <label className="field">
          <span>
            Chave da transcrição na cloud (opcional)
            {secrets.GROQ_API_KEY?.set && <em className="hint"> guardada</em>}
          </span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={draft.groq_key ?? ""}
            onChange={(event) => onChange({ ...draft, groq_key: event.target.value })}
            placeholder="sem isto, a transcrição corre no PC e é mais lenta"
          />
        </label>
      </section>
    </div>
  );
}
