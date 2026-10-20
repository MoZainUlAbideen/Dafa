"""Integrity checks on the real extracted books (backend/data/processed).
These guard the parsers against regressions on the actual PDFs."""

import json
from pathlib import Path

import pytest

from dafa.ingest.parse_sections import numbering_gaps
from dafa.models import Section

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
pytestmark = pytest.mark.skipif(not (DATA / "ppc.json").exists(), reason="processed data not built")


def load(book):
    return {s.id: s for s in (Section(**r) for r in json.loads((DATA / f"{book}.json").read_text(encoding="utf-8")))}


def test_ppc_complete_and_ordered():
    ppc = load("ppc")
    assert len(ppc) > 600 and "511" in ppc
    assert numbering_gaps(list(ppc.values())) == []


def test_constitution_complete_and_ordered():
    c = load("constitution")
    assert len(c) > 300 and "280" in c
    assert numbering_gaps(list(c.values())) == []


@pytest.mark.parametrize("sid,title,starts", [
    ("302", "Punishment of qatl-e-amd", "Whoever commits qatl-e-amd shall"),
    ("378", "Theft", "Whoever, intending to take dishonestly"),
    ("489-F", "Dishonestly issuing a cheque", "Whoever dishonestly issues a cheque"),
    ("359", "Kidnapping", "Kidnapping is of two kinds"),
])
def test_ppc_known_sections(sid, title, starts):
    s = load("ppc")[sid]
    assert s.title == title and s.text.startswith(starts)


@pytest.mark.parametrize("aid,title", [
    ("10", "Safeguards as to arrest and detention"),
    ("10A", "Right to fair trial"),
    ("25A", "Right to education"),
    ("8", "Laws inconsistent with or in derogation of Fundamental Rights to be void"),
])
def test_constitution_titles_from_arrangement(aid, title):
    assert load("constitution")[aid].title == title


def test_no_amendment_markers_or_footnote_digits_left():
    for book in ("ppc", "constitution"):
        for s in load(book).values():
            assert "[" not in s.text and "]" not in s.text, (book, s.id)


def test_omissions_flagged():
    assert load("ppc")["13"].omitted
    assert load("constitution")["184"].omitted  # omitted by the 27th Amendment


def test_schedule_ii_joined_and_matches_source():
    ppc = load("ppc")
    assert sum(1 for s in ppc.values() if s.schedule) >= 400
    # values checked by eye against the CrPC PDF page images
    assert ppc["379"].schedule.bailable.lower().startswith("not bailable")
    assert ppc["420"].schedule.bailable.lower().startswith("bailable")
    assert ppc["489-F"].schedule.compoundable.lower().startswith("compoundable")
    assert "shall not arrest" in ppc["161"].schedule.cognizable.lower()
