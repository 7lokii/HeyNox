import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from nox.brain.agent import Agent
from nox.brain.llm import EchoLlm
from nox.config import Config
from nox.integrations.whatsapp import (
    IncomingMessage,
    WhatsAppGroup,
    WhatsAppService,
    WhatsAppStore,
    clean_text,
    is_agent_reply,
    jid_server,
    jid_user,
    qr_data_url,
    starts_with_nox,
)
from nox.integrations.whatsapp_history import WhatsAppHistory
from nox.safety.audit import AuditLog
from nox.ui.server import NoxApp, build_server
from nox.ui.settings import SettingsStore


class FakeBackend:
    """Transporte determinístico: nenhuma conta, nenhuma rede."""

    def __init__(self, groups: list[WhatsAppGroup] | None = None) -> None:
        self.handlers = None
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.sent: list[tuple[str, str]] = []
        self.groups_list = groups or [WhatsAppGroup("120@g.us", "Família", 4)]
        self.failure: Exception | None = None

    def connect(self, handlers) -> None:
        if self.failure is not None:
            raise self.failure
        self.handlers = handlers
        self.started.set()
        self.stopped.wait(2)

    def stop(self) -> None:
        self.stopped.set()

    def groups(self) -> list[WhatsAppGroup]:
        return list(self.groups_list)

    def send(self, chat: str, text: str) -> None:
        self.sent.append((chat, text))


def make_service(tmp_path, *, reply=None, cooldown_s: float = 0.0):
    backend = FakeBackend()
    clock = [100.0]
    service = WhatsAppService(
        reply or (lambda text, _sender, _owner: f"eco: {text}"),
        backend_factory=lambda: backend,
        store=WhatsAppStore(tmp_path / "whatsapp.json"),
        history=WhatsAppHistory(tmp_path / "history.db"),
        audit=AuditLog(tmp_path / "audit.jsonl"),
        cooldown_s=cooldown_s,
        clock=lambda: clock[0],
        log=lambda _message: None,
    )
    return service, backend, clock


@pytest.fixture
def whatsapp(tmp_path):
    service, backend, clock = make_service(tmp_path)
    yield service, backend, clock
    service.disable()


def connected(service: WhatsAppService, backend: FakeBackend) -> None:
    service.enable()
    assert backend.started.wait(1)
    assert backend.handlers is not None
    backend.handlers.connected("351912345678@s.whatsapp.net")
    service.refresh_groups()
    service.select_group("120@g.us")


def message(**overrides) -> IncomingMessage:
    values = {
        "chat": "120@g.us",
        "sender": "351911111111@s.whatsapp.net",
        "text": "@Nox que horas são?",
        "is_group": True,
        "sender_name": "Maria",
    }
    values.update(overrides)
    return IncomingMessage(**values)


def test_revoke_event_exposes_the_original_message_id() -> None:
    pytest.importorskip("neonize")
    from neonize.proto.waCommon.WACommon_pb2 import MessageKey
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message, ProtocolMessage

    from nox.integrations.whatsapp import revoked_message_id

    revoke = Message(
        protocolMessage=ProtocolMessage(
            key=MessageKey(ID="m1"),
            type=ProtocolMessage.REVOKE,
        )
    )
    assert revoked_message_id(revoke) == "m1"
    assert revoked_message_id(Message(conversation="olá")) == ""


def test_jid_helpers() -> None:
    assert jid_user("351912345678:2@s.whatsapp.net") == "351912345678"
    assert jid_server("120@g.us") == "g.us"


def test_trigger_is_the_literal_nox_at_the_start() -> None:
    assert starts_with_nox("@Nox olá") is True
    assert starts_with_nox("  @nox, olá") is True
    assert starts_with_nox("@Nox: olá") is True
    assert starts_with_nox("olá @Nox") is False
    assert starts_with_nox("@Noxas olá") is False
    assert starts_with_nox("@351912345678 olá") is False

    assert is_agent_reply("Nox: olá") is True
    assert is_agent_reply("  nox: olá") is True
    assert is_agent_reply("@Nox olá") is False


def test_clean_text_removes_the_trigger() -> None:
    assert clean_text("  @Nox   vê   isto ") == "vê isto"
    assert clean_text("@Nox, vê isto") == "vê isto"


def test_qr_normalizes_png_and_text() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"dados"
    assert qr_data_url(png).startswith("data:image/png;base64,")


def test_enable_exposes_qr_and_connected_state(whatsapp) -> None:
    service, backend, _ = whatsapp
    service.enable()
    assert backend.started.wait(1)

    assert service.payload()["status"] == "starting"
    assert backend.handlers is not None
    backend.handlers.qr("data:image/png;base64,abc")
    assert service.payload()["status"] == "qr"
    assert service.payload()["qr"] == "data:image/png;base64,abc"

    backend.handlers.connected("351912345678@s.whatsapp.net")
    payload = service.payload()
    assert payload["status"] == "connected"
    assert payload["me"] == "351912345678"


def test_only_nox_prefix_in_the_selected_group_gets_an_answer(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    backend.handlers.message(message())
    assert backend.sent == [("120@g.us", "Nox: eco: que horas são?")]


def test_own_messages_can_call_the_agent(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    backend.handlers.message(message(from_me=True))

    assert backend.sent == [("120@g.us", "Nox: eco: que horas são?")]


def test_reply_callback_receives_whether_the_sender_is_the_owner(tmp_path) -> None:
    seen: list[tuple[str, str, bool]] = []

    def reply(text: str, sender: str, owner: bool) -> str:
        seen.append((text, sender, owner))
        return "ok"

    service, backend, _ = make_service(tmp_path, reply=reply)
    connected(service, backend)

    backend.handlers.message(message(from_me=True))
    backend.handlers.message(message(sender="351922222222@s.whatsapp.net"))

    assert seen == [
        ("que horas são?", "351911111111@s.whatsapp.net", True),
        ("que horas são?", "351922222222@s.whatsapp.net", False),
    ]


def test_history_stores_untriggered_messages_and_group_size(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    connected(service, backend)

    backend.handlers.message(
        message(
            text="assunto privado do grupo",
            message_id="m1",
            sender_name="Maria",
            sent_at=time.time(),
        )
    )

    assert backend.sent == []
    owner = service.context(owner=True)
    guest = service.context(owner=False)
    assert "4 participantes" in owner
    assert "assunto privado do grupo" in owner
    assert "assunto privado do grupo" not in guest
    assert "4 participantes" in guest


def test_deleted_message_is_kept_for_the_owner_only(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    connected(service, backend)
    stamp = time.time()

    backend.handlers.message(
        message(
            text="@Nox combinamos às 15h",
            message_id="m1",
            sender_name="Maria",
            sent_at=stamp,
        )
    )
    backend.handlers.message(
        message(
            text="",
            message_id="revoke-1",
            sender="351922222222@s.whatsapp.net",
            sender_name="João",
            sent_at=stamp + 1,
            revoked_id="m1",
        )
    )

    assert [text for _chat, text in backend.sent] == ["Nox: eco: combinamos às 15h"]
    owner = service.context(owner=True)
    assert "combinamos às 15h" in owner
    assert "APAGADA" in owner
    assert "por João" in owner
    assert "combinamos às 15h" not in service.context(owner=False)


def test_group_count_refresh_updates_the_selected_group(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    connected(service, backend)
    backend.groups_list = [WhatsAppGroup("120@g.us", "Família", 7)]

    service.refresh_groups()

    assert service.payload()["selected"]["participants"] == 7
    assert "7 participantes" in service.context(owner=True)


def test_history_survives_a_new_service_instance(tmp_path) -> None:
    first, backend, _ = make_service(tmp_path)
    connected(first, backend)
    backend.handlers.message(message(text="fica guardado", message_id="m3", sent_at=time.time()))
    first.disable()

    second, backend2, _ = make_service(tmp_path)
    connected(second, backend2)

    assert "fica guardado" in second.context(owner=True)
    second.disable()


def test_app_wires_history_only_into_the_owner_agent(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    connected(service, backend)
    backend.handlers.message(message(text="segredo do grupo", message_id="m2", sent_at=time.time()))
    config = Config.model_validate({"nox": {"voice_enabled": False}})
    app = NoxApp(
        config,
        agent=Agent(EchoLlm()),
        settings=SettingsStore(root=tmp_path / "app"),
        whatsapp=service,
    )

    assert app.whatsapp_owner_agent.context is not None
    assert app.whatsapp_guest_agent.context is not None
    assert "segredo do grupo" in app.whatsapp_owner_agent.context("pergunta")
    assert "segredo do grupo" not in app.whatsapp_guest_agent.context("pergunta")


def test_agent_prefix_is_not_answered(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    backend.handlers.message(message(from_me=True, text="Nox: já respondi"))

    assert backend.sent == []


def test_bare_trigger_gets_a_short_prompt(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    backend.handlers.message(message(text="@Nox"))

    assert backend.sent == [("120@g.us", "Nox: Diz-me o que precisas.")]


@pytest.mark.parametrize(
    "incoming",
    [
        message(is_group=False),
        message(chat="999@g.us"),
        message(text="olá a todos"),
        message(text="@Noxas olá"),
        message(text="@351912345678 que horas são?"),
        message(text=""),
    ],
)
def test_ignored_messages(whatsapp, incoming: IncomingMessage) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    backend.handlers.message(incoming)

    assert backend.sent == []


def test_all_messages_mode_answers_without_trigger(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)
    assert service.set_mode("all")["mode"] == "all"

    backend.handlers.message(message(text="bom dia a todos"))

    assert backend.sent == [("120@g.us", "Nox: eco: bom dia a todos")]


def test_invalid_mode_is_refused(whatsapp) -> None:
    service, _backend, _ = whatsapp
    with pytest.raises(ValueError, match="Modo inválido"):
        service.set_mode("alguns")


def test_no_group_selected_means_no_replies(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    service.enable()
    assert backend.started.wait(1)
    backend.handlers.connected("351912345678@s.whatsapp.net")

    backend.handlers.message(message())

    assert backend.sent == []
    service.disable()


def test_cooldown_avoids_message_storms(tmp_path) -> None:
    service, backend, clock = make_service(tmp_path, cooldown_s=5.0)
    connected(service, backend)

    backend.handlers.message(message(text="@Nox primeira"))
    clock[0] += 1
    backend.handlers.message(message(text="@Nox segunda"))
    clock[0] += 5
    backend.handlers.message(message(text="@Nox terceira"))

    assert [text for _chat, text in backend.sent] == [
        "Nox: eco: primeira",
        "Nox: eco: terceira",
    ]


def test_reply_failure_keeps_the_channel_alive(tmp_path) -> None:
    def boom(_text: str, _sender: str, _owner: bool) -> str:
        raise RuntimeError("modelo em baixo")

    service, backend, _ = make_service(tmp_path, reply=boom)
    connected(service, backend)

    backend.handlers.message(message())

    assert backend.sent == []
    payload = service.payload()
    assert payload["status"] == "connected"
    assert "modelo em baixo" in payload["error"]


def test_audit_records_the_reply(whatsapp, tmp_path) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)
    backend.handlers.message(message())

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["tool"] == "whatsapp"
    assert entry["ok"] is True


def test_missing_backend_reverts_the_switch(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    backend.failure = RuntimeError("falta o extra whatsapp")

    payload = service.enable()

    assert payload["enabled"] is False
    assert payload["status"] == "error"
    assert "extra whatsapp" in payload["error"]


def test_unknown_group_is_refused(whatsapp) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    with pytest.raises(ValueError, match="desconhecido"):
        service.select_group("nao-existe@g.us")


def test_disable_stops_the_backend_and_persists_off(whatsapp, tmp_path) -> None:
    service, backend, _ = whatsapp
    connected(service, backend)

    payload = service.disable()

    assert payload["enabled"] is False
    assert backend.stopped.wait(1)
    saved = json.loads((tmp_path / "whatsapp.json").read_text(encoding="utf-8"))
    assert saved["enabled"] is False


def test_stop_keeps_the_startup_preference(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    connected(service, backend)
    service.set_mode("all")
    service.stop()

    saved = json.loads((tmp_path / "whatsapp.json").read_text(encoding="utf-8"))
    assert saved["enabled"] is True
    assert saved["mode"] == "all"

    second, backend2, _ = make_service(tmp_path)
    second.resume()
    assert backend2.started.wait(1)
    second.disable()


def test_app_routes_owner_and_guest_to_separate_agents(tmp_path) -> None:
    class StubAgent:
        def __init__(self, name: str) -> None:
            self.name = name
            self.calls: list[str] = []

        def reply(self, text: str) -> str:
            self.calls.append(text)
            return self.name

    service, _backend, _ = make_service(tmp_path)
    config = Config.model_validate({"nox": {"voice_enabled": False}})
    app = NoxApp(
        config,
        agent=Agent(EchoLlm()),
        settings=SettingsStore(root=tmp_path / "app"),
        whatsapp=service,
    )
    owner = StubAgent("owner")
    guest = StubAgent("guest")
    app.whatsapp_owner_agent = owner  # type: ignore[assignment]
    app.whatsapp_guest_agent = guest  # type: ignore[assignment]

    assert app._whatsapp_reply("do dono", "dono@s.whatsapp.net", True) == "owner"
    assert app._whatsapp_reply("de outra pessoa", "outra@s.whatsapp.net", False) == "guest"
    assert owner.calls == ["do dono"]
    assert guest.calls == ["de outra pessoa"]


def test_whatsapp_agents_have_owner_and_guest_prompts(tmp_path) -> None:
    config = Config.model_validate({"nox": {"voice_enabled": False}})
    app = NoxApp(
        config,
        agent=Agent(EchoLlm()),
        settings=SettingsStore(root=tmp_path / "app"),
    )

    owner_prompt = app.whatsapp_owner_agent.conversation.system
    guest_prompt = app.whatsapp_guest_agent.conversation.system
    assert "Esta mensagem é do dono" in owner_prompt
    assert "histórico" in owner_prompt
    assert "Esta mensagem é de outro membro" in guest_prompt
    assert "não reveles" in guest_prompt
    assert "Não tens acesso ao histórico" in guest_prompt


def test_api_toggle_and_group_selection(tmp_path) -> None:
    service, backend, _ = make_service(tmp_path)
    config = Config.model_validate({"nox": {"voice_enabled": False}})
    app = NoxApp(
        config,
        agent=Agent(EchoLlm()),
        settings=SettingsStore(root=tmp_path / "app"),
        whatsapp=service,
    )
    httpd, port = build_server(app, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        assert get_json(base + "/api/whatsapp")["status"] == "off"

        assert post_json(base + "/api/whatsapp", {"on": True})["enabled"] is True
        assert backend.started.wait(1)
        backend.handlers.connected("351912345678@s.whatsapp.net")

        groups = post_json(base + "/api/whatsapp/groups", {})["groups"]
        assert groups[0]["name"] == "Família"

        selected = post_json(base + "/api/whatsapp/group", {"jid": "120@g.us"})
        assert selected["selected"]["name"] == "Família"
        assert selected["mode"] == "mentions"

        assert post_json(base + "/api/whatsapp/mode", {"mode": "all"})["mode"] == "all"
        assert post_json(base + "/api/whatsapp", {"on": False})["enabled"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(  # noqa: S310
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))
