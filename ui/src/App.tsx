/** HUD do Nox. Estado por polling: o backend é um servidor stdlib, não tem
 *  websockets, e o original já fazia o mesmo em `nox/ui/index.html`. */

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { TopBar } from "./components/TopBar";
import { Spectrum } from "./components/Spectrum";
import { ConversationLog } from "./components/ConversationLog";
import { Approvals } from "./components/Approvals";
import { MemoryPanel } from "./components/MemoryPanel";
import { Composer } from "./components/Composer";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";
import type { Approval, Fact, SettingsPayload, Turn, UpdateState } from "./types";

const STATE_MS = 900;
const MEMORY_MS = 2500;

export function App() {
  const [status, setStatus] = useState("parado");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [voice, setVoice] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [emergency, setEmergency] = useState(false);
  const [fullAccess, setFullAccess] = useState(false);
  const [setup, setSetup] = useState<SettingsPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [update, setUpdate] = useState<UpdateState>({
    available: false,
    latest: "",
    current: "",
    can_apply: false,
  });

  const refresh = useCallback(async () => {
    try {
      const state = await api.state();
      setEmergency(Boolean(state.emergency));
      setVoice(state.voice);
      setTurns(state.turns);
      setApprovals(state.approvals ?? []);
      setFullAccess(Boolean(state.full_access));
      setUpdate(state.update ?? { available: false, latest: "", current: "", can_apply: false });
      if (state.setup_required) {
        // Primeiro arranque: sem chave não há HUD, há configuração. O
        // `current ?? payload` evita recarregar o formulário a cada polling
        // e apagar o que o utilizador já escreveu.
        void api
          .settings()
          .then((payload) => setSetup((current) => current ?? payload))
          .catch(() => undefined);
      }
      if (state.voice_error && !state.voice) {
        setStatus("erro na voz");
        setVoiceError(state.voice_error);
      } else {
        setStatus(state.status);
        setVoiceError("");
      }
    } catch {
      setStatus("sem ligação");
    }
  }, []);

  const refreshMemory = useCallback(async () => {
    try {
      const data = await api.memory();
      setFacts(data.facts);
    } catch {
      // Silencioso: a memória não é crítica para a conversa.
    }
  }, []);

  const toggleEmergency = useCallback(async () => {
    try {
      const data = await api.emergency(!emergency);
      setEmergency(Boolean(data.emergency));
    } catch {
      // Sem ligação: o próximo refresh repõe o estado.
    }
    await refresh();
  }, [emergency, refresh]);

  useEffect(() => {
    document.body.dataset.status = status;
  }, [status]);

  useEffect(() => {
    const stateId = setInterval(() => void refresh(), STATE_MS);
    const memoryId = setInterval(() => void refreshMemory(), MEMORY_MS);
    // A primeira leitura sai num timer: o efeito só monta os relógios, e o
    // `setState` acontece na resposta, não durante o render.
    const kick = setTimeout(() => {
      void refresh();
      void refreshMemory();
    }, 0);
    return () => {
      clearTimeout(kick);
      clearInterval(stateId);
      clearInterval(memoryId);
    };
  }, [refresh, refreshMemory]);

  if (setup) {
    return (
      <Setup
        payload={setup}
        onReady={() => {
          setSetup(null);
          void refresh();
        }}
      />
    );
  }

  return (
    <div className="app">
      <TopBar
        status={status}
        emergency={emergency}
        fullAccess={fullAccess}
        onToggleEmergency={() => void toggleEmergency()}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {update.available && (
        <div className="update-bar">
          <span>
            Versão {update.latest} disponível. Estás na {update.current}.
          </span>
          <button type="button" onClick={() => setSettingsOpen(true)}>
            Ver
          </button>
        </div>
      )}
      <main className="stage">
        <Spectrum onStatus={setStatus} />
        <aside className="side">
          <div className="panel-head">Conversa</div>
          <ConversationLog turns={turns} />
          <Approvals items={approvals} onDecided={() => void refresh()} />
          <MemoryPanel facts={facts} onChanged={() => void refreshMemory()} />
        </aside>
      </main>
      {settingsOpen && (
        <Settings
          onClose={() => setSettingsOpen(false)}
          onSaved={() => {
            void refresh();
          }}
          onUpdateApplied={() => setSettingsOpen(false)}
        />
      )}
      <Composer
        voice={voice}
        voiceError={voiceError}
        onSent={() => {
          void refresh();
          void refreshMemory();
        }}
        onVoice={(on) => {
          setVoice(on);
          void refresh();
        }}
      />
    </div>
  );
}
