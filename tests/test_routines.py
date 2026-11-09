from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nox.automation.routines import (
    Routine,
    RoutineError,
    RoutineScheduler,
    RoutineStore,
    is_due,
    parse_schedule,
)

NOW = datetime(2026, 11, 9, 10, 0)


def make(
    schedule: str, *, last: datetime | None = None, created: datetime | None = None
) -> Routine:
    created_at = (created or NOW).timestamp()
    return Routine(
        id="abc123",
        prompt="resumir o dia",
        schedule=schedule,
        created_at=created_at,
        last_run=last.timestamp() if last else None,
    )


@pytest.mark.parametrize(
    "schedule",
    ["daily@09:00", "daily@23:59", "every@30m", "every@2h", "once@2026-11-10T09:00"],
)
def test_valid_schedules(schedule: str) -> None:
    assert parse_schedule(schedule) == schedule


@pytest.mark.parametrize(
    "schedule",
    ["daily@25:00", "daily@9:00", "every@0m", "every@2d", "once@2026-13-01T09:00", "amanhã"],
)
def test_invalid_schedules(schedule: str) -> None:
    with pytest.raises(RoutineError, match="agenda inválida"):
        parse_schedule(schedule)


def test_daily_runs_after_the_time() -> None:
    assert is_due(make("daily@09:00", created=NOW - timedelta(days=1)), NOW) is True


def test_daily_created_after_the_time_waits_for_tomorrow() -> None:
    routine = make("daily@09:00", created=NOW)

    assert is_due(routine, NOW) is False
    assert is_due(routine, NOW + timedelta(days=1)) is True


def test_daily_does_not_run_before_the_time() -> None:
    assert is_due(make("daily@11:00"), NOW) is False


def test_daily_does_not_repeat_on_the_same_day() -> None:
    assert is_due(make("daily@09:00", last=NOW.replace(hour=9, minute=5)), NOW) is False


def test_daily_runs_again_the_next_day() -> None:
    assert is_due(make("daily@09:00", last=NOW - timedelta(days=1)), NOW) is True


def test_every_waits_for_the_interval() -> None:
    assert is_due(make("every@2h", created=NOW - timedelta(hours=1)), NOW) is False
    assert is_due(make("every@2h", created=NOW - timedelta(hours=3)), NOW) is True


def test_every_counts_from_the_last_run() -> None:
    assert is_due(make("every@30m", last=NOW - timedelta(minutes=10)), NOW) is False
    assert is_due(make("every@30m", last=NOW - timedelta(minutes=40)), NOW) is True


def test_once_runs_when_due_and_only_once() -> None:
    assert is_due(make("once@2026-11-10T09:00"), NOW) is False
    assert is_due(make("once@2026-11-09T09:00"), NOW) is True
    assert is_due(make("once@2026-11-09T09:00", last=NOW), NOW) is False


def test_disabled_routines_never_run() -> None:
    routine = make("daily@09:00")
    routine.enabled = False
    assert is_due(routine, NOW) is False


def test_store_adds_lists_and_removes(tmp_path: Path) -> None:
    store = RoutineStore(tmp_path / "routines.json")

    routine = store.add("resumir o dia", "daily@09:00", now=NOW)
    assert [item.id for item in store.load()] == [routine.id]

    assert store.remove("resumir") == 1
    assert store.load() == []


def test_store_marks_runs_and_disables_once(tmp_path: Path) -> None:
    store = RoutineStore(tmp_path / "routines.json")
    routine = store.add("uma vez", "once@2026-11-09T09:00", now=NOW)

    store.mark_run(routine.id, when=NOW)

    saved = store.load()[0]
    assert saved.runs == 1
    assert saved.last_run == NOW.timestamp()
    assert saved.enabled is False


def test_store_rejects_empty_prompts(tmp_path: Path) -> None:
    store = RoutineStore(tmp_path / "routines.json")
    with pytest.raises(RoutineError, match="falta"):
        store.add("   ", "daily@09:00")


def test_scheduler_runs_each_routine_once(tmp_path: Path) -> None:
    store = RoutineStore(tmp_path / "routines.json")
    routine = store.add("resumir", "daily@09:00", now=NOW - timedelta(days=1))
    ran: list[str] = []
    scheduler = RoutineScheduler(store, lambda item: ran.append(item.id) or "ok", clock=lambda: NOW)

    first = scheduler.run_due()
    second = scheduler.run_due()

    assert [item.id for item in first] == [routine.id]
    assert second == []
    assert ran == [routine.id]


def test_scheduler_survives_a_failing_routine(tmp_path: Path) -> None:
    store = RoutineStore(tmp_path / "routines.json")
    store.add("falhar", "daily@09:00", now=NOW - timedelta(days=1))
    errors: list[Exception] = []

    def boom(_routine: Routine) -> str:
        raise RuntimeError("falhou")

    scheduler = RoutineScheduler(
        store,
        boom,
        clock=lambda: NOW,
        on_error=lambda _routine, exc: errors.append(exc),
    )
    scheduler.run_due()

    assert len(errors) == 1
