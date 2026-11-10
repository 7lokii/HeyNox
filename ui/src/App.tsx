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
import type { Approval, Fact, Turn } from "./types";

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

  const refresh = useCallback(async () => {
    try {
      const state = await api.state();
      setEmergency(Boolean(state.emergency));
      setVoice(state.voice);
      setTurns(state.turns);
      setApprovals(state.approvals ?? []);
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

  return (
    <div className="app">
      <TopBar
        status={status}
        emergency={emergency}
        onToggleEmergency={() => void toggleEmergency()}
      />
      <main className="stage">
        <Spectrum onStatus={setStatus} />
        <aside className="side">
          <div className="panel-head">Conversa</div>
          <ConversationLog turns={turns} />
          <Approvals items={approvals} onDecided={() => void refresh()} />
          <MemoryPanel facts={facts} onChanged={() => void refreshMemory()} />
        </aside>
      </main>
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
