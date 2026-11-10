/** Topo do HUD: marca, relógio, estado e o botão de emergência. */

import { useEffect, useState } from "react";

interface Props {
  status: string;
  emergency: boolean;
  onToggleEmergency: () => void;
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

export function TopBar({ status, emergency, onToggleEmergency }: Props) {
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
      <div className="status">
        <i />
        <span>{status}</span>
      </div>
    </header>
  );
}
