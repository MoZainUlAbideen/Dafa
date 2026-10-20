"""PDF -> clean lines, using font information rather than guesswork.

Statute PDFs carry three kinds of noise that ruin naive text extraction:
  1. footnotes at the bottom of pages ("1Subs. by Act XX of 2016 ...")
  2. superscript amendment numbers glued to the text ("1[Pakistan]")
  3. running headers/footers and page numbers repeated on every page
Footnotes and superscripts are set in a smaller font than the body text, so
we measure the body font size and drop spans that are clearly smaller.
Headers/footers are lines that repeat on many pages.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Line:
    page: int  # 1-based
    text: str
    bold: bool
    size: float


def _norm_for_repeat(t: str) -> str:
    # Ignore digits AND spacing: "CONSTITUTION OF PAKISTAN   5" and
    # "16   CONSTITUTION OF PAKISTAN" are the same running header.
    return re.sub(r"[\d\s]+", "", t.lower())


@dataclass
class _Span:
    x0: float
    x1: float
    ymid: float
    size: float
    text: str
    bold: bool


def group_into_lines(spans: list[_Span]) -> list[list[_Span]]:
    """Group spans that share a baseline into one visual line, ordered left to right.

    Why not use the PDF's own lines/blocks: in the PPC PDF the bold section heading
    ("302. Punishment of qatl-e-amd.") and the first words of its body sit on the
    same printed line but in separate blocks with slightly different y, so block
    order put the body BEFORE the heading (bug found on section 302)."""
    lines: list[list[_Span]] = []
    for sp in sorted(spans, key=lambda s: (s.ymid, s.x0)):
        if lines and abs(sp.ymid - lines[-1][0].ymid) <= max(2.5, 0.35 * sp.size):
            lines[-1].append(sp)
        else:
            lines.append([sp])
    return [sorted(ln, key=lambda s: s.x0) for ln in lines]


def _join(spans: list[_Span]) -> str:
    out = ""
    prev: _Span | None = None
    for sp in spans:
        t = sp.text
        if prev is not None and out and not out.endswith(" ") and not t.startswith(" ") and sp.x0 - prev.x1 > 1.0:
            out += " "
        out += t
        prev = sp
    return re.sub(r"\s+", " ", out).strip()


def extract_lines(pdf_path: Path, small_ratio: float = 0.75) -> list[Line]:
    """small_ratio: spans smaller than this fraction of the body size are dropped.
    Measured on the real PDFs: PPC body 13pt / footnotes 7-9pt / explanations 11pt;
    Constitution body 11pt / margin notes + footnotes 8pt / superscripts 4-5.5pt.
    (0.86 was too strict and dropped the PPC's 11pt explanation text.)"""
    import pymupdf as fitz  # only needed at ingestion time

    doc = fitz.open(pdf_path)
    sizes: Counter[float] = Counter()
    pages = []
    for page in doc:
        d = page.get_text("dict")
        pages.append(d)
        for block in d["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes[round(span["size"], 1)] += len(span["text"])
    body_size = sizes.most_common(1)[0][0] if sizes else 10.0
    cutoff = body_size * small_ratio

    raw: list[Line] = []
    for pno, d in enumerate(pages, start=1):
        spans: list[_Span] = []
        for block in d["blocks"]:
            for line in block.get("lines", []):
                for s in line["spans"]:
                    if not s["text"].strip() or s["size"] < cutoff:
                        continue  # blank, footnote text or superscript marker
                    x0, y0, x1, y1 = s["bbox"]
                    bold = bool(s["flags"] & 16) or "bold" in s["font"].lower()
                    spans.append(_Span(x0, x1, (y0 + y1) / 2, s["size"], s["text"], bold))
        for ln in group_into_lines(spans):
            text = _join(ln)
            if text:
                total = sum(len(s.text) for s in ln)
                bold_chars = sum(len(s.text) for s in ln if s.bold)
                raw.append(Line(pno, text, bold_chars > total * 0.6, max(s.size for s in ln)))

    # Drop running headers/footers: identical (digits ignored) lines on >25% of pages.
    n_pages = len(pages)
    seen_on: dict[str, set[int]] = {}
    for ln in raw:
        seen_on.setdefault(_norm_for_repeat(ln.text), set()).add(ln.page)
    repeated = {k for k, v in seen_on.items() if n_pages >= 8 and len(v) > n_pages * 0.25}
    out = []
    for ln in raw:
        if _norm_for_repeat(ln.text) in repeated:
            continue
        if re.fullmatch(r"(page\s*)?\d{1,4}(\s*of\s*\d+)?", ln.text.strip(), re.I):
            continue
        out.append(ln)
    return out


# "11[", "4 [" (superscript footnote number + bracket), and closing "]".
AMEND_MARK_RE = re.compile(r"(?<![\w(])\d{1,2}\s?\[|\[|\]")
OMIT_RE = re.compile(r"\*\s*\*\s*\*(\s*\*)*")


def clean_text(t: str) -> str:
    """Remove amendment brackets and tidy whitespace.
    '1[Pakistan]' (when the superscript survived) -> 'Pakistan'."""
    t = AMEND_MARK_RE.sub("", t)
    t = OMIT_RE.sub(" ", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"-\s*\n\s*", "", t)
    return t.strip()
