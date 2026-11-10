/** Topo do HUD: marca, relógio, estado e o botão de emergência. */

import { useEffect, useState } from "react";

interface Props {
  status: string;
  emergency: boolean;
  fullAccess: boolean;
  onToggleEmergency: () => void;
  onOpenSettings: () => void;
}

function useClock(): string {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("pt-PT", { hour12: false }));
  useEffect(() => {
    const id = setInterval(() => {
      setTime(new Date().toLocaleTimeString("pt-PT", { hour12: false }));
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

export function TopBar({ status, emergency, fullAccess, onToggleEmergency, onOpenSettings }: Props) {
  const time = useClock();
  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark">◈</span>NOX
      </div>
      <div className="clock">{time}</div>
      <button
        type="button"
        className="emergency"
        aria-pressed={emergency}
        title="Parar o controlo do PC"
        onClick={onToggleEmergency}
      >
        {emergency ? "Retomar" : "Parar"}
      </button>
      <button
        type="button"
        className="gear"
        onClick={onOpenSettings}
        title="Definições"
        aria-label="Definições"
      >
        ⚙
      </button>
      {fullAccess && (
        <span className="gear-badge" title="Acesso total: nada pede aprovação">
          acesso total
        </span>
      )}
      <div className="status">
        <i />
        <span>{status}</span>
      </div>
    </header>
  );
}
