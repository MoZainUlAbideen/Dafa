# CLAUDE.md: how we build Dafa

Same workflow as EdgarIQ, Rehnuma, Parity, Earshot and Dehqan.

## Project
Dafa: grounded Q&A over Pakistan's Constitution and Penal Code, with CrPC
Schedule II bail/arrest facts. Monorepo: `backend/` (FastAPI, Render) and
`frontend/` (Next.js, Vercel).

## Rules
1. Use uv for Python: `uv sync`, `uv run ...`. Never pip or venv by hand.
2. Real tests for every module. `uv run pytest -q` must pass before every commit.
3. Bugs are diagnosed, not guessed: reproduce, find the root cause, fix, add a
   test, log it in PROGRESS.md under "Bugs found and fixed".
4. Eval numbers are honest. Never edit the golden set to make a failing case
   pass unless the expected answer was wrong against the official text.
5. Legal text is never paraphrased into the data files. Processed JSON holds
   the official wording, cleaned only of amendment markers and footnotes.
6. Explain every change in simple words so it can be explained in interviews.
7. After each finished task, update the PROGRESS.md checklist.
8. Small commits with clear messages; push daily.

## Commands
- Backend dev: `cd backend && uv run uvicorn dafa.api.main:app --reload --port 8000`
- Tests: `cd backend && uv run pytest -q`
- Evals: `cd backend && uv run python -m evals.run_evals [--mode full]`
- Rebuild data: `cd backend && uv run python -m dafa.ingest.build`
- Frontend dev: `cd frontend && npm run dev`
- Frontend build check: `cd frontend && npm run build`

## Secrets
`backend/.env` (GROQ_API_KEY) and `frontend/.env.local` are git-ignored.
Never commit keys.
