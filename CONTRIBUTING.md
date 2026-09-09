# Contributing

SkinVision AI is a personal portfolio project. Contributions are welcome
but this is intentionally a lightweight process, not an elaborate
workflow — see [README.md](README.md) for what the project is and
[docs/](docs/) for how each part works.

## Setup

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

API at http://localhost:8010, web at http://localhost:3010.

**Backend, locally (outside Docker):**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest
uvicorn app.main:app --reload
```

`pytest` requires a reachable PostgreSQL matching `DATABASE_URL` (e.g.
`docker compose up -d db`, then `alembic upgrade head`) — tests exercise
the real database rather than mocking the ORM.

**Frontend, locally:**

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev -- --port 3010
```

## Running the backend tests

```bash
docker compose exec api pytest -q                 # full suite (756 tests)
docker compose exec api alembic check                # confirm no pending migrations
```

## Running the evaluation harness

```bash
docker compose exec api pytest tests/evaluation/    # regression gate, part of the normal suite
docker compose exec api python -m evaluation           # standalone run + JSON report
```

Both run fully offline — no API key or network access needed. See
[docs/evaluation.md](docs/evaluation.md#maintaining-and-extending-the-evaluation-dataset)
before adding or changing a case.

## Running the frontend checks

```bash
cd frontend
npx tsc --noEmit    # TypeScript
npm run lint          # ESLint
npm run build           # production build
```

## Expectations for a change

- **Deterministic skincare logic** (ingredient compatibility, routine
  ordering, visual observations) lives in versioned Python/rule files
  under `backend/app/{ingredients,routine,vision}/` and
  `backend/rules/` — never in a prompt or LLM call. A new rule or
  threshold needs a source (for an ingredient rule, a real citation) and
  a test; see [docs/ingredients.md](docs/ingredients.md) and
  [docs/routine.md](docs/routine.md).
- **LLM/agent changes must preserve the trust boundary**: the model
  explains and orchestrates, it never originates a fact, score,
  citation, or severity — see
  [docs/agent.md](docs/agent.md#the-one-rule-this-document-exists-to-explain)
  and, if adding a new agent tool, its
  [developer runbook](docs/agent.md#adding-a-new-agent-tool-developer-runbook).
  A change to `app/llm/` or `app/agent/` should not weaken
  `app/llm/validation.py` / `app/agent/validation.py`'s anti-hallucination
  or diagnostic-claim checks.
- **Every change needs a test.** New deterministic logic needs a unit
  test with a real expected value (never hand-guessed — run the code and
  read back what it actually produced); a new agent tool needs the
  tests and evaluation case listed in its runbook; a bug fix needs a
  test that would have caught it.
- **Safety behavior is not optional to preserve**: disclaimers,
  diagnostic-claim rejection, rate limiting, upload/decompression-bomb
  protection, sanitized error responses, and the evaluation harness's
  104 cases should all still pass — see [docs/safety.md](docs/safety.md).
- Keep documentation honest: don't claim clinical accuracy, don't claim
  a feature exists before it does, and update the relevant doc in the
  same change as the code (see [docs/evaluation.md](docs/evaluation.md#maintaining-and-extending-the-evaluation-dataset)
  for when an evaluation expectation changing is legitimate versus a
  hidden regression).

## Submitting a change

Open a pull request with a clear description of what changed and why.
Before requesting review, confirm the backend suite, evaluation harness,
and frontend checks above all pass, and `alembic check` reports no
pending migrations.
