"""FastAPI app: the live backend the Vercel frontend talks to.

Endpoints
  GET  /health                       liveness + what's loaded
  GET  /books                        books with section counts
  GET  /books/{book}/toc             chapter/part navigator
  GET  /sections/{book}/{id}         one section (+ prev/next)
  GET  /search?q=&book=              BM25 search, no LLM
  POST /ask   {"query": "..."}       full grounded answer
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict, defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dafa.config import settings
from dafa.llm.groq_client import GroqClient
from dafa.llm.prompts import PROMPT_VERSION
from dafa.models import BOOK_TITLES, UNIT_LABEL, Section
from dafa.pipeline.answer import Pipeline
from dafa.retrieval.store import get_store

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("dafa.api")

app = FastAPI(title="Dafa API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_pipeline: Pipeline | None = None


def pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(get_store(), GroqClient() if settings.llm_enabled else None)
    return _pipeline


# ---------- tiny in-memory rate limiter + answer cache ----------
_hits: dict[str, deque] = defaultdict(deque)
_cache: OrderedDict[str, dict] = OrderedDict()
CACHE_SIZE = 256


def _rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_min:
        return True
    q.append(now)
    return False


def section_out(s: Section, full: bool = True) -> dict:
    d = {
        "book": s.book, "id": s.id, "key": s.key, "label": s.label, "title": s.title,
        "group": s.group, "page": s.page, "omitted": s.omitted,
        "schedule": s.schedule.model_dump() if s.schedule else None,
    }
    d["text"] = s.text if full else (s.text[:280] + ("…" if len(s.text) > 280 else ""))
    return d


class AskIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)


@app.get("/health")
def health():
    store = get_store()
    return {
        "status": "ok",
        "books": {b: sum(1 for s in store.sections if s.book == b) for b in store.books()},
        "llm": settings.llm_enabled,
        "model": settings.groq_model if settings.llm_enabled else None,
        "prompt_version": PROMPT_VERSION,
    }


@app.get("/books")
def books():
    store = get_store()
    out = []
    for b in store.books():
        rows = [s for s in store.sections if s.book == b]
        out.append({
            "id": b, "title": BOOK_TITLES[b], "unit": UNIT_LABEL[b],
            "count": sum(1 for s in rows if not s.omitted),
            "with_schedule": sum(1 for s in rows if s.schedule),
        })
    return out


@app.get("/books/{book}/toc")
def toc(book: str):
    if book not in BOOK_TITLES:
        raise HTTPException(404, "Unknown book")
    return get_store().toc(book)


@app.get("/sections/{book}/{sec_id}")
def get_section(book: str, sec_id: str):
    store = get_store()
    s = store.get(book, sec_id)
    if not s:
        raise HTTPException(404, f"{book} {sec_id} not found")
    prev, nxt = store.neighbours(book, s.id)
    return {
        **section_out(s),
        "prev": {"id": prev.id, "title": prev.title} if prev else None,
        "next": {"id": nxt.id, "title": nxt.title} if nxt else None,
    }


@app.get("/search")
def search(q: str, book: str | None = None, k: int = 8):
    if book and book not in BOOK_TITLES:
        raise HTTPException(400, "Unknown book")
    secs = pipeline().retrieve(q, book=book)[: max(1, min(k, 20))]
    return [section_out(s, full=False) for s in secs]


@app.post("/ask")
def ask(body: AskIn, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    norm = " ".join(body.query.lower().split())
    if norm in _cache:
        _cache.move_to_end(norm)
        return {**_cache[norm], "cached": True}
    if _rate_limited(ip):
        raise HTTPException(429, "Too many questions in a minute. Please wait a moment.")

    res = pipeline().answer(body.query)
    out = {
        "query": res.query, "mode": res.mode, "answer": res.answer, "language": res.language,
        "verified": res.verified, "warnings": res.warnings, "quotes": res.quotes,
        "sections": [section_out(s) for s in res.sections],
        "timings_ms": res.timings_ms, "cached": False,
    }
    # One structured log line per request: the raw material for monitoring.
    log.info(json.dumps({
        "event": "ask", "mode": res.mode, "lang": res.language, "verified": res.verified,
        "n_sections": len(res.sections), "warnings": len(res.warnings),
        "timings_ms": res.timings_ms, **res.usage, "prompt_version": PROMPT_VERSION,
    }))
    if res.mode == "answer" and res.verified:
        _cache[norm] = out
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return out
