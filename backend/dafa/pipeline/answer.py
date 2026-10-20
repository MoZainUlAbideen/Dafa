"""The question -> answer pipeline.

    route  -> exact refs ("dafa 302") are fetched directly
    rewrite (LLM) -> language, scope, book, statutory keywords
    retrieve (BM25) -> top-k sections, refs first
    draft (LLM) -> answer with [book:id] citations + verbatim quotes
    verify (deterministic) -> one repair round, then strip anything unverified

If no API key is set, or Groq is down, the pipeline degrades to search-only
mode: it still returns the right sections, just without a written answer.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from dafa.config import settings
from dafa.llm import prompts
from dafa.llm.groq_client import GroqClient, LLMError, Usage
from dafa.models import Section
from dafa.pipeline.verify import attach_citations, canonical_citations, strip_bad_markers, verify
from dafa.retrieval.router import route
from dafa.retrieval.store import LawStore

log = logging.getLogger("dafa.pipeline")

MAX_SECTION_CHARS = 1200  # was 1800; smaller prompts fit Groq's free-tier 8K tokens/minute
DRAFT_K = 4  # sections sent to the answer writer (all retrieved ones are still shown to the user)
URDU_SCRIPT_RE = re.compile(r"[؀-ۿ]")
ROMAN_URDU_HINTS = re.compile(
    r"\b(kya|kia|hai|hain|mein|kaun|kaunsi|konsi|ki|ka|ke|ko|agar|lagti|lagta|saza|kitni|kab|kaise|mera|meri|mujhe|ho|gaya|gayi|liya|kar)\b",
    re.IGNORECASE,
)


@dataclass
class AnswerResult:
    query: str
    mode: str  # "answer" | "search_only" | "out_of_scope"
    answer: str
    language: str
    sections: list[Section]
    quotes: list[dict] = field(default_factory=list)
    verified: bool = False
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    raw_draft: str = ""  # the model's first draft before any fixing (for evals / debugging)
    llm_error: str = ""  # set when the LLM failed (e.g. daily rate limit), so callers can react


def detect_language(query: str) -> str:
    if URDU_SCRIPT_RE.search(query):
        return "ur"
    if len(ROMAN_URDU_HINTS.findall(query)) >= 2:
        return "roman_ur"
    return "en"


def format_context(sections: list[Section]) -> tuple[str, dict[str, str]]:
    """Build the CONTEXT block for the model, and the key -> text map the
    verifier checks against (the exact same text the model saw)."""
    blocks, ctx = [], {}
    for s in sections:
        body = s.text[:MAX_SECTION_CHARS]
        sched = ""
        if s.schedule:
            sc = s.schedule
            sched = (
                f"\nSCHEDULE (CrPC Schedule II): cognizable: {sc.cognizable}; bailable: {sc.bailable}; "
                f"compoundable: {sc.compoundable}; punishment: {sc.punishment}; triable by: {sc.court}"
            )
        block = f"[{s.key}] {s.label}: {s.title}\n{body}{sched}"
        blocks.append(block)
        ctx[s.key] = f"{s.title}\n{body}{sched}"
    return "\n\n---\n\n".join(blocks), ctx


class Pipeline:
    def __init__(self, store: LawStore, llm: GroqClient | None = None, top_k: int | None = None):
        self.store = store
        self.llm = llm
        self.top_k = top_k or settings.top_k

    # ---------- retrieval ----------
    def retrieve(self, query: str, book: str | None = None, keywords: list[str] | None = None, english_query: str | None = None) -> list[Section]:
        r = route(query)
        found: list[Section] = []
        for ref_book, ref_id in r.refs:
            s = self.store.get(ref_book, ref_id)
            if s is None and ref_book == "ppc":  # "article 302"-style mix-ups
                s = self.store.get("constitution", ref_id)
            if s and s not in found:
                found.append(s)
        search_q = f"{query} {english_query or ''}"
        if len(found) < self.top_k:
            hits = self.store.search(search_q, k=self.top_k, book=book, extra_terms=keywords, prefer=r.book_hint)
            for h in hits:
                if h.section not in found:
                    found.append(h.section)
                if len(found) >= self.top_k:
                    break
        return found

    # ---------- full answer ----------
    def answer(self, query: str) -> AnswerResult:
        t0 = time.monotonic()
        timings: dict[str, int] = {}
        usage = Usage()
        language = detect_language(query)
        book, keywords, english_q = None, None, None

        llm_ok = self.llm is not None and bool(self.llm.api_key)
        warnings: list[str] = []
        rewrite_error = ""

        if llm_ok and not route(query).refs:
            try:
                rw = self.llm.chat_json(prompts.REWRITE_SYSTEM, query, usage=usage, max_tokens=300)
                language = rw.get("language", language) if rw.get("language") in prompts.LANGUAGE_RULES else language
                if rw.get("in_scope") is False:
                    timings["total"] = int((time.monotonic() - t0) * 1000)
                    return AnswerResult(query, "out_of_scope", OUT_OF_SCOPE[language], language, [], timings_ms=timings, usage=_usage(usage))
                book = rw.get("book") if rw.get("book") in ("ppc", "constitution") else None
                keywords = [str(k) for k in rw.get("keywords", [])][:12]
                english_q = rw.get("english_query")
            except LLMError as e:
                log.warning("rewrite failed: %s", e)
                warnings.append("Query rewriting unavailable; used direct search.")
                rewrite_error = str(e)
        timings["rewrite"] = int((time.monotonic() - t0) * 1000)

        t1 = time.monotonic()
        sections = self.retrieve(query, book=book, keywords=keywords, english_query=english_q)
        timings["retrieve"] = int((time.monotonic() - t1) * 1000)

        if not sections:
            timings["total"] = int((time.monotonic() - t0) * 1000)
            return AnswerResult(query, "search_only", NO_MATCH[language], language, [], warnings=warnings, timings_ms=timings, usage=_usage(usage))

        if not llm_ok or "daily limit" in rewrite_error:  # no point calling the writer if the quota is gone
            timings["total"] = int((time.monotonic() - t0) * 1000)
            return AnswerResult(query, "search_only", SEARCH_ONLY[language], language, sections, warnings=warnings,
                                timings_ms=timings, llm_error=rewrite_error)

        t2 = time.monotonic()
        context_text, ctx = format_context(sections[:DRAFT_K])
        system = prompts.ANSWER_SYSTEM.replace("{language_rule}", prompts.LANGUAGE_RULES[language])
        user = f"QUESTION: {query}\n\nCONTEXT:\n{context_text}"
        try:
            draft = self.llm.chat_json(system, user, usage=usage)
            raw_draft = str(draft.get("answer", ""))
            answer_text = attach_citations(canonical_citations(raw_draft.strip()), draft.get("citations"))
            quotes = [q for q in draft.get("quotes", []) if isinstance(q, dict)]
            verdict = verify(answer_text, quotes, ctx)
            if not verdict.ok:  # one repair round with the exact problems listed
                repair = prompts.REPAIR_NOTE.format(problems="\n".join(verdict.problems))
                draft = self.llm.chat_json(system, f"{user}\n\nPREVIOUS ANSWER:\n{answer_text}\n\n{repair}", usage=usage)
                answer_text = attach_citations(canonical_citations(str(draft.get("answer", "")).strip()), draft.get("citations"))
                quotes = [q for q in draft.get("quotes", []) if isinstance(q, dict)]
                verdict = verify(answer_text, quotes, ctx)
            if not verdict.ok:
                answer_text = strip_bad_markers(answer_text, verdict.bad_citations)
                quotes = [q for q in quotes if str(q.get("text", ""))[:80] not in verdict.bad_quotes]
                warnings.extend(verdict.problems)
        except LLMError as e:
            log.warning("draft failed: %s", e)
            timings["total"] = int((time.monotonic() - t0) * 1000)
            warnings.append("The answer writer is unavailable right now; showing the matching sections.")
            return AnswerResult(query, "search_only", SEARCH_ONLY[language], language, sections, warnings=warnings,
                                timings_ms=timings, usage=_usage(usage), llm_error=str(e))
        timings["draft_verify"] = int((time.monotonic() - t2) * 1000)
        timings["total"] = int((time.monotonic() - t0) * 1000)

        cited = {k.lower() for k in re.findall(r"\[((?:ppc|constitution):[^\]]+)\]", answer_text)}
        ordered = [s for s in sections if s.key.lower() in cited] + [s for s in sections if s.key.lower() not in cited]
        return AnswerResult(
            query, "answer", answer_text, language, ordered, quotes=quotes,
            verified=verdict.ok, warnings=warnings, timings_ms=timings, usage=_usage(usage), raw_draft=raw_draft,
        )


def _usage(u: Usage) -> dict:
    return {"llm_calls": u.calls, "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}


SEARCH_ONLY = {
    "en": "Here are the sections that best match your question. Open a card to read the full text.",
    "ur": "آپ کے سوال سے متعلق قانون کی یہ دفعات ملی ہیں۔ مکمل متن پڑھنے کے لیے کارڈ کھولیں۔",
    "roman_ur": "Aap ke sawal se milti julti yeh dafaat mili hain. Poora text parhne ke liye card kholein.",
}
NO_MATCH = {
    "en": "I couldn't find a section in the Constitution or the Penal Code that matches this. Try describing it differently, or name a section number.",
    "ur": "آئین یا تعزیراتِ پاکستان میں اس سے متعلق کوئی دفعہ نہیں ملی۔ سوال مختلف الفاظ میں لکھیں یا دفعہ نمبر بتائیں۔",
    "roman_ur": "Constitution ya PPC mein is se milti koi dafa nahi mili. Sawal thora mukhtalif likhein ya dafa number batayein.",
}
OUT_OF_SCOPE = {
    "en": "I can only help with questions about Pakistan's Constitution and the Pakistan Penal Code.",
    "ur": "میں صرف آئینِ پاکستان اور تعزیراتِ پاکستان سے متعلق سوالات میں مدد کر سکتا ہوں۔",
    "roman_ur": "Main sirf Pakistan ke Constitution aur Penal Code ke sawalon mein madad kar sakta hoon.",
}
