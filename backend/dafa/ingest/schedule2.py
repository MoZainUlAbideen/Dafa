"""CrPC Schedule II -> {ppc_section_id: ScheduleInfo}.

Schedule II of the Code of Criminal Procedure is a large table: one row per
PPC offence, with columns for whether police may arrest without warrant
(cognizable), warrant or summons, bailable, compoundable, punishment and the
trial court. We read it with PyMuPDF's table finder, map columns by their
header words (so column order in a given PDF doesn't matter), and merge
continuation rows (rows that wrap onto the next line have an empty section cell).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dafa.ingest.pdf_text import clean_text
from dafa.models import ScheduleInfo

SEC_RE = re.compile(r"^\s*(\d{1,3}(?:\s*-?\s*[A-Z]{1,3})?)\s*(?:\(.*\))?\s*$")

COLUMN_WORDS = {
    "section": ["section"],
    "offence": ["offence", "offense"],
    "cognizable": ["arrest", "police"],
    "warrant_or_summons": ["warrant or summons", "summons"],
    "bailable": ["bail"],
    "compoundable": ["compound"],
    "punishment": ["punishment"],
    "court": ["court", "triable"],
}


def map_columns(header: list[str]) -> dict[str, int]:
    """Header cells -> {field: column index}. Earlier fields win ties."""
    cols: dict[str, int] = {}
    norm = [re.sub(r"\s+", " ", (h or "").lower()) for h in header]
    for field in ["warrant_or_summons", "section", "offence", "cognizable", "bailable", "compoundable", "punishment", "court"]:
        for i, h in enumerate(norm):
            if i in cols.values():
                continue
            if any(w in h for w in COLUMN_WORDS[field]):
                cols[field] = i
                break
    return cols


def normalise_sec(raw: str) -> str | None:
    m = SEC_RE.match(raw or "")
    if not m:
        return None
    s = re.sub(r"\s+", "", m.group(1)).upper()
    s = re.sub(r"^(\d+)([A-Z]+)$", r"\1-\2", s)  # "489F" -> "489-F" (PPC style)
    return s


def rows_to_schedule(rows: list[list[str]], cols: dict[str, int]) -> dict[str, ScheduleInfo]:
    out: dict[str, dict[str, str]] = {}
    current: str | None = None
    for row in rows:
        def cell(field: str) -> str:
            i = cols.get(field)
            return re.sub(r"\s+", " ", row[i] or "").strip() if i is not None and i < len(row) else ""

        sec = normalise_sec(cell("section"))
        if sec:
            current = sec
            out.setdefault(sec, {f: "" for f in COLUMN_WORDS if f != "section"})
            for f in out[sec]:
                out[sec][f] = cell(f)
        elif current and not cell("section"):
            for f in out[current]:  # continuation row: append wrapped text
                extra = cell(f)
                if extra:
                    out[current][f] = f"{out[current][f]} {extra}".strip()
    return {k: ScheduleInfo(**v) for k, v in out.items()}


DITTO_RE = re.compile(r"^(ditto|do)\b\.?\s*\.*$", re.I)
ANCHOR_RE = re.compile(r"^\W*(?:\d{1,2}\[)?(\d{2,3}[A-Z]{0,2})\W*$")
# Case-sensitive: "Of Rape" is a sub-heading, but a wrapped cell line like
# "of stolen property" is not (bug: re.I dropped "3 years" from row 414).
HEADING_RE = re.compile(r"^\W*(?:\d{1,2}\[)?(CHAPTER\b|Of\s+[A-Z]|SCHEDULE\b|Page\s+\d+\s+of)")
FIELDS = ["section", "offence", "cognizable", "warrant_or_summons", "bailable", "compoundable", "punishment", "court"]
DEFAULT_BOUNDS = [97.0, 122.0, 189.0, 238.0, 287.0, 337.0, 388.0, 448.0, 491.0]


@dataclass
class Word:
    x0: float
    x1: float
    y: float
    text: str


def page_words(page, min_size: float) -> list[Word]:
    """Words with positions, built from characters so a run like '414 Assisting in'
    is split into separate words (the section number must land in column 0).
    Superscript footnote markers (tiny font) are dropped."""
    words: list[Word] = []
    raw = page.get_text("rawdict")
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["size"] < min_size:
                    continue
                cur: list = []
                for ch in span["chars"] + [None]:
                    if ch is None or ch["c"].isspace():
                        if cur:
                            x0 = cur[0]["bbox"][0]; x1 = cur[-1]["bbox"][2]
                            y = (cur[0]["bbox"][1] + cur[0]["bbox"][3]) / 2
                            words.append(Word(x0, x1, y, "".join(c["c"] for c in cur)))
                            cur = []
                    else:
                        cur.append(ch)
    return words


def page_body_size(page) -> float:
    sizes: dict[float, int] = {}
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                if sp["text"].strip():
                    k = round(sp["size"], 1)
                    sizes[k] = sizes.get(k, 0) + len(sp["text"])
    return max(sizes, key=sizes.get) if sizes else 9.0


def vertical_segments(page) -> list[tuple[float, float, float]]:
    """Vertical ruling lines of the table: (x, y_top, y_bottom)."""
    segs = []
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 8:
                    segs.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 2.5 and r.height > 8:
                    segs.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
    return segs


def _edges_at(segs: list[tuple[float, float, float]], y: float) -> list[float]:
    xs: list[float] = []
    for x, y0, y1 in segs:
        if y0 - 3 <= y <= y1 + 3 and not any(abs(x - e) < 3 for e in xs):
            xs.append(x)
    return sorted(xs)


def bounds_at(segs: list[tuple[float, float, float]], y: float) -> list[float] | None:
    """Column edges for a row starting at height y: the x of every vertical line
    crossing the row's first lines. Read per row, not per page: column widths
    change from page to page, and pages 266-267 stack two differently-ruled
    tables. Sampled over y..y+15 because a row at the very top of a page can sit
    just above where the ruling lines start (bug: row 414 on p.272 was lost)."""
    best: list[float] = []
    for dy in (0, 5, 10, 15):
        xs = _edges_at(segs, y + dy)
        if len(xs) >= len(FIELDS) + 1:
            return xs[: len(FIELDS) + 1]  # an extra narrow column at the far right is empty
        best = xs if len(xs) > len(best) else best
    return None


def column_of(x0: float, x1: float, bounds: list[float]) -> int | None:
    mid = (x0 + x1) / 2
    if mid < bounds[0] - 2 or mid > bounds[-1] + 2:
        return None
    for k in range(len(bounds) - 1):
        if mid < bounds[k + 1]:
            return k
    return len(bounds) - 2


def cell_text(ws: list[Word]) -> str:
    ws = sorted(ws, key=lambda w: (round(w.y), w.x0))
    text = " ".join(w.text for w in ws)
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # "conse- quence" -> "consequence"
    text = re.sub(r"\d?\s*\*(\s*\*)+", " ", text)  # "1* * *" omission markers
    text = re.sub(r"\s+([.,;])", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = clean_text(text)
    if not DITTO_RE.match(text):  # "May arrest without warrant. Ditto.." -> drop the trailing ditto
        text = re.sub(r"\s*\bDitto\b\.*", "", text).strip()
    return text


def parse_page_rows(words: list[Word], segs) -> tuple[list[list[str]], list[str]]:
    """Returns (rows, carry). Rows start at each section number in the first
    column. `carry` is per-column text above the first row: the continuation of
    the previous page's last row."""
    anchors = []
    for w in words:
        if not ANCHOR_RE.match(w.text):
            continue
        b = bounds_at(segs, w.y)
        if b and column_of(w.x0, w.x1, b) == 0:
            anchors.append((w, b))
    anchors.sort(key=lambda a: a[0].y)
    table_bottom = max((y1 for _, _, y1 in segs), default=1e9)

    def is_heading(w: Word) -> bool:
        line = " ".join(x.text for x in sorted((v for v in words if abs(v.y - w.y) < 2), key=lambda v: v.x0))
        return bool(HEADING_RE.match(line))

    rows: list[list[str]] = []
    carry = [""] * (len(FIELDS) - 1)
    if anchors:  # continuation text at the top of the page
        b = anchors[0][1]
        cells: list[list[Word]] = [[] for _ in FIELDS]
        table_top = min((y0 for _, y0, _ in segs), default=0)
        for w in words:
            if table_top - 2 <= w.y < anchors[0][0].y - 4 and not is_heading(w):
                k = column_of(w.x0, w.x1, b)
                if k is not None:
                    cells[k].append(w)
        carry = [cell_text(c) for c in cells[1:]]
    for i, (a, b) in enumerate(anchors):
        y0 = a.y - 4
        y1 = anchors[i + 1][0].y - 4 if i + 1 < len(anchors) else table_bottom + 2
        cells = [[] for _ in FIELDS]
        for w in words:
            if w is a or not (y0 <= w.y < y1) or is_heading(w):
                continue
            k = column_of(w.x0, w.x1, b)
            if k is not None:
                cells[k].append(w)
        rows.append([ANCHOR_RE.match(a.text).group(1)] + [cell_text(c) for c in cells[1:]])
    return rows, carry


def parse_schedule2(pdf_path: Path) -> tuple[dict[str, ScheduleInfo], dict]:
    """Returns (rows by PPC section, report). Image-only pages can't be read
    without OCR; they are listed in the report rather than silently skipped."""
    import pymupdf as fitz

    doc = fitz.open(pdf_path)
    # Range: first page with a table whose rows start with PPC numbers, up to Schedule III.
    start = bounds = None
    for i in range(len(doc)):
        page = doc[i]
        if start is None:
            for t in page.find_tables().tables:
                data = t.extract()
                firsts = [str(r[0] or "").strip() for r in data]
                if sum(bool(re.match(r"^\d{2,3}[A-Z]?$", f)) for f in firsts) >= 2 and t.col_count >= 8:
                    start = i
                    bounds = sorted({round(c[0], 1) for c in t.cells if c})[:9]
                    break
        elif re.search(r"SCHEDULE\s*-?\s*III\b", page.get_text()):
            end = i
            break
    else:
        end = len(doc)
    if start is None:
        raise ValueError("Schedule II table not found in CrPC PDF")

    body = 10.0
    sizes: dict[float, int] = {}
    for i in range(start, min(start + 5, end)):
        for blk in doc[i].get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    sizes[round(sp["size"], 1)] = sizes.get(round(sp["size"], 1), 0) + len(sp["text"])
    if sizes:
        body = max(sizes, key=sizes.get)

    out: dict[str, dict[str, str]] = {}
    prev_vals: dict[str, str] = {}
    image_pages, last_num, last_sec = [], 0, None
    for i in range(start, end):
        page = doc[i]
        # Per-page cutoff: the table's text size changes from page to page (9pt on
        # p.209, 7pt on p.214/266), so one global body size either drops whole pages
        # or keeps superscript footnote digits. 0.85 x this page's body size drops
        # the superscripts (4.6-6pt on a 7pt page) and keeps every table word.
        words = page_words(page, 0.85 * page_body_size(page))
        segs = vertical_segments(page)
        if len(words) < 25 or not segs:  # no text layer, or no table frame (scanned image)
            image_pages.append(i + 1)
            last_sec = None  # can't know what continues across an unreadable page
            continue
        rows, carry = parse_page_rows(words, segs)
        if last_sec and any(carry):
            for f, v in zip(FIELDS[1:], carry):
                if v and not DITTO_RE.match(v):
                    out[last_sec][f] = f"{out[last_sec][f]} {v}".strip()
        for row in rows:
            sec = normalise_sec(row[0])
            if not sec:
                continue
            num = int(re.match(r"\d+", sec).group())
            if num < last_num - 50:
                break  # a new, non-PPC table started
            last_num = max(last_num, num)
            vals = dict(zip(FIELDS[1:], row[1:]))
            for f, v in vals.items():  # "Ditto .." = same as the row above
                if DITTO_RE.match(v):
                    vals[f] = prev_vals.get(f, "")
            if sec in out and (vals["offence"].lower().startswith("contd") or not vals["offence"]):
                last_sec = sec
                for f, v in vals.items():  # "115 contd." on the next page: append
                    if v and not DITTO_RE.match(v) and not v.lower().startswith("contd"):
                        out[sec][f] = f"{out[sec][f]} {v}".strip()
                continue
            if sec not in out:
                out[sec] = vals
                prev_vals = vals
                last_sec = sec
    report = {"pages": f"{start + 1}-{end}", "image_only_pages": image_pages, "rows": len(out)}
    return {k: ScheduleInfo(**v) for k, v in out.items()}, report
