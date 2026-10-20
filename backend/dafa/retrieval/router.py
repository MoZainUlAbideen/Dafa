"""Detect direct references like "section 302", "dafa 489-F", "Article 25A".

When a user names a section we fetch it exactly instead of searching.
That is faster, cheaper and cannot retrieve the wrong thing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "302", "489-F", "337-A", "25A", "295-C", "63A"
_ID = r"(\d{1,3}(?:-?[A-Z]{1,2})?)"

_PPC_WORDS = r"(?:section|sec\.?|s\.|dafa|daffa|dafah|دفعہ|ppc|u/s)"
_CONST_WORDS = r"(?:article|art\.?|aain|aaeen|شق|آرٹیکل)"

PPC_RE = re.compile(rf"{_PPC_WORDS}\s*{_ID}\b", re.IGNORECASE)
PPC_SUFFIX_RE = re.compile(rf"\b{_ID}\s*(?:ppc|p\.p\.c)\b", re.IGNORECASE)
CONST_RE = re.compile(rf"{_CONST_WORDS}\s*{_ID}\b", re.IGNORECASE)
BARE_NUM_RE = re.compile(rf"^\s*{_ID}\s*\??\s*$", re.IGNORECASE)


@dataclass
class Route:
    refs: list[tuple[str, str]]  # [(book, id)]
    book_hint: str | None  # "ppc" / "constitution" if the query clearly targets one


def normalise_id(raw: str) -> str:
    """'489f' -> '489-F'; '25a' stays '25A' for the Constitution style is decided by lookup."""
    raw = raw.upper().replace(" ", "")
    return raw


def route(query: str) -> Route:
    refs: list[tuple[str, str]] = []
    for m in PPC_RE.finditer(query):
        refs.append(("ppc", normalise_id(m.group(1))))
    for m in PPC_SUFFIX_RE.finditer(query):
        refs.append(("ppc", normalise_id(m.group(1))))
    for m in CONST_RE.finditer(query):
        refs.append(("constitution", normalise_id(m.group(1))))
    if not refs:
        m = BARE_NUM_RE.match(query)
        if m:  # a bare "302" most often means the PPC
            refs.append(("ppc", normalise_id(m.group(1))))

    q = query.lower()
    hint = None
    if re.search(r"constitution|aain|aaeen|fundamental right|article|parliament|assembly|senate|prime minister|president|supreme court|high court|amendment", q):
        hint = "constitution"
    if re.search(r"ppc|penal|crime|offence|offense|punish|saza|jail|fir|bail|zamanat|dafa|police", q):
        hint = "ppc" if hint is None else None  # both mentioned -> no hint
    seen, uniq = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return Route(refs=uniq, book_hint=hint)
