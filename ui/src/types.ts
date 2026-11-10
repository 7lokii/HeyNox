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
  setup_required: boolean;
  full_access: boolean;
  update: UpdateState;
}

/** Um fornecedor de modelo, com o que o formulário precisa de pré-preencher. */
export interface Provider {
  id: string;
  label: string;
  base_url: string;
  api_format: string;
  model: string;
  key_env: string;
  needs_key: boolean;
}

/** Estado de uma chave: existe e um rabo mascarado. O valor nunca vem. */
export interface SecretStatus {
  set: boolean;
  preview: string;
}

export interface SettingsValues {
  name: string;
  wake_word: string;
  voice_enabled: boolean;
  provider: string;
  api_format: string;
  base_url: string;
  model: string;
  key_env: string;
  input_device: string;
  input_fallback: string;
  full_access: boolean;
  update_enabled: boolean;
  update_manifest_url: string;
  update_check_hours: number;
}

/** Resposta de `GET /api/settings`. */
export interface SettingsPayload {
  providers: Provider[];
  values: SettingsValues;
  secrets: Record<string, SecretStatus>;
  setup_required: boolean;
  version: string;
  paths: { data: string; config: string; env: string };
}

export interface Device {
  index: number;
  name: string;
}

/** O que o formulário envia. Chaves vazias querem dizer "não mexer". */
export interface SettingsDraft {
  name?: string;
  wake_word?: string;
  voice_enabled?: boolean;
  provider?: string;
  base_url?: string;
  api_format?: string;
  model?: string;
  api_key?: string;
  groq_key?: string;
  clear_api_key?: boolean;
  input_device?: string;
  full_access?: boolean;
  update_enabled?: boolean;
  update_manifest_url?: string;
  update_check_hours?: number;
}

/** Pedaço de `GET /api/state` e `GET /api/update`. */
export interface UpdateState {
  available: boolean;
  latest: string;
  current: string;
  can_apply: boolean;
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
