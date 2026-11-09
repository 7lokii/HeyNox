import pytest

import nox.audio.devices as devices


def fake(monkeypatch: pytest.MonkeyPatch, names: list[tuple[int, str]]) -> None:
    monkeypatch.setattr(devices, "input_devices", lambda: names)


def test_match_by_partial_name(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons"), (7, "Capacete (Mi TW Earphones 2S)")])
    assert devices.match_input("mi tw") == 7
    assert devices.match_input("MI TW") == 7


def test_no_match_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons")])
    assert devices.match_input("Mi TW") is None


def test_default_names_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons")])
    assert devices.match_input("default") is None
    assert devices.match_input("") is None


def test_preferred_wins_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons"), (7, "Mi TW Earphones 2S")])
    assert devices.resolve_input("Mi TW", "default") == (7, "Mi TW")


def test_falls_back_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons")])
    assert devices.resolve_input("Mi TW", "default") == (None, "default")


def test_fallback_can_be_named(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons"), (3, "Microfone USB")])
    assert devices.resolve_input("Mi TW", "USB") == (3, "USB")


def test_picker_picks_up_a_device_connected_later(monkeypatch: pytest.MonkeyPatch) -> None:
    fake(monkeypatch, [(0, "Mapeador de sons")])
    picker = devices.DevicePicker("Mi TW", "default")
    assert picker.index is None

    fake(monkeypatch, [(0, "Mapeador de sons"), (9, "Mi TW Earphones 2S")])
    assert picker.reopen() == 9
    assert picker.label == "Mi TW"
