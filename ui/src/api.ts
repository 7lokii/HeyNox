/** Cliente do backend do Nox. Usa caminhos relativos ao documento para o mesmo
 *  HUD funcionar em `/` (local) e em `/heynox/` (proxy autenticado do NoxSec). */

import type {
  Device,
  LevelsPayload,
  MemoryPayload,
  NoxState,
  SettingsDraft,
  SettingsPayload,
  WhatsAppState,
} from "./types";

const root = new URL("./", document.baseURI);

function endpoint(path: string): string {
  return new URL(path.replace(/^\/+/, ""), root).toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), init);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as T;
}

function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  state: () => request<NoxState>("api/state"),
  levels: () => request<LevelsPayload>("api/levels"),
  memory: () => request<MemoryPayload>("api/memory"),
  say: (text: string) => request<{ answer: string }>("api/say", post({ text })),
  voice: (on: boolean) => request<{ voice: boolean }>("api/voice", post({ on })),
  forget: (pattern: string) =>
    request<{ removed: number }>("api/memory/forget", post({ pattern })),
  decide: (id: string, approved: boolean) =>
    request<{ decided: boolean }>("api/approvals", post({ id, approved })),
  emergency: (on: boolean) =>
    request<{ emergency: boolean }>("api/emergency", post({ on })),
  settings: () => request<SettingsPayload>("api/settings"),
  saveSettings: (draft: SettingsDraft) =>
    request<{ setup_required: boolean; values: SettingsPayload["values"] }>(
      "api/settings",
      post(draft),
    ),
  testKey: (draft: SettingsDraft) =>
    request<{ ok: boolean; message: string }>("api/settings/test", post(draft)),
  devices: () => request<{ devices: Device[]; selected: string }>("api/devices"),
  whatsapp: () => request<WhatsAppState>("api/whatsapp"),
  setWhatsApp: (on: boolean) =>
    request<WhatsAppState>("api/whatsapp", post({ on })),
  selectWhatsAppGroup: (jid: string) =>
    request<WhatsAppState>("api/whatsapp/group", post({ jid })),
  setWhatsAppMode: (mode: string) =>
    request<WhatsAppState>("api/whatsapp/mode", post({ mode })),
  refreshWhatsAppGroups: () =>
    request<WhatsAppState>("api/whatsapp/groups", post({})),
};
