/** Contratos do backend Python (`nox/ui/server.py` e `nox/ui/state.py`). */

export type TurnRole = "user" | "assistant";

export interface Turn {
  role: TurnRole | string;
  text: string;
  at: number;
}

/** Pedido de aprovação pendente (`nox/safety/approvals.py`). */
export interface Approval {
  id: string;
  summary: string;
  detail?: string;
  action: string;
}

/** Resposta de `GET /api/state`. */
export interface NoxState {
  status: string;
  voice: boolean;
  levels: number[];
  input_levels: number[];
  source: "nox" | "user" | "none" | string;
  turns: Turn[];
  approvals: Approval[];
  emergency: boolean;
  voice_error: string;
}

/** Resposta de `GET /api/levels`. */
export interface LevelsPayload {
  levels: number[];
  input: number[];
  source: string;
  status: string;
}

export interface Fact {
  id: number;
  kind: string;
  text: string;
}

/** Resposta de `GET /api/memory`. */
export interface MemoryPayload {
  facts: Fact[];
}
