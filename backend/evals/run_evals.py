"""Dafa eval harness.

Two modes:
  retrieval  (default, offline, free)  - did the right sections come back?
  full       (needs GROQ_API_KEY)      - plus: is the answer verified, does it
                                         cite the right section, mention the
                                         right facts, use the user's language,
                                         and refuse out-of-scope questions?

Usage (from backend/):
  uv run python -m evals.run_evals                 # retrieval mode
  uv run python -m evals.run_evals --mode full     # end-to-end with Groq
  uv run python -m evals.run_evals --only ppc-theft-01

Writes evals/results/latest.json, evals/results/report.html, and appends a
summary line to evals/results/history.jsonl so regressions are visible.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dafa.config import settings
from dafa.llm.groq_client import GroqClient, LLMError, preflight
from dafa.llm.prompts import PROMPT_VERSION
from dafa.pipeline.answer import Pipeline, detect_language
from dafa.retrieval.store import _canon, get_store

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden.jsonl"
RESULTS = HERE / "results"
K = 5


def load_cases(only: str | None) -> list[dict]:
    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("//")]
    return [c for c in cases if not only or c["id"] == only or c["id"].startswith(only)]


def ids_match(got: str, want: str) -> bool:
    return _canon(got) == _canon(want)


def grade_retrieval(case: dict, keys: list[str]) -> dict:
    want = case.get("expect", [])
    if not want:
        return {}
    got = keys[:K]
    hits = [w for w in want if any(ids_match(g, w) for g in got)]
    rr = 0.0
    for rank, g in enumerate(got, 1):
        if any(ids_match(g, w) for w in want):
            rr = 1 / rank
            break
    return {"hit": bool(hits), "recall": len(hits) / len(want), "rr": rr}


def grade_schedule(case: dict, store) -> dict:
    book, sid = case["section"].split(":")
    s = store.get(book, sid)
    if not s or not s.schedule:
        return {"pass": False, "detail": "no schedule row found"}
    fails = []
    for field, expected in case["schedule"].items():
        actual = getattr(s.schedule, field, "")
        if expected.lower() not in actual.lower():
            fails.append(f"{field}: expected '{expected}', got '{actual}'")
    return {"pass": not fails, "detail": "; ".join(fails)}


def grade_answer(case: dict, res) -> dict:
    g: dict = {}
    if case["type"] == "out_of_scope":
        g["refused"] = res.mode == "out_of_scope"
        return g
    g["verified"] = res.mode == "answer" and res.verified
    cited = {m.lower() for m in re.findall(r"\[((?:ppc|constitution):[^\]]+)\]", res.answer)}
    want = [w.lower() for w in case.get("expect", [])]
    g["cites_expected"] = any(any(ids_match(c, w) for c in cited) for w in want) if want else True
    for phrase in case.get("must_include", []):
        g.setdefault("facts", True)
        if phrase.lower() not in res.answer.lower():
            g["facts"] = False
    if case.get("language"):
        g["language"] = detect_language(res.answer) == case["language"] or res.language == case["language"]
    return g


def run(mode: str, only: str | None) -> dict:
    store = get_store()
    llm = GroqClient(min_interval_s=2.5) if mode == "full" else None
    if mode == "full" and not settings.llm_enabled:
        sys.exit("Full mode needs GROQ_API_KEY in backend/.env")
    if mode == "full":
        try:
            preflight(llm)
        except LLMError as e:
            sys.exit(f"Groq preflight failed for model '{settings.groq_model}': {e}\n"
                     "List the models your key can use with:  uv run python -m dafa.llm.groq_client\n"
                     "then set GROQ_MODEL in backend/.env")
    pipe = Pipeline(store, llm=llm, top_k=K)
    rows = []
    for case in load_cases(only):
        t0 = time.monotonic()
        row: dict = {"id": case["id"], "type": case["type"], "split": case.get("split", "dev"), "query": case.get("query", case.get("section"))}
        if case["type"] == "schedule":
            row.update(grade_schedule(case, store))
            row["pass"] = row["pass"]
        elif mode == "retrieval":
            if case["type"] == "out_of_scope":
                continue  # needs the LLM's scope judgement
            secs = pipe.retrieve(case["query"])
            keys = [s.key for s in secs]
            row["got"] = keys[:K]
            row.update(grade_retrieval(case, keys))
            row["pass"] = row.get("hit", False)
        else:
            res = pipe.answer(case["query"])
            keys = [s.key for s in res.sections]
            row["got"] = keys[:K]
            row["answer"] = res.answer
            row["warnings"] = res.warnings
            row.update(grade_retrieval(case, keys))
            row.update(grade_answer(case, res))
            checks = [v for k, v in row.items() if k in ("hit", "verified", "cites_expected", "facts", "language", "refused")]
            row["pass"] = all(checks) if checks else False
        row["ms"] = int((time.monotonic() - t0) * 1000)
        rows.append(row)
        mark = "PASS" if row["pass"] else "FAIL"
        print(f"{mark}  {row['id']:<28} {row.get('got', row.get('detail', ''))}")
        if not row["pass"]:  # say exactly which checks failed, so failures can be diagnosed
            failed = [k for k in ("hit", "verified", "cites_expected", "facts", "language", "refused") if row.get(k) is False]
            print(f"        failed checks: {failed or '-'}" + (f" | warnings: {row['warnings']}" if row.get("warnings") else ""))
    return summarise(rows, mode)


def summarise(rows: list[dict], mode: str) -> dict:
    def avg(key, subset=None):
        vals = [r[key] for r in (subset or rows) if key in r]
        return round(sum(vals) / len(vals), 3) if vals else None

    by_type: dict[str, dict] = {}
    for t in sorted({r["type"] for r in rows}):
        sub = [r for r in rows if r["type"] == t]
        by_type[t] = {"n": len(sub), "pass_rate": round(sum(r["pass"] for r in sub) / len(sub), 3)}
    by_split = {}
    for sp in sorted({r["split"] for r in rows}):
        sub = [r for r in rows if r["split"] == sp]
        by_split[sp] = {"n": len(sub), "pass_rate": round(sum(r["pass"] for r in sub) / len(sub), 3),
                        f"hit@{K}": avg("hit", sub), "mrr": avg("rr", sub)}
    summary = {
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "model": settings.groq_model if mode == "full" else None,
        "n": len(rows),
        "pass_rate": round(sum(r["pass"] for r in rows) / len(rows), 3) if rows else 0,
        f"hit@{K}": avg("hit"),
        f"recall@{K}": avg("recall"),
        "mrr": avg("rr"),
        "verified_rate": avg("verified"),
        "by_type": by_type,
        "by_split": by_split,  # dev = cases used while tuning; heldout = written after, never tuned on
    }
    return {"summary": summary, "rows": rows}


def write_report(result: dict) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(RESULTS / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(result["summary"], ensure_ascii=False) + "\n")
    s = result["summary"]
    rows_html = "".join(
        f"<tr class={'pass' if r['pass'] else 'fail'}><td>{'PASS' if r['pass'] else 'FAIL'}</td><td>{html.escape(r['id'])}</td>"
        f"<td>{html.escape(r['type'])}</td><td dir=auto>{html.escape(str(r.get('query', '')))}</td>"
        f"<td>{html.escape(', '.join(r.get('got', [])) or r.get('detail', ''))}</td>"
        f"<td dir=auto>{html.escape(r.get('answer', '')[:400])}</td></tr>"
        for r in result["rows"]
    )
    types = "".join(f"<li>{t}: {v['pass_rate']:.0%} of {v['n']}</li>" for t, v in s["by_type"].items())
    types += "".join(f"<li><b>{sp} split</b>: {v['pass_rate']:.0%} of {v['n']}</li>" for sp, v in s.get("by_split", {}).items())
    page = f"""<!doctype html><meta charset=utf-8><title>Dafa eval report</title>
<style>body{{font:15px/1.5 system-ui;margin:32px;color:#16352b;background:#f4f7f3}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #cfdcd3;padding:6px 8px;text-align:left;vertical-align:top}}tr.fail td:first-child{{color:#a2272d;font-weight:700}}
tr.pass td:first-child{{color:#1f6b4a;font-weight:700}}.k{{display:flex;gap:28px;flex-wrap:wrap}}.k div{{font-size:13px}}.k b{{display:block;font-size:26px}}</style>
<h1>Dafa eval report</h1><p>{s['when']} | mode: {s['mode']} | prompt {s['prompt_version']} | model: {s['model'] or 'n/a'}</p>
<div class=k><div><b>{s['pass_rate']:.0%}</b>pass rate ({s['n']} cases)</div><div><b>{s[f'hit@{K}'] if s[f'hit@{K}'] is not None else '-'}</b>hit@{K}</div>
<div><b>{s[f'recall@{K}'] if s[f'recall@{K}'] is not None else '-'}</b>recall@{K}</div><div><b>{s['mrr'] if s['mrr'] is not None else '-'}</b>MRR</div>
<div><b>{s['verified_rate'] if s['verified_rate'] is not None else '-'}</b>verified answers</div></div><ul>{types}</ul>
<table><tr><th></th><th>id</th><th>type</th><th>query</th><th>retrieved / detail</th><th>answer</th></tr>{rows_html}</table>"""
    (RESULTS / "report.html").write_text(page, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    ap.add_argument("--only")
    args = ap.parse_args()
    result = run(args.mode, args.only)
    write_report(result)
    s = result["summary"]
    print(f"\npass rate {s['pass_rate']:.0%} | hit@{K} {s[f'hit@{K}']} | recall@{K} {s[f'recall@{K}']} | MRR {s['mrr']} | verified {s['verified_rate']}")
    for sp, v in s["by_split"].items():
        print(f"  {sp:<8} {v['pass_rate']:.0%} of {v['n']} | hit@{K} {v[f'hit@{K}']} | MRR {v['mrr']}")
    print(f"report: {RESULTS / 'report.html'}")


if __name__ == "__main__":
    main()
