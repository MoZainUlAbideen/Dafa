"""Loads the processed law books and answers two questions:
  - get(book, id): exact lookup, tolerant of "489F" vs "489-F"
  - search(query): BM25 over every section, optionally limited to one book
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dafa.config import settings
from dafa.models import BOOK_TITLES, Section
from dafa.retrieval.bm25 import BM25
from dafa.retrieval.text import expand_query, tokenize

TITLE_WEIGHT = 3  # a match in the title counts like 3 matches in the body


def _canon(sec_id: str) -> str:
    """Canonical form for matching: uppercase, no dashes/spaces. '489-F' -> '489F'."""
    return re.sub(r"[\s\-]", "", sec_id.upper())


@dataclass
class Hit:
    section: Section
    score: float


class LawStore:
    def __init__(self, sections: list[Section]):
        self.sections = sections
        self._by_key = {(s.book, _canon(s.id)): s for s in sections}
        self._book_idx: dict[str, set[int]] = {}
        docs = []
        for i, s in enumerate(sections):
            self._book_idx.setdefault(s.book, set()).add(i)
            body = f"{(s.title + ' ') * TITLE_WEIGHT} {s.group} {s.text}"
            if s.schedule and s.schedule.offence:
                body += " " + s.schedule.offence
            docs.append(tokenize(body))
        self.bm25 = BM25(docs)

    @classmethod
    def from_dir(cls, data_dir: Path) -> "LawStore":
        sections: list[Section] = []
        for book in BOOK_TITLES:
            path = data_dir / f"{book}.json"
            if path.exists():
                rows = json.loads(path.read_text(encoding="utf-8"))
                sections.extend(Section(**r) for r in rows)
        return cls(sections)

    def books(self) -> list[str]:
        return [b for b in BOOK_TITLES if b in self._book_idx]

    def get(self, book: str, sec_id: str) -> Section | None:
        return self._by_key.get((book, _canon(sec_id)))

    def neighbours(self, book: str, sec_id: str) -> tuple[Section | None, Section | None]:
        rows = [s for s in self.sections if s.book == book]
        for i, s in enumerate(rows):
            if _canon(s.id) == _canon(sec_id):
                return (rows[i - 1] if i > 0 else None, rows[i + 1] if i + 1 < len(rows) else None)
        return None, None

    def search(self, query: str, k: int = 6, book: str | None = None, extra_terms: list[str] | None = None) -> list[Hit]:
        terms = expand_query(query)
        for t in extra_terms or []:
            terms.extend(tokenize(t))
        allowed = self._book_idx.get(book) if book else None
        hits = self.bm25.top(terms, k * 3, allowed)
        out = [Hit(self.sections[i], sc) for i, sc in hits if not self.sections[i].omitted]
        return out[:k]

    def toc(self, book: str) -> list[dict]:
        groups: list[dict] = []
        for s in self.sections:
            if s.book != book:
                continue
            if not groups or groups[-1]["name"] != s.group:
                groups.append({"name": s.group, "sections": []})
            groups[-1]["sections"].append({"id": s.id, "title": s.title, "omitted": s.omitted})
        return groups


@lru_cache(maxsize=1)
def get_store() -> LawStore:
    return LawStore.from_dir(settings.data_dir)
