"""Rotinas: prompts que o Nox corre sozinho a horas certas.

Guardadas em `%LOCALAPPDATA%\\HeyNox\\routines.json`. Três formas de agenda:

- `daily@09:00` — todos os dias a essa hora (ou na primeira vez que o Nox
  arrancar depois dela);
- `every@2h` — a cada 2 horas, contadas desde a criação ou da última execução;
- `once@2026-11-10T09:00` — uma vez, e depois fica desligada.

O agendador vive na interface (`nox --ui`). Sem interface, as rotinas ficam
guardadas mas não disparam — o CLI não tem um processo sempre ligado.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from nox.config import NoxError
from nox.paths import user_data_dir

DAILY = re.compile(r"^daily@(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")
EVERY = re.compile(r"^every@(?P<count>[1-9]\d*)(?P<unit>[smh])$")
ONCE = re.compile(r"^once@(?P<date>\d{4}-\d{2}-\d{2})T(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")

EXAMPLES = "daily@09:00, every@2h ou once@2026-11-10T09:00"


class RoutineError(NoxError):
    """Rotina inválida."""


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


@dataclass
class Routine:
    id: str
    prompt: str
    schedule: str
    created_at: float
    last_run: float | None = None
    enabled: bool = True
    runs: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Routine:
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            prompt=str(data.get("prompt") or ""),
            schedule=str(data.get("schedule") or ""),
            created_at=_number(data.get("created_at"), time.time()),
            last_run=_number(data["last_run"]) if data.get("last_run") else None,
            enabled=bool(data.get("enabled", True)),
            runs=int(_number(data.get("runs"))),
        )


def parse_schedule(text: str) -> str:
    """Valida a agenda e devolve-a normalizada."""
    value = text.strip()
    if DAILY.match(value) or EVERY.match(value):
        return value
    if ONCE.match(value):
        try:
            _once_at(value)
        except ValueError as exc:
            raise RoutineError(
                f"agenda inválida: a data em {text!r} não existe. Usa {EXAMPLES}"
            ) from exc
        return value
    raise RoutineError(f"agenda inválida: {text!r}. Usa {EXAMPLES}")


def _daily_target(schedule: str) -> tuple[int, int]:
    match = DAILY.match(schedule)
    assert match is not None
    return int(match.group("hour")), int(match.group("minute"))


def _every_seconds(schedule: str) -> int:
    match = EVERY.match(schedule)
    assert match is not None
    factor = {"s": 1, "m": 60, "h": 3600}[match.group("unit")]
    return int(match.group("count")) * factor


def _once_at(schedule: str) -> datetime:
    match = ONCE.match(schedule)
    assert match is not None
    return datetime.fromisoformat(
        f"{match.group('date')}T{match.group('hour')}:{match.group('minute')}"
    )


def is_due(routine: Routine, now: datetime) -> bool:
    if not routine.enabled or not routine.prompt.strip():
        return False
    last = datetime.fromtimestamp(routine.last_run) if routine.last_run else None

    if DAILY.match(routine.schedule):
        hour, minute = _daily_target(routine.schedule)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return False
        if last is not None:
            return last.date() < now.date()
        # Criada depois da hora de hoje: a primeira execução é amanhã, não já.
        created = datetime.fromtimestamp(routine.created_at)
        return created <= target

    if EVERY.match(routine.schedule):
        interval = _every_seconds(routine.schedule)
        reference = routine.last_run or routine.created_at
        return now.timestamp() - reference >= interval

    if ONCE.match(routine.schedule):
        if last is not None:
            return False
        return now >= _once_at(routine.schedule)

    return False


class RoutineStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_data_dir() / "routines.json")
        self._lock = threading.Lock()

    def load(self) -> list[Routine]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [Routine.from_dict(item) for item in raw if isinstance(item, dict)]

    def save(self, routines: list[Routine]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps([routine.to_dict() for routine in routines], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def add(self, prompt: str, schedule: str, *, now: datetime | None = None) -> Routine:
        prompt = prompt.strip()
        if not prompt:
            raise RoutineError("falta o que a rotina deve fazer")
        if len(prompt) > 2000:
            raise RoutineError("a rotina é grande demais")
        routine = Routine(
            id=uuid.uuid4().hex[:8],
            prompt=prompt,
            schedule=parse_schedule(schedule),
            created_at=(now or datetime.now()).timestamp(),
        )
        with self._lock:
            routines = self.load()
            routines.append(routine)
            self.save(routines)
        return routine

    def remove(self, key: str) -> int:
        key = key.strip().lower()
        if not key:
            return 0
        with self._lock:
            routines = self.load()
            keep = [
                routine
                for routine in routines
                if routine.id != key and key not in routine.prompt.lower()
            ]
            removed = len(routines) - len(keep)
            if removed:
                self.save(keep)
            return removed

    def mark_run(self, routine_id: str, *, when: datetime | None = None) -> None:
        with self._lock:
            routines = self.load()
            for routine in routines:
                if routine.id == routine_id:
                    routine.last_run = (when or datetime.now()).timestamp()
                    routine.runs += 1
                    if ONCE.match(routine.schedule):
                        routine.enabled = False
            self.save(routines)


@dataclass
class RoutineScheduler:
    """Corre as rotinas devidas num thread próprio."""

    store: RoutineStore
    run: Callable[[Routine], str]
    tick_s: float = 30.0
    clock: Callable[[], datetime] = datetime.now
    on_error: Callable[[Routine, Exception], None] | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False, init=False)
    _thread: threading.Thread | None = field(default=None, repr=False, init=False)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nox-routines", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick_s):
            self.run_due()

    def run_due(self, now: datetime | None = None) -> list[Routine]:
        moment = now or self.clock()
        executed: list[Routine] = []
        for routine in self.store.load():
            if not is_due(routine, moment):
                continue
            self.store.mark_run(routine.id, when=moment)
            try:
                self.run(routine)
            except Exception as exc:  # noqa: BLE001 — uma rotina má não para as outras
                if self.on_error is not None:
                    self.on_error(routine, exc)
            executed.append(routine)
        return executed
