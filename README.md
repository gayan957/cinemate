# CineMate

A multi-agent AI assistant that recommends **films and TV series**. You
describe what you feel like watching in plain English — for example
*"something like Interstellar but less sad, under two hours"* — and CineMate
replies with three suggestions, a short friendly explanation, and a poster for
each. It never gives away the ending.

Every recommendation comes from a real record in its own database, so the
system does not invent titles.

---

## What makes it different

Instead of one large program, the work is split between four small programs
called **agents**, each with a single job. The large language model is used
only for the two things it does well — understanding the request and writing
the answer — while the actual recommendations always come from the database.

| Agent | Port | Job |
|---|---|---|
| **Guardian** | 8001 | The front door. Accounts, login tokens, input cleaning, attack blocking, output checks, audit log, encryption. The web page only ever talks to this agent. |
| **Orchestrator** | 8000 | The brain. Turns your request into a plan, applies age limits, calls the other agents, and writes the final answer. |
| **Retrieval** | — | The librarian. Searches the database with six methods. Started by the Orchestrator over MCP; has no web port. |
| **Analysis** | 8002 | The review reader. Sentiment, named entities, and spoiler-free summaries of user reviews. |

```
          You (web browser)
                 │
                 ▼
        Frontend (Streamlit)        port 8501
                 │  HTTP
                 ▼
        GUARDIAN                    port 8001   ← the only public entry point
                 │  HTTP
                 ▼
        ORCHESTRATOR                port 8000
           │ MCP          │ HTTP
           ▼              ▼
        RETRIEVAL      ANALYSIS      port 8002
           │
           ▼
        PostgreSQL + pgvector
```

---

## Features

- Understands everyday language, including moods and time limits.
- Handles **films and TV series** together.
- **Six search methods** (BM25, full-text, dense/embeddings, hybrid, reranked,
  and a full pipeline) so retrieval quality can be compared.
- Every recommendation is **grounded** in a real database row.
- **Spoiler-free** review summaries.
- Secure accounts: bcrypt passwords, 24-hour JWT tokens, a free-tier daily
  limit, and encrypted saved preferences.
- **Age-appropriate** filtering applied inside the search.
- Posters for each recommended title (from TMDB).
- A privacy-respecting audit log.

---

## Requirements

- **Python 3.11 or 3.12** (not 3.13 or 3.14 — some libraries have no builds for
  them yet).
- **PostgreSQL 16+** with the **pgvector** extension, or access to the team's
  Aiven database.
- **`psql`** (PostgreSQL client) — only needed to create the tables.
- A free **Groq** API key (the language model) and a free **TMDB** API key
  (the film data).
- About 3 GB of free disk space for the Python libraries and AI models, and
  8 GB of RAM or more.

---

## Setup

Run everything from the project folder.

### 1. Get the code and create the environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

This takes 5–10 minutes because it downloads PyTorch and the NLP models.

> **macOS / iCloud note:** do not keep the project in an iCloud-synced folder
> such as `~/Documents` or `~/Desktop`. iCloud removes local copies of files to
> save space, and Python then hangs while importing them. Either move the
> project out of those folders, or name the virtual environment `.venv.nosync`
> (which iCloud ignores) and point `.venv` at it:
> ```bash
> python3.11 -m venv .venv.nosync
> ln -s .venv.nosync .venv
> ```

### 2. Create the `.env` file

Create a file called `.env` in the project folder. **Never commit or share
it** — it is listed in `.gitignore`.

```
GROQ_API_KEY=your-groq-key
TMDB_API_KEY=your-tmdb-key
DATABASE_URL=postgres://user:password@host:port/defaultdb?sslmode=require
JWT_SECRET=a-long-random-string
ENCRYPTION_KEY=a-fernet-key
```

`JWT_SECRET` and `ENCRYPTION_KEY` **must be the same on every team machine**.
To generate them once:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
```

> If `ENCRYPTION_KEY` ever changes, data already encrypted with the old key can
> no longer be read.

### 3. Create the database tables

Only done once per database (skip if the team database already has its tables):

```bash
psql "$DATABASE_URL" -f data/schema.sql
```

### 4. Load the film and TV data

```bash
python data/ingest_tmdb.py --pages 5     # small test set (~100 of each)
python data/inspect_db.py                # check the counts
```

The full dataset (about 6,000 films and 4,000 series) takes several hours:

```bash
python data/ingest_tmdb.py               # uses MOVIE_PAGES and TV_PAGES from config
```

Loading is **safe to stop and resume** — press Ctrl+C and run the same command
again to carry on. Titles already loaded are skipped. Add `--reset` to start
from empty (keeps accounts and logs).

> **Restart CineMate after loading new titles** — the keyword index is built
> when the Retrieval agent starts.

---

## Running it

```bash
python run_all.py
```

Then open **http://localhost:8501**, create an account, and ask a question.
Press **Ctrl+C** to stop everything. If a service fails to start, `run_all.py`
prints its exit code and stops, so scroll up to see the error.

A question takes about 15–20 seconds, most of which is starting the Retrieval
agent (it reloads for every question).

---

## Testing

With CineMate running, in a second terminal:

```bash
python test_system.py            # full end-to-end test; every line should say PASS
```

Other checks:

```bash
python agents/orchestrator/hello_llm.py   # is the Groq key working?
python agents/retrieval/compare.py        # compare the six search methods
python agents/retrieval/test_mcp.py       # does the MCP server work?
python agents/guardian/test_guardian.py   # security checks
```

---

## Project layout

```
cinemate/
├── agents/
│   ├── guardian/        main.py, auth.py, sanitizer.py, audit.py
│   ├── orchestrator/    main.py, planner.py, mcp_client.py, prompts/
│   ├── retrieval/       search.py (six methods), mcp_server.py, compare.py
│   └── analysis/        main.py, nlp_tools.py
├── data/                schema.sql, ingest_tmdb.py, inspect_db.py
├── frontend/app.py      the Streamlit web page
├── shared/              config.py (all settings), schemas.py (message shapes)
├── docs/                guides and reports
├── run_all.py           starts every service
└── test_system.py       end-to-end test
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Commands or imports hang with no error (macOS) | iCloud evicted the files. Run `find . -flags +dataless`; move the project out of `~/Documents`, or use `.venv.nosync` (see Setup). |
| `pip` fails to build a package | You are on Python 3.13/3.14. Recreate `.venv` with `python3.11`. |
| "X did not start in time" / "X crashed" | Read the error above it — usually a missing `.env` value or a port already in use. |
| `Address already in use` | An old copy is running: `lsof -i :8001`, then `kill <PID>`. |
| Database connection / SSL error | Check `DATABASE_URL`: use the Aiven port (not 5432) and keep `?sslmode=require`. |
| Logins fail on one machine only | That machine's `JWT_SECRET` differs from the others. |
| New titles don't appear | Restart `run_all.py` after ingestion. |

---

## Configuration

Every setting lives in [`shared/config.py`](shared/config.py): ports, model
names, retrieval settings (candidates, final count, fusion and variety
constants), ingestion page counts, and security limits. Secrets come from
`.env` and are never written there.

The system uses `openai/gpt-oss-120b` on Groq, `all-MiniLM-L6-v2` for
embeddings, and local models (spaCy, DistilBERT, DistilBART) for review
analysis.

---

## Notes

- All film and TV data comes from **TMDB**. This product uses the TMDB API but
  is not endorsed or certified by TMDB.
- CineMate is a recommendation assistant, not an authority. It suggests titles;
  the choice is yours.
```

