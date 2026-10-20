"""Citation verifier: deterministic checks on every drafted answer.

An LLM answer about the law is only useful if its citations are real.
Before anything reaches the user we check that:
  1. every [book:id] marker in the answer refers to a section we actually
     retrieved and showed the model (no invented sections)
  2. every quote the model claims is verbatim really appears in that section
  3. every number of years / rupees / days in the answer appears somewhere in
     the retrieved text (catches "7 years" when the law says "10 years")
No LLM is involved, so this layer is fast, free and fully unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MARKER_RE = re.compile(r"\[(ppc|constitution):([0-9]{1,3}[A-Za-z\-]{0,4})\]")
NUMBER_CLAIM_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(years?|months?|days?|lakh|crore|rupees|rs\.?)|(?:rs\.?|rupees)\s*(\d[\d,]*)",
    re.IGNORECASE,
)

WORD_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fourteen": "14",
    "fifteen": "15", "twenty": "20", "twenty-five": "25", "thirty": "30", "forty": "40",
    "fifty": "50", "hundred": "100", "thousand": "1000",
}


def normalise(text: str) -> str:
    """Make comparisons robust to quote styles, dashes and whitespace."""
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("\u00ad", "")  # soft hyphen
    # all dash variants -> "-" (bug: a correct quote with U+2011 "motor\u2011cycle" was rejected)
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2212\-]+", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .;:,\"'")


def _numbers_in(text: str) -> set[str]:
    t = text.lower()
    nums = {n.replace(",", "") for n in re.findall(r"\d[\d,]*", t)}
    for w, d in WORD_NUMBERS.items():
        if re.search(rf"\b{w}\b", t):
            nums.add(d)
    return nums


# Citation variants models produce instead of "[ppc:302]": gpt-oss's native
# 【ppc:302】, (ppc:302), [PPC 302], [ppc:302, ppc:379] ...
_KEY = r"(ppc|constitution)\s*[:\s]\s*(\d{1,3}\s*-?\s*[A-Za-z]{0,3})"
_GROUP_RE = re.compile(r"[\[\u3010(]\s*(" + _KEY + r"(?:\s*[,;]\s*" + _KEY + r")*)\s*[\]\u3011)]", re.IGNORECASE)
_ONE_RE = re.compile(_KEY, re.IGNORECASE)


def canonical_citations(answer: str) -> str:
    """Rewrite every citation variant into the canonical "[book:id]" form the
    verifier and the frontend understand."""
    def fix(m: re.Match) -> str:
        keys = []
        for b, i in _ONE_RE.findall(m.group(1)):
            i = re.sub(r"\s+", "", i).upper()
            if b.lower() == "ppc":
                i = re.sub(r"^(\d+)([A-Z]+)$", r"\1-\2", i)
            keys.append(f"[{b.lower()}:{i}]")
        return " ".join(keys)
    return _GROUP_RE.sub(fix, answer)


def attach_citations(answer: str, citations) -> str:
    """The model lists the keys it relied on in a separate JSON field (structured
    output is far more reliable than markers inside free text). If the answer
    text carries no inline [book:id] markers, show the listed keys at the end.
    The verifier still checks every one of them against the provided CONTEXT."""
    if MARKER_RE.search(answer) or not isinstance(citations, list):
        return answer
    canon = canonical_citations(" ".join(f"[{c}]" for c in citations if isinstance(c, str)))
    keys = list(dict.fromkeys(re.findall(r"\[(?:ppc|constitution):[^\]]+\]", canon)))  # dedupe, keep order
    return f"{answer}\n\nSources: {' '.join(keys)}" if keys else answer


@dataclass
class Verdict:
    ok: bool
    bad_citations: list[str] = field(default_factory=list)
    bad_quotes: list[str] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)
    no_citations: bool = False

    @property
    def problems(self) -> list[str]:
        out = []
        if self.bad_citations:
            out.append(f"Cited sections that were not provided: {', '.join(self.bad_citations)}")
        if self.bad_quotes:
            out.append(f"Quotes not found verbatim in the cited section: {self.bad_quotes}")
        if self.unsupported_numbers:
            out.append(f"Numbers not present in any provided section: {', '.join(self.unsupported_numbers)}")
        if self.no_citations:
            out.append("The answer cites no section. Cite the sections you used with their keys, e.g. [ppc:379].")
        return out


def verify(answer: str, quotes: list[dict], context: dict[str, str]) -> Verdict:
    """`context` maps 'ppc:302' -> the full text the model was shown."""
    canon = {k.lower().replace("-", ""): k for k in context}

    bad_cites = []
    for book, sid in MARKER_RE.findall(answer):
        key = f"{book}:{sid}".lower().replace("-", "")
        if key not in canon:
            bad_cites.append(f"{book}:{sid}")

    bad_quotes = []
    for q in quotes or []:
        key = str(q.get("key", "")).lower().replace("-", "")
        text = str(q.get("text", ""))
        src = context.get(canon.get(key, ""), "")
        if not text.strip():
            continue
        if not src or normalise(text) not in normalise(src):
            bad_quotes.append(text[:80])

    all_numbers: set[str] = set()
    for t in context.values():
        all_numbers |= _numbers_in(t)
    unsupported = []
    for m in NUMBER_CLAIM_RE.finditer(answer):
        num = (m.group(1) or m.group(3) or "").replace(",", "")
        if num and num not in all_numbers:
            unsupported.append(m.group(0).strip())

    # An answer with zero citations used to pass (nothing to reject). Bug found in
    # full evals: every claim must be traceable, so no citations = not verified.
    good_cites = [1 for book, sid in MARKER_RE.findall(answer) if f"{book}:{sid}".lower().replace("-", "") in canon]
    no_cites = bool(context) and not good_cites
    ok = not bad_cites and not bad_quotes and not unsupported and not no_cites
    return Verdict(ok, sorted(set(bad_cites)), bad_quotes, unsupported, no_cites)


def strip_bad_markers(answer: str, bad: list[str]) -> str:
    for b in bad:
        answer = answer.replace(f"[{b}]", "")
    return answer
