"""Core data shapes shared by ingestion, retrieval and the API.

A `Section` is one unit of law: a PPC section ("302") or a Constitution
article ("25A"). Everything downstream (search, citations, the frontend
section cards) works with these.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BookId = Literal["constitution", "ppc"]

BOOK_TITLES: dict[str, str] = {
    "constitution": "Constitution of Pakistan, 1973",
    "ppc": "Pakistan Penal Code, 1860",
}

# What a single unit is called in each book ("Article 25A", "Section 302").
UNIT_LABEL: dict[str, str] = {"constitution": "Article", "ppc": "Section"}


class ScheduleInfo(BaseModel):
    """CrPC Schedule II row for a PPC section: the procedural facts
    people actually need when an FIR names a section."""

    offence: str = ""
    cognizable: str = ""  # "Yes" / "No" / free text from the table
    warrant_or_summons: str = ""
    bailable: str = ""
    compoundable: str = ""
    punishment: str = ""
    court: str = ""


class Section(BaseModel):
    book: BookId
    id: str  # "302", "489-F", "25A"
    title: str
    text: str  # body text, cleaned of amendment markers
    group: str = ""  # Part / Chapter heading this unit sits under
    page: int | None = None  # 1-based page in the source PDF
    omitted: bool = False
    schedule: ScheduleInfo | None = None

    @property
    def key(self) -> str:
        return f"{self.book}:{self.id}"

    @property
    def label(self) -> str:
        return f"{UNIT_LABEL[self.book]} {self.id}"


class TocGroup(BaseModel):
    name: str
    sections: list[dict] = Field(default_factory=list)  # [{id, title}]
