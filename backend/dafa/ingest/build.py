"""Build the processed law data from the official PDFs.

    uv run python -m dafa.ingest.build

Reads   backend/data/raw/{constitution,ppc,crpc}.pdf
Writes  backend/data/processed/{constitution,ppc}.json
Prints  a summary: units found, numbering gaps, Schedule II rows joined.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dafa.config import settings
from dafa.ingest.parse_sections import numbering_gaps, parse
from dafa.ingest.pdf_text import extract_lines
from dafa.ingest.schedule2 import parse_schedule2
from dafa.models import Section


def build_book(book: str, pdf: Path) -> list[Section]:
    lines = extract_lines(pdf)
    secs = parse(lines, book)
    gaps = numbering_gaps(secs)
    print(f"  {book}: {len(secs)} units ({sum(s.omitted for s in secs)} omitted), "
          f"last = {secs[-1].id if secs else '-'}, numbering gaps: {gaps[:15] or 'none'}{' ...' if len(gaps) > 15 else ''}")
    return secs


def write(book: str, secs: list[Section], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{book}.json"
    path.write_text(json.dumps([s.model_dump() for s in secs], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  wrote {path}")


def main() -> None:
    raw, out = settings.raw_dir, settings.data_dir
    missing = [n for n in ("constitution.pdf", "ppc.pdf") if not (raw / n).exists()]
    if missing:
        sys.exit(f"Missing in {raw}: {', '.join(missing)}")

    print("Constitution")
    const = build_book("constitution", raw / "constitution.pdf")
    write("constitution", const, out)

    print("Penal Code")
    ppc = build_book("ppc", raw / "ppc.pdf")
    crpc = raw / "crpc.pdf"
    if crpc.exists():
        sched, rep = parse_schedule2(crpc)
        print(f"  Schedule II pages {rep['pages']}; image-only pages (no text, skipped): {rep['image_only_pages']}")
        joined = 0
        for s in ppc:
            info = sched.get(s.id) or sched.get(s.id.replace("-", ""))
            if info:
                s.schedule = info
                joined += 1
        unmatched = sorted(set(sched) - {s.id for s in ppc})
        print(f"  Schedule II: {len(sched)} rows, joined to {joined} PPC sections, unmatched rows: {unmatched[:15]}")
    else:
        print("  crpc.pdf not found: skipping Schedule II")
    write("ppc", ppc, out)


if __name__ == "__main__":
    main()
