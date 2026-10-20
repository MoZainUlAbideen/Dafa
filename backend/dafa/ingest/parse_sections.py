"""Clean lines -> Sections, for both the PPC and the Constitution.

Both books share the same basic shape:

    CHAPTER XVII                      <- group heading (PART for the Constitution)
    OF OFFENCES AGAINST PROPERTY      <- group name
    378. Theft.- Whoever, intending   <- section start: number, title, separator, body
    to take dishonestly ...           <- body continues

Problems this module handles:
  - the table of contents at the front repeats every "378. Theft" line,
    so we start at the real section 1 (the one followed by actual body text)
  - lines inside a section can start with a number too (schedules, lists),
    so a new section is only accepted if its number comes next in order
  - titles end in different separators: ".-", ".—", ":", ":-", or just ". "
  - omitted sections ("[Omitted]") are kept but flagged
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dafa.ingest.pdf_text import Line, clean_text
from dafa.models import Section

# Prefix noise before the number: brackets, asterisks, quotes ("[[90.", "*273.", '["311.')
# and superscript footnote digits glued to a bracket ("11[15."). "(" is excluded so
# clause markers like "(1)" never look like sections. The rest may be empty when the
# number sits alone on its line ("61." with the text on the next line).
# (Bug fixed: "\d{0,2}\[?" let "10." be read as footnote "1" + section "0".)
START_RE = re.compile(r"^[^\w(]*(?:\d{1,2}\s?\[[^\w(]*)?(?P<id>\d{1,3}(?:-?[A-Z]{1,3})?)\s*\.(?!\d)\s*(?P<rest>.*)$")
# Case-sensitive on purpose: real headings are in capitals; "Chapter XVI of this Code"
# at the start of a wrapped body line is a cross-reference, not a heading (bug found in PPC).
GROUP_RE = re.compile(r"^\W*(?P<kind>CHAPTER|PART)\s+(?P<num>[IVXLC]+(?:-?[A-Z]{1,2})?|\d{1,2}[A-Z]?)\b\.?\s*(?:[-–—:.]+\s*)?(?P<rest>.*)$")
SUBHEAD_RE = re.compile(r"^\s*Of\s+[A-Z][\w ,'\-]{2,70}$")
END_RE = {
    # Only a standalone uppercase heading ends the body; "the First Schedule" inside a sentence must not.
    # (may carry an amendment bracket or asterisk: "[FIRST SCHEDULE", "*FIFTH SCHEDULE")
    "constitution": re.compile(r"^\W*(?:THE\s+)?(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH)\s+SCHEDULE\W*$"),
    "ppc": re.compile(r"^\W*(?:THE\s+)?SCHEDULE\W*$"),
}
OMITTED_RE = re.compile(r"^\W*(omitted|repealed|rep\.)\W*$|^\W*\[?\s*omitted", re.I)
SEPARATORS = [r"\s*[.:]\s*[-–—]+\s*", r":\s+", r"\s+[-–—]+\s+"]

MAX_JUMP = 40


def sort_key(sec_id: str) -> tuple[int, str]:
    m = re.match(r"(\d+)-?([A-Z]*)", sec_id.upper())
    return (int(m.group(1)), m.group(2)) if m else (0, "")


def split_title(rest: str) -> tuple[str, str]:
    """'Theft.- Whoever intending ...' -> ('Theft', 'Whoever intending ...').
    Takes the EARLIEST separator: checking separators in a fixed order made
    "Kidnapping. Kidnapping is of two kinds: ..." split at the colon (bug, PPC 359)."""
    rest = rest.strip()
    candidates = []
    # extra rules: some bodies start "whoever" (336-B); some start straight at clause "(1)" (489-E)
    for sep in SEPARATORS + [r"\.\s+(?=[A-Z(\"'\u201c]|whoever\b)", r"[.:]?\s+(?=\(1\)\s)"]:
        m = re.search(sep, rest)
        if m and 1 <= m.start() <= 200:
            candidates.append(m)
    if candidates:
        m = min(candidates, key=lambda x: x.start())
        return rest[: m.start()].strip(" .:"), rest[m.end():].strip()
    if rest.endswith((".", ":")) and len(rest) <= 200:
        return rest.rstrip(".: "), ""
    return rest, ""


def tidy_heading(t: str) -> str:
    t = clean_text(t).strip(" .-–—:")
    if t.isupper():
        small = {"of", "and", "the", "to", "in", "for", "or", "by", "on", "against", "relating", "with"}
        words = t.lower().split()
        t = " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(words))
    return t


@dataclass
class _Draft:
    id: str
    title: str
    page: int
    group: str
    body: list[str] = field(default_factory=list)


def parse(lines: list[Line], book: str) -> list[Section]:
    texts = [ln.text for ln in lines]

    # 1) find the real start: the occurrence of section 1 with the most text before the next start
    starts = [i for i, t in enumerate(texts) if (m := START_RE.match(t)) and m.group("id") == "1"]
    if not starts:
        raise ValueError(f"{book}: could not find section/article 1")

    def body_len(i: int) -> int:
        n = 0
        for t in texts[i + 1 : i + 15]:
            if START_RE.match(t):
                break
            n += len(t)
        return n + len(texts[i])

    # Earliest "1." followed by real body text. TOC entries are short; and the
    # longest-body heuristic used before picked a schedule list's "1." instead (bug).
    begin = next((i for i in starts if body_len(i) >= 150), max(starts, key=body_len))
    # The Constitution PDF prints article titles as margin notes (dropped with the
    # small fonts), so titles come from the "Arrangement of Articles" before the body.
    inline_titles = book != "constitution"
    vocab = {w.lower() for t in texts[begin:] for w in re.findall(r"[A-Za-z]{4,}", t)}
    toc_titles = {} if inline_titles else toc_title_map(texts[:begin], vocab)
    # Keep the nearest group heading before section 1 (e.g. "PART I Introductory").
    group = ""
    for j in range(begin - 1, max(begin - 6, -1), -1):
        if GROUP_RE.match(texts[j]):
            group = _group_name(texts, j)
            break

    drafts: list[_Draft] = []
    part = ""  # Constitution: remember the PART when a CHAPTER inside it starts
    i = begin
    end_re = END_RE.get(book)
    while i < len(texts):
        t = texts[i]
        if end_re and end_re.match(t) and drafts:
            break
        g = GROUP_RE.match(t)
        if g:
            name = _group_name(texts, i)
            if g.group("kind").upper() == "PART":
                part = name
                group = name
            else:
                group = f"{part}, {name}" if (book == "constitution" and part) else name
            i += _group_span(texts, i)
            continue
        m = START_RE.match(t)
        if m and _accept(m.group("id"), drafts) and not _decoy(m.group("id"), drafts, texts, i):
            rest = m.group("rest")
            if not rest.strip() and i + 1 < len(texts) and not START_RE.match(texts[i + 1]):
                rest = texts[i + 1]  # number alone on its line: title/body is on the next one
                i += 1
            if inline_titles:
                title, body = split_title(rest)
                nxt = texts[i + 1] if i + 1 < len(texts) else ""
                if not body and nxt and not START_RE.match(nxt) and not GROUP_RE.match(nxt):
                    # Title wrapped onto the next line: "...in respect of an official" / "act. Whoever..."
                    t2, b2 = split_title(f"{rest} {nxt}")
                    if b2 and len(t2) - len(rest) <= 60:
                        title, body = t2, b2
                        i += 1
            else:
                title, body = toc_titles.get(m.group("id"), ""), rest
            drafts.append(_Draft(m.group("id"), title, lines[i].page, group, [body] if body else []))
            i += 1
            continue
        if SUBHEAD_RE.match(t) and i + 1 < len(texts) and START_RE.match(texts[i + 1]):
            i += 1  # PPC italic sub-heading like "Of Theft"
            continue
        if drafts:
            drafts[-1].body.append(t)
        i += 1

    return [_finish(d, book) for d in drafts]


def _accept(sec_id: str, drafts: list[_Draft]) -> bool:
    if not drafts:
        return sec_id == "1"
    prev = sort_key(drafts[-1].id)
    cur = sort_key(sec_id)
    return cur > prev and cur[0] - prev[0] <= MAX_JUMP


def toc_title_map(toc_lines: list[str], vocab: set[str] | None = None) -> dict[str, str]:
    """'25A.    Right to education.' (possibly wrapped over 2 lines) -> {'25A': 'Right to education'}."""
    titles: dict[str, str] = {}
    current: str | None = None
    for t in toc_lines:
        m = START_RE.match(t)
        if m:
            current = m.group("id")
            titles[current] = m.group("rest").strip()
        elif current and not GROUP_RE.match(t) and not titles[current].endswith(".") and len(t) < 90:
            titles[current] = f"{titles[current]} {t.strip()}"
        else:
            current = None
    vocab = vocab or set()

    def dehyphen(m: re.Match) -> str:
        joined = m.group(1) + m.group(2)
        # "Funda- mental" -> "Fundamental" only if that word exists in the book;
        # otherwise it's a real hyphen: "self- incrimination" -> "self-incrimination".
        return joined if joined.lower() in vocab else f"{m.group(1)}-{m.group(2)}"

    out = {}
    for k, v in titles.items():
        v = clean_text(re.sub(r"\.{3,}.*$", "", v)).strip(" .")
        out[k] = re.sub(r"(\w+)-\s+(\w+)", dehyphen, v)
    return out


def _decoy(sec_id: str, drafts: list[_Draft], texts: list[str], i: int, look: int = 60) -> bool:
    """A numbered line that jumps ahead (5 -> 12) is a decoy if the next
    numbered line falls back between them (6): then "12." was a list item
    inside section 5's body, not a new section."""
    if not drafts:
        return False
    prev, cur = sort_key(drafts[-1].id), sort_key(sec_id)
    if cur[0] - prev[0] <= 1:
        return False
    for t in texts[i + 1 : i + 1 + look]:
        m = START_RE.match(t)
        if m:
            nxt = sort_key(m.group("id"))
            return prev < nxt < cur
    return False


def _heading_lines(texts: list[str], i: int) -> list[str]:
    """Name lines of a CHAPTER/PART heading. The name may be on the same line,
    on the next line, or wrap over two uppercase lines
    ("OF OFFENCES RELATING TO DOCUMENTS AND TO" / "PROPERTY MARKS")."""
    g = GROUP_RE.match(texts[i])
    names = [g.group("rest").strip()] if g.group("rest").strip() else []
    j = i + 1
    while j < len(texts) and len(names) < 3:
        t = texts[j].strip()
        if START_RE.match(t) or GROUP_RE.match(t) or SUBHEAD_RE.match(t) or len(t) > 90:
            break
        letters = [c for c in t if c.isalpha()]
        is_caps = letters and sum(c.isupper() for c in letters) / len(letters) > 0.8
        if names and not (is_caps and names[-1].isupper()):
            break  # only keep wrapping while the heading is in capitals
        names.append(t)
        j += 1
    return names


def _group_name(texts: list[str], i: int) -> str:
    g = GROUP_RE.match(texts[i])
    kind = g.group("kind").capitalize()
    num = g.group("num").upper()
    rest = " ".join(_heading_lines(texts, i))
    return f"{kind} {num}: {tidy_heading(rest)}" if rest else f"{kind} {num}"


def _group_span(texts: list[str], i: int) -> int:
    """How many lines the heading occupies."""
    g = GROUP_RE.match(texts[i])
    extra = len(_heading_lines(texts, i)) - (1 if g.group("rest").strip() else 0)
    return 1 + extra


OMIT_NOTE_RE = re.compile(r"\b(omitted|rep\.|repealed)\s+(by|vide)\b", re.I)


def display_id(sec_id: str, book: str) -> str:
    """PPC lettered sections are cited with a hyphen ("489-F"); the Constitution without ("25A")."""
    return re.sub(r"^(\d+)([A-Z]+)$", r"\1-\2", sec_id) if book == "ppc" else sec_id.replace("-", "")


def _finish(d: _Draft, book: str) -> Section:
    text = clean_text(" ".join(d.body))
    title = clean_text(d.title)
    head = f"{title} {text[:120]}"
    # "[Definition of Queen.] Omitted by A.O., 1961" / "Rep. by A.O., 1937" / "[Omitted]"
    omitted = bool(OMITTED_RE.match(title)) or (bool(OMIT_NOTE_RE.search(head)) and len(text) < 260)
    if omitted:
        note = f"{title}. {text}".strip(". ") if title and not OMITTED_RE.match(title) else text
        title, text = "Omitted", note
    return Section(book=book, id=display_id(d.id, book), title=title or "Untitled", text=text, group=d.group, page=d.page, omitted=omitted)


def numbering_gaps(sections: list[Section]) -> list[str]:
    """Report jumps in plain numbering (e.g. 377 -> 379) to spot parsing misses."""
    gaps, prev = [], None
    for s in sections:
        n = sort_key(s.id)[0]
        if prev is not None and n - prev > 1:
            gaps.append(f"{prev}->{n}")
        prev = n
    return gaps
