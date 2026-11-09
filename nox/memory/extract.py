"""Extração de factos duráveis das frases do utilizador.

Regras, não LLM: uma chamada ao modelo por turno custaria latência e dinheiro
para apanhar "chamo-me X". O que as regras não apanham fica para quando houver
um extrator semântico — e o utilizador pode sempre dizer "lembra-te que …".
"""

from __future__ import annotations

import re

_TRAILING = " \t\n.!?;:,"

_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\bchamo-me\s+(?P<v>.+)", re.I), "nome", "O utilizador chama-se {v}."),
    (
        re.compile(r"\bo meu nome é\s+(?P<v>.+)", re.I),
        "nome",
        "O utilizador chama-se {v}.",
    ),
    (
        re.compile(r"\blembra-te (?:que|de)\s+(?P<v>.+)", re.I),
        "nota",
        "{v}",
    ),
    (
        re.compile(r"\b(?:guarda|anota) (?:que|isto)\s*:?\s*(?P<v>.+)", re.I),
        "nota",
        "{v}",
    ),
    (re.compile(r"\bprefiro\s+(?P<v>.+)", re.I), "preferencia", "O utilizador prefere {v}."),
    (
        re.compile(r"\bnão gosto de\s+(?P<v>.+)", re.I),
        "desgosto",
        "O utilizador não gosta de {v}.",
    ),
    (re.compile(r"\bgosto de\s+(?P<v>.+)", re.I), "gosto", "O utilizador gosta de {v}."),
)

MAX_FACT_CHARS = 200


def extract_facts(text: str) -> list[tuple[str, str]]:
    """Devolve pares (tipo, facto) prontos a guardar. Pode vir vazio."""
    text = text.strip()
    if not text or len(text) > MAX_FACT_CHARS * 2:
        return []

    found: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    for pattern, kind, template in _RULES:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group("v")
        value = _first_clause(raw).strip().rstrip(_TRAILING)
        if not value or len(value) > MAX_FACT_CHARS:
            continue
        offset = len(raw) - len(raw.lstrip())
        start = match.start("v") + offset
        end = start + len(value)
        # "não gosto de X" contém "gosto de X": a regra mais específica vem
        # primeiro e a segunda é descartada por estar dentro do mesmo troço.
        if any(start >= outer_start and end <= outer_end for outer_start, outer_end in spans):
            continue
        fact = template.format(v=value)
        if any(fact.lower() == existing.lower() for _, existing in found):
            continue
        spans.append((start, end))
        found.append((kind, fact))
    return found


def _first_clause(raw: str) -> str:
    """Corta o valor onde começa outra coisa que o Nox também quer guardar.

    "Chamo-me Rui e prefiro respostas curtas" tem de dar dois factos, não um
    facto comprido e mal formado.
    """
    for separator in (" e ", ", "):
        index = raw.lower().find(separator)
        if index == -1:
            continue
        rest = raw[index + len(separator) :]
        if any(pattern.search(rest) for pattern, _, _ in _RULES):
            return raw[:index]
    return raw
