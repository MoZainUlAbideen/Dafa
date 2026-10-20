# Dafa progress log

## Milestones

- [x] 1. Project scaffold: uv backend, FastAPI app, Render blueprint, Next.js frontend
- [x] 2. Retrieval core: reference router, Roman Urdu glossary, BM25, LawStore (tests)
- [x] 3. Answer pipeline: Groq client, prompts, citation verifier, repair round, search-only fallback (tests)
- [x] 4. Frontend: stamp-paper design, landing, /ask workspace, /read pages (production build passes)
- [ ] 5. Ingestion: official PDFs -> Constitution + PPC section JSON, CrPC Schedule II join (tests)
- [ ] 6. Golden set verified against extracted text; retrieval evals run and failures fixed
- [ ] 7. Full end-to-end evals with Groq; failures diagnosed and fixed
- [ ] 8. Backend live on Render
- [ ] 9. Frontend live on Vercel, connected to the live backend
- [ ] 10. README results section filled in, LinkedIn post

## Eval results

| Date | Mode | Cases | Pass rate | hit@5 | recall@5 | MRR | Verified |
|---|---|---|---|---|---|---|---|
| (first run pending) | | | | | | | |

## Bugs found and fixed

(Logged here as they are diagnosed: symptom, root cause, fix, test that guards it.)
