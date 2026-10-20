# Dafa progress log

## Milestones

- [x] 1. Project scaffold: uv backend, FastAPI app, Render blueprint, Next.js frontend
- [x] 2. Retrieval core: reference router, Roman Urdu glossary, BM25, LawStore (tests)
- [x] 3. Answer pipeline: Groq client, prompts, citation verifier, repair round, search-only fallback (tests)
- [x] 4. Frontend: stamp-paper design, landing, /ask workspace, /read pages (production build passes)
- [x] 5. Ingestion: official PDFs -> Constitution (328 articles) + PPC (639 sections) JSON, CrPC Schedule II joined to 410 sections (tests)
- [x] 6. Golden set verified against the source PDFs; retrieval evals run, failures diagnosed and fixed; held-out split added
- [ ] 7. Full end-to-end evals with Groq (run locally with GROQ_API_KEY); failures diagnosed and fixed (in progress: bugs 17-22 fixed)
- [ ] 8. Backend live on Render
- [ ] 9. Frontend live on Vercel, connected to the live backend
- [ ] 10. README results section filled in, LinkedIn post

## Source documents

| Book | Source | Version |
|---|---|---|
| Constitution of Pakistan, 1973 | Provincial Assembly of the Punjab (pakp.gov.pk), Ministry of Law & Justice text | Amended up to the 27th Amendment (2025) |
| Pakistan Penal Code, 1860 | Sindh Judicial Academy (sja.gos.pk) | Amended up to 14 Dec 2023 |
| Code of Criminal Procedure, 1898 (Schedule II) | Sindh Judicial Academy (sja.gos.pk) | Amended up to 31 Dec 2022 |

Schedule II page 252 of the CrPC PDF is a scanned image with no text layer; rows on it are missing (reported by the build).

## Eval results

Golden set: 56 cases (44 dev, 12 held-out). Expected sections and Schedule II values were checked against the PDF pages by eye.
"dev" cases were used while tuning; "held-out" cases were written afterwards and never tuned on.

| Date | Mode | Split | Cases | Pass rate | hit@5 | MRR | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-20 | retrieval | dev | 44 | 80% | 0.763 | 0.646 | first run on real data |
| 2026-10-20 | retrieval | dev | 44 | 98% | 0.974 | 0.810 | after router + glossary + stemming fixes |
| 2026-10-20 | retrieval | held-out | 12 | 58% | 0.583 | 0.371 | honest number: keyword search alone misses paraphrases |
| (next) | full (Groq) | both | 56 | | | | measures whether the LLM query rewrite closes the held-out gap |

Takeaway: the 98% dev number is optimistic because the glossary was extended using dev failures. The held-out
split shows the real vocabulary gap ("lied under oath" vs "false evidence", "punished twice" vs "double punishment").
That gap is what the LLM rewrite step (full mode) has to close; if it doesn't, add embeddings (hybrid search).

## Bugs found and fixed

Each has a regression test.

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | PPC parsing stalled after section 9 | START_RE `\d{0,2}\[?` let "10." be read as footnote "1" + section "0" | footnote digits only allowed when a `[` follows |
| 2 | Decoy test passed by accident after fix 1 | 40-number jump allowance accepted a numbered list line ("12.") inside section 5 | `_decoy()`: a jump is rejected if the next numbered line falls back between the two numbers |
| 3 | Constitution "articles" were Federal Legislative List entries | start picked the "1." with the longest body, which was a schedule entry | take the earliest "1." followed by real body text |
| 4 | Article titles missing | titles are 8pt margin notes, dropped with the small fonts | titles taken from the Arrangement of Articles (table of contents) |
| 5 | Running header leaked into text | page number on alternating sides ("...PAKISTAN 5" / "16 ...PAKISTAN") | header detection ignores digits and spacing |
| 6 | 12 Constitution + 4 PPC numbering gaps | numbers alone on a line ("61.") and prefixes ("[[90.", "*273.", '["311.') | generalised start pattern; title/body taken from the next line |
| 7 | PPC 302 lost its first words | heading and body on the same printed line in separate blocks; block order put body first | lines rebuilt by grouping spans on the same baseline, ordered left to right |
| 8 | PPC explanation text missing | 0.86 small-font cutoff dropped 11pt explanations (body 13pt) | cutoff 0.75, measured from the real font-size distribution |
| 9 | "Chapter XVI: of this Code" fake chapter | case-insensitive heading regex matched a cross-reference | heading detection is case-sensitive |
| 10 | Titles like "Kidnapping. Kidnapping is of two kinds" | separators tried in fixed order; a later colon won | earliest separator wins |
| 11 | Schedule II: 0 rows | heading text only on 2 pages; table finder dropped spaces ("Shallnot") | page range scan + words rebuilt from characters |
| 12 | Schedule II cells shifted into wrong columns | column widths change per page; pages 266-267 stack two tables | column edges read per row from the vertical ruling lines |
| 13 | Row 414 lost "3 years"; row 420 lost "of a" | case-insensitive "Of [A-Z]" heading filter dropped lines starting "of stolen..." | case-sensitive heading filter |
| 14 | Row 414 merged into the previous row | first row sat 3pt above where the ruling lines start | column lines sampled over the row's first 15pt |
| 15 | Misdiagnosis (reverted): lowering the global size cutoff to fix #13 dropped whole 7pt pages | table text size varies per page (9pt / 7pt) | per-page body size, cutoff 0.85x |
| 16 | "lawyer if the police arrest me" never found Article 10 | router hard-filtered to the PPC on the word "police" | router hints are a soft score boost, rights words point to the Constitution |
| 17 | Every full-eval case failed with HTTP 404 | Groq retired the default model `llama-3.3-70b-versatile` | default is now `openai/gpt-oss-120b`; eval preflight fails fast with a clear message; `python -m dafa.llm.groq_client` lists usable models |
| 18 | "max completion tokens reached before generating a valid document" | gpt-oss is a reasoning model; hidden reasoning tokens count against `max_tokens` (300/1200 was too small) | `reasoning_effort: low`, larger budget for reasoning models, one retry with double budget on `json_validate_failed` |
| 19 | Answers with no citation passed verification (lookup-06) | the verifier only rejected *bad* citations; zero citations had nothing to reject | no citations = not verified, triggers the repair round |
| 20 | Every lookup failed `cites_expected` at low reasoning effort | model drifted from the `[ppc:302]` format | all citation variants (【ppc:302】, (PPC: 489F), [ppc:378, ppc:379]) are canonicalised; raw first draft saved in eval rows for diagnosis |
| 21 | Correct quote rejected | source uses a non-breaking hyphen (U+2011) | quote normaliser maps every dash variant to "-" |
| 22 | Runs ended in a wall of HTTP 429 | free tier is 8K tokens/min and 200K tokens/day; client gave up after 10s and budgets were too large | honour retry-after; pace on `x-ratelimit-remaining-tokens`; smaller prompts (4 sections x 1,200 chars); daily-limit 429 stops the eval cleanly and `--resume` continues later |
