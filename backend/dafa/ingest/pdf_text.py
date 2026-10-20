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
    return re.sub(r"\d+", "#", t.strip().lower())


def extract_lines(pdf_path: Path, small_ratio: float = 0.86) -> list[Line]:
    import fitz  # PyMuPDF; only needed at ingestion time

    doc = fitz.open(pdf_path)
    sizes: Counter[float] = Counter()
    pages = []
    for page in doc:
        d = page.get_text("dict", sort=True)
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
        for block in d["blocks"]:
            for line in block.get("lines", []):
                kept, bold_chars, total_chars, max_size = [], 0, 0, 0.0
                for span in line["spans"]:
                    txt = span["text"]
                    if not txt.strip():
                        kept.append(txt)
                        continue
                    if span["size"] < cutoff:
                        continue  # footnote text or superscript marker
                    kept.append(txt)
                    total_chars += len(txt)
                    max_size = max(max_size, span["size"])
                    if span["flags"] & 16 or "bold" in span["font"].lower():
                        bold_chars += len(txt)
                text = "".join(kept).strip()
                if text:
                    raw.append(Line(pno, text, bold_chars > total_chars * 0.6, max_size))

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


AMEND_MARK_RE = re.compile(r"\d{0,2}\[|\]")
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
