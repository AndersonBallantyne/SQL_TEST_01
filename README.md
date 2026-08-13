# Ask-Your-Database

A hand-built SQL agent over a reproducible Postgres stack — no LangChain, no framework. The
model proposes SQL; a read-only database role decides what's actually allowed to run. Seven
builds, one system: the agent itself, a real data pipeline, retrieval, observability, CI, a
chat front end, and a second agent that checks the first one's answers before they're shown.

Full write-up, build-by-build, plus the real incidents that changed the design:
**[andersonballantyne.github.io](https://andersonballantyne.github.io/)**

Try it live (synthetic data, read-only, rate-limited):
**[Ask-Your-Database demo](https://sqltest01-xsbrz2cqxejyktbhe7ekzm.streamlit.app/)**

## What's here

| Build | What it added |
|---|---|
| 1 | The agent itself — a hand-built tool-use loop against a read-only Postgres role |
| 2 / 2.5 | Raw-to-queryable ETL pipeline, plus a writable scratch schema for the agent's own derived results |
| 3 / 3.5 | pgvector retrieval over equipment data, then over the project's own docs |
| 4 | Structured tool-call logging, an eval harness, and a metrics rollup |
| 5 | Public repo, CI, and a real mid-build data-anonymization pivot |
| 6 | A Streamlit chat front end with persistent, tiered conversation memory |
| 7 | A second agent that verifies every answer against its own tool evidence before it's shown |

## Repo layout

```
src/          every first-party Python module and script, flat (they import each other
              directly - agent.py, tools.py, the data pipeline, the eval harnesses, app.py)
migrations/   001-015, applied in order against Postgres
tests/        pytest suite (pythonpath = src, configured in pytest.ini)
data/         the one official synthesized dataset - real structure, no real institutional data
docs/         per-build flow diagrams, handoff briefs, and the living command cheat sheet
legacy/       schema/seed files for a secondary SQL Server lab environment, not part of the agent
```

## Running it

```bash
cp .env.example .env   # fill in real values - see the comments in that file for what each does
docker compose up -d postgres
# apply migrations/001 through migrations/015 in order against that Postgres, e.g.:
for f in migrations/*.sql; do psql -h 127.0.0.1 -U devuser -d appdb -f "$f"; done
python src/ingest.py && python src/transform.py && python src/build_allocation_items.py
python src/embed_summaries.py && python src/extract_doc_chunks.py && python src/embed_chunks.py
docker compose up -d streamlit_app   # http://localhost:8501
```

`pytest -v` runs the full test suite against a local Postgres with the same migrations applied.
CI (`.github/workflows/ci.yml`) does the same thing from a genuinely empty environment on every
push, plus a gated eval harness (both the main agent's and the verifier's) on a relevant merge
to `main`.

## Trust boundary

The model never touches the database directly. It proposes SQL through a tool call; the agent
code is the first gate, and a dedicated read-only Postgres role is the second, independent of
whether the code gate is ever wrong. The write path (`agent_scratch`, for the agent's own
derived results and chat history) is a **separate** role with `CREATE`+`USAGE` on exactly one
schema — never an extension of the read-only role's grants.
