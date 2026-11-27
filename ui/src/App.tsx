/** HUD do Nox. Estado por polling: o backend é um servidor stdlib, não tem
 *  websockets, e o original já fazia o mesmo em `nox/ui/index.html`. */

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { TopBar } from "./components/TopBar";
import { Spectrum } from "./components/Spectrum";
import { ConversationLog } from "./components/ConversationLog";
import { Approvals } from "./components/Approvals";
import { MemoryPanel } from "./components/MemoryPanel";
import { WhatsAppPanel } from "./components/WhatsAppPanel";
import { Composer } from "./components/Composer";
import { Settings } from "./screens/Settings";
import { Setup } from "./screens/Setup";
import { useVoice } from "./voice";
import type {
  Approval,
  Fact,
  SettingsPayload,
  Turn,
  WhatsAppState,
} from "./types";

const STATE_MS = 900;
const MEMORY_MS = 2500;

export function App() {
  const [serverStatus, setServerStatus] = useState("parado");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  // A voz vive enquanto o HUD estiver aberto. Não há botão para a ligar:
  // o servidor é que decide, pela transcrição, se a fala era para o Nox.
  const [voiceOn, setVoiceOn] = useState(true);
  const [voiceStatus, setVoiceStatus] = useState("a ligar");
  const [voiceSpeaking, setVoiceSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [voiceDenied, setVoiceDenied] = useState(false);
  const [emergency, setEmergency] = useState(false);
  const [fullAccess, setFullAccess] = useState(false);
  const [whatsapp, setWhatsapp] = useState<WhatsAppState | null>(null);
  const [whatsappBusy, setWhatsappBusy] = useState(false);
  const [setup, setSetup] = useState<SettingsPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const state = await api.state();
      setEmergency(Boolean(state.emergency));
      setTurns(state.turns);
      setApprovals(state.approvals ?? []);
      setFullAccess(Boolean(state.full_access));
      if (state.setup_required) {
        // Primeiro arranque: sem chave não há HUD, há configuração. O
        // `current ?? payload` evita recarregar o formulário a cada polling
        // e apagar o que o utilizador já escreveu.
        void api
          .settings()
          .then((payload) => setSetup((current) => current ?? payload))
          .catch(() => undefined);
      }
      setServerStatus(state.status);
    } catch {
      setServerStatus("sem ligação");
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

  useVoice({
    active: voiceOn,
    onStatus: (status) => {
      setVoiceStatus(status);
      // Um estado normal (a ouvir ou a espera da palavra) limpa o aviso de
      // microfone bloqueado; so um erro o volta a mostrar.
      if (status === "a ouvir" || status.startsWith("diz «")) {
        setVoiceDenied(false);
        setVoiceError("");
      }
    },
    onSpeaking: setVoiceSpeaking,
    onTurn: () => {
      void refresh();
      void refreshMemory();
    },
    onError: (message, permissionDenied) => {
      setVoiceError(message);
      if (permissionDenied) setVoiceDenied(true);
    },
    onStop: () => {
      setVoiceOn(false);
      setVoiceStatus("parado");
      setVoiceSpeaking(false);
    },
  });

  const retryVoice = useCallback(() => {
    setVoiceError("");
    setVoiceDenied(false);
    setVoiceStatus("a ligar");
    setVoiceOn(true);
    void refresh();
  }, [refresh]);

  const refreshWhatsApp = useCallback(async () => {
    try {
      setWhatsapp(await api.whatsapp());
    } catch {
      // O modo é opcional; uma falha aqui não pode parar o HUD.
    }
  }, []);

  const toggleWhatsApp = useCallback(async (on: boolean) => {
    setWhatsappBusy(true);
    try {
      setWhatsapp(await api.setWhatsApp(on));
    } catch {
      // O próximo polling repõe o estado real.
    } finally {
      setWhatsappBusy(false);
    }
  }, []);

  const selectWhatsAppGroup = useCallback(async (jid: string) => {
    setWhatsappBusy(true);
    try {
      setWhatsapp(await api.selectWhatsAppGroup(jid));
    } catch {
      // A lista pode ter mudado; o próximo polling mostra o estado.
    } finally {
      setWhatsappBusy(false);
    }
  }, []);

  const setWhatsAppMode = useCallback(async (mode: string) => {
    setWhatsappBusy(true);
    try {
      setWhatsapp(await api.setWhatsAppMode(mode));
    } catch {
      // O próximo polling repõe o estado real.
    } finally {
      setWhatsappBusy(false);
    }
  }, []);

  const refreshWhatsAppGroups = useCallback(async () => {
    setWhatsappBusy(true);
    try {
      setWhatsapp(await api.refreshWhatsAppGroups());
    } catch {
      // Sem rede, a lista anterior fica.
    } finally {
      setWhatsappBusy(false);
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

  const status = voiceOn ? voiceStatus : serverStatus;

  useEffect(() => {
    document.body.dataset.status = status;
  }, [status]);

  useEffect(() => {
    const stateId = setInterval(() => void refresh(), STATE_MS);
    const memoryId = setInterval(() => void refreshMemory(), MEMORY_MS);
    const whatsappId = setInterval(() => void refreshWhatsApp(), 1600);
    // A primeira leitura sai num timer: o efeito só monta os relógios, e o
    // `setState` acontece na resposta, não durante o render.
    const kick = setTimeout(() => {
      void refresh();
      void refreshMemory();
      void refreshWhatsApp();
    }, 0);
    return () => {
      clearTimeout(kick);
      clearInterval(stateId);
      clearInterval(memoryId);
      clearInterval(whatsappId);
    };
  }, [refresh, refreshMemory, refreshWhatsApp]);

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
      <main className="stage">
        <Spectrum
          onStatus={setServerStatus}
          speaking={voiceSpeaking}
          clientVoice={voiceOn}
        />
        <aside className="side">
          <div className="panel-head">Conversa</div>
          <ConversationLog turns={turns} />
          <Approvals items={approvals} onDecided={() => void refresh()} />
          <WhatsAppPanel
            state={whatsapp}
            busy={whatsappBusy}
            onToggle={(on) => void toggleWhatsApp(on)}
            onSelect={(jid) => void selectWhatsAppGroup(jid)}
            onMode={(mode) => void setWhatsAppMode(mode)}
            onRefresh={() => void refreshWhatsAppGroups()}
          />
          <MemoryPanel facts={facts} onChanged={() => void refreshMemory()} />
        </aside>
      </main>
      {settingsOpen && (
        <Settings
          onClose={() => setSettingsOpen(false)}
          onSaved={() => {
            void refresh();
          }}
        />
      )}
      <Composer
        voiceError={voiceError}
        voiceDenied={voiceDenied}
        onSent={() => {
          void refresh();
          void refreshMemory();
        }}
        onRetry={retryVoice}
      />
    </div>
  );
}
