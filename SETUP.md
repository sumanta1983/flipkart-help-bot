# RAG System — Setup Guide

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | 3.11+ | `python --version` |
| PostgreSQL | 14+ | `psql --version` |
| pgvector extension | any | see step 3 |
| OpenAI API key | — | [platform.openai.com](https://platform.openai.com) |

> If you are running the Healthiin monorepo, PostgreSQL is already running at `localhost:5433` via Docker. Skip straight to step 3.

---

## Step 1 — Clone / navigate to the project

```bash
cd /path/to/rag
```

---

## Step 2 — Create a Python virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

You should see `(.venv)` in your terminal prompt.

---

## Step 3 — Install pgvector in PostgreSQL

pgvector is a PostgreSQL extension. It needs to be installed once per PostgreSQL instance.

## OR install from requirements

```pip install -r requirements.txt```

### Option A — Using Docker (recommended for local dev)

If you do not have PostgreSQL yet, spin one up with pgvector pre-installed:

```bash
docker run -d \
  --name rag-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=rag \
  -p 5433:5432 \
  pgvector/pgvector:pg16
```

### Option B — Existing PostgreSQL (apt / brew)

```bash
# Ubuntu / Debian
sudo apt install postgresql-16-pgvector

# macOS (Homebrew)
brew install pgvector
```

Then connect and enable the extension:

```sql
-- Connect as superuser
psql -U postgres -h localhost -p 5432

-- Create the RAG database (if it does not exist)
CREATE DATABASE rag;

-- Connect to it and enable pgvector
\c rag
CREATE EXTENSION IF NOT EXISTS vector;
```

> The API also runs `CREATE EXTENSION IF NOT EXISTS vector` on startup automatically, so you only need the database to exist.

---

## Step 4 — Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs: FastAPI, LangChain, langchain-openai, langchain-postgres, pypdf, beautifulsoup4, playwright, psycopg2-binary, and others.

### Optional — Playwright for JavaScript-rendered sites

If you plan to ingest JS-heavy sites (Flipkart, Amazon, React/Vue SPAs), install the Chromium browser after `pip install`:

```bash
playwright install chromium
```

This is a one-time download (~130 MB). Static sites (Wikipedia, docs, blogs) do **not** need this.

---

## Step 5 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# REQUIRED
OPENAI_API_KEY=sk-...

# PostgreSQL — adjust host/port/user/password/dbname as needed
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/rag

# Optional overrides (defaults shown)
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
RETRIEVAL_K=5
```

> **Never commit `.env` to git.** It is already in `.gitignore`.

---

## Step 6 — Start the API server

```bash
uvicorn api.main:app --reload --port 8000
```

Expected output:

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

On first start, the server automatically runs `CREATE EXTENSION IF NOT EXISTS vector` on the database.

---

## Step 7 — Verify the setup

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/source-types
# {"source_types":["pdf","url","text","database"]}
```

Or open the interactive API docs in your browser:

```
http://localhost:8000/docs
```

---

## Step 8 — Ingest your first document

### From a PDF

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "pdf",
    "source": "/absolute/path/to/document.pdf",
    "collection": "my-docs"
  }'
```

### From a URL (static site)

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "url",
    "source": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
    "collection": "my-docs"
  }'
```

### From a URL (JavaScript-rendered site)

Add `"js": true` for sites that require a real browser to render content (Flipkart, Amazon, SPAs):

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "url",
    "source": "https://www.flipkart.com/helpcentre",
    "collection": "my-docs",
    "js": true
  }'
```

> Requires `playwright install chromium` to have been run once (see Step 4).

### From a text / Markdown file

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "text",
    "source": "/absolute/path/to/notes.md",
    "collection": "my-docs"
  }'
```

### From a SQL database

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "database",
    "source": "postgresql+psycopg2://user:pass@localhost:5433/mydb",
    "collection": "products",
    "db_query": "SELECT name, description FROM products WHERE active = true",
    "db_content_columns": ["name", "description"]
  }'
```

Response for all ingest calls:

```json
{ "collection": "my-docs", "chunks_stored": 42 }
```

### Scraping structured sites (e.g. Flipkart Help Centre)

For sites with dynamic navigation (React SPAs where you need to click through topics), use the dedicated scraper scripts in `scripts/`:

```bash
# Scrape all FAQs and save to data/flipkart_faq.json
python scripts/scrape_flipkart_faq.py

# Scrape AND automatically ingest into the RAG collection 'flipkart-faq'
python scripts/scrape_flipkart_faq.py --ingest

# Custom output path
python scripts/scrape_flipkart_faq.py --out /tmp/my_faqs.json
```

Output format (`data/flipkart_faq.json`):
```json
[
  {
    "topic": "Delivery related",
    "question": "Can I take the shipment after opening and checking the contents inside?",
    "answer": "As per company policy, a shipment can't be opened before delivery...",
    "url": "https://www.flipkart.com/helpcentre?catalog=...&faq=...&view=FAQ"
  }
]
```

---

## Step 9 — Ask a question

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the main topic of the document?",
    "collection": "my-docs"
  }'
```

Response:

```json
{
  "answer": "The document is about...",
  "sources": [
    { "source": "document.pdf", "snippet": "..." }
  ]
}
```

---

## Troubleshooting

### `connection refused` on port 5433
PostgreSQL is not running. Start it with Docker (see step 3) or via your system service manager:
```bash
sudo systemctl start postgresql
```

### `extension "vector" does not exist`
pgvector is not installed in PostgreSQL. Follow step 3 for your OS.

### `openai.AuthenticationError`
Your `OPENAI_API_KEY` in `.env` is missing or invalid.

### `ModuleNotFoundError`
Virtual environment is not activated. Run `source .venv/bin/activate`.

### `chunks_stored: 0`
The loader found no content. Check that:
- The file path is absolute and the file exists.
- The URL is publicly accessible.
- The SQL query returns rows.
- For JS-heavy sites, use `"js": true` in the request body.

### `Error: browserType.launch: Executable doesn't exist`
Playwright browser not installed. Run:
```bash
playwright install chromium
```

---

## Running in Production

```bash
# Run with multiple workers (no --reload)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Or with gunicorn:

```bash
pip install gunicorn
gunicorn api.main:app -k uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8000
```
