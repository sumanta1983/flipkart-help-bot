# RAG System — Claude Code Guide

## Overview

A **generic, multi-source Retrieval-Augmented Generation (RAG) system** built with Python, FastAPI, LangChain, pgvector, and OpenAI. It is not tied to any specific domain — the same pipeline handles PDFs, websites, plain text/Markdown, and SQL databases.

---

## Project Structure

```
rag/
├── api/
│   └── main.py               # FastAPI app — all HTTP endpoints
├── ingestion/
│   ├── pipeline.py           # Orchestrates load → chunk → embed → store
│   └── loaders/
│       ├── pdf_loader.py     # PDF files or directories of PDFs
│       ├── web_loader.py     # One or more URLs
│       ├── text_loader.py    # .txt / .md files or directories
│       └── db_loader.py      # SQL query results from any DB
├── retrieval/
│   └── retriever.py          # pgvector similarity search
├── generation/
│   └── chain.py              # LangChain prompt + OpenAI → answer
├── vector_store.py           # PGVector singleton factory (per collection)
├── config.py                 # Pydantic settings (reads .env)
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Layer       | Technology                                      |
|-------------|-------------------------------------------------|
| API         | FastAPI + Uvicorn                               |
| Orchestration | LangChain (loaders, splitters, chains)        |
| LLM         | OpenAI `gpt-4o`                                 |
| Embeddings  | OpenAI `text-embedding-3-small`                 |
| Vector DB   | pgvector (PostgreSQL extension)                 |
| Web (static) | requests + BeautifulSoup (`WebBaseLoader`)    |
| Web (JS)    | Playwright headless Chromium (opt-in via `js: true`) |
| Settings    | pydantic-settings (reads `.env`)                |
| Language    | Python 3.11+                                    |

---

## Setup

```bash
# 1. Create virtualenv
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 2a. Install Playwright browser (only needed for JS-rendered URLs)
playwright install chromium

# 3. Configure environment
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY and DATABASE_URL

# 4. Ensure PostgreSQL is running with pgvector
#    The API auto-runs: CREATE EXTENSION IF NOT EXISTS vector; on startup

# 5. Start the API
uvicorn api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

---

## API Endpoints

### `GET /health`
Returns `{"status": "ok"}`.

### `GET /source-types`
Lists supported source types: `pdf`, `url`, `text`, `database`.

### `POST /ingest`
Load documents into a pgvector collection.

```json
{
  "source_type": "pdf",
  "source": "/path/to/report.pdf",
  "collection": "flipkart-faq",
  "metadata": { "project": "finance" }
}
```

| source_type | `source` value                    | Extra fields |
|-------------|-----------------------------------|--------------|
| `pdf`       | Path to `.pdf` file or directory  | —            |
| `url`       | URL string or list of URLs        | `js` (bool, default `false`) — set `true` for JS-rendered sites |
| `text`      | Path to `.txt`/`.md` or directory | —            |
| `database`  | SQLAlchemy connection string      | `db_query`, `db_content_columns`, `db_metadata_columns` |

**URL examples:**

```json
// Static site (Wikipedia, docs, blogs)
{ "source_type": "url", "source": "https://example.com", "collection": "kb" }

// JavaScript-rendered site (Flipkart, Amazon, SPAs)
{ "source_type": "url", "source": "https://www.flipkart.com/helpcentre", "collection": "kb", "js": true }
```

Response:
```json
{ "collection": "flipkart-faq", "chunks_stored": 42 }
```

### `POST /query`
Ask a question — returns LLM answer + source references.

```json
{
  "question": "What are the key risks in Q3?",
  "collection": "flipkart-faq",
  "k": 5,
  "filter": { "project": "finance" }
}
```

Response:
```json
{
  "answer": "The key risks are...",
  "sources": [
    { "source": "report.pdf", "snippet": "..." }
  ]
}
```

### `POST /search`
Raw similarity search — returns chunks without LLM generation. Useful for debugging.

```json
{
  "query": "Q3 risks",
  "collection": "flipkart-faq",
  "k": 3
}
```

---

## Collections

Every ingest call targets a **collection** (default: `"default"`). Collections are separate namespaces in pgvector — each has its own embedding table. Use them to keep knowledge bases isolated:

```
"medical-docs"   → PDFs from medical knowledge base
"company-wiki"   → Crawled internal wiki pages
"product-db"     → SQL rows from products table
```

Query with the same collection name to search only that namespace.

---

## Scraper Scripts (`scripts/`)

For sites that require browser navigation (clicking through menus, SPAs), use a dedicated scraper instead of the generic URL ingest.

| Script | Target | Output |
|--------|--------|--------|
| `scrape_flipkart_faq.py` | Flipkart Help Centre | `data/flipkart_faq.json` |

```bash
# Scrape only
python scripts/scrape_flipkart_faq.py

# Scrape + ingest into collection 'flipkart-faq'
python scripts/scrape_flipkart_faq.py --ingest
```

Each scraper:
1. Uses Playwright to navigate and click through the site structure.
2. Extracts structured Q&A pairs (topic / question / answer / url).
3. Saves a JSON file to `data/`.
4. Optionally POSTs to `/ingest` as a `text` source.

---

## Adding a New Source Type

1. Create `ingestion/loaders/<type>_loader.py` with a `load_<type>(source) -> list[Document]` function.
2. Add the new `SourceType` enum value in `ingestion/pipeline.py`.
3. Add the branch in `ingest()` in `ingestion/pipeline.py`.
4. No changes needed to the API, retriever, or generation layers.

---

## Environment Variables

All settings live in `.env` (see `.env.example`):

| Variable               | Default                                        | Description                  |
|------------------------|------------------------------------------------|------------------------------|
| `OPENAI_API_KEY`       | —                                              | Required                     |
| `OPENAI_MODEL`         | `gpt-4o`                                       | Generation model             |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small`                     | Embedding model              |
| `DATABASE_URL`         | `postgresql://postgres:postgres@localhost:5433/rag` | pgvector connection     |
| `CHUNK_SIZE`           | `1000`                                         | Token chunk size             |
| `CHUNK_OVERLAP`        | `200`                                          | Overlap between chunks       |
| `RETRIEVAL_K`          | `5`                                            | Default top-k results        |

---

## Key Conventions

- **Web loader has two modes** — `js=False` uses requests+BeautifulSoup (fast, default); `js=True` uses Playwright headless Chromium (for JS-rendered pages). Playwright must be installed separately: `playwright install chromium`.
- **One loader per source type** — each lives in `ingestion/loaders/` and returns `list[Document]`.
- **Pipeline is the only place chunking happens** — never chunk inside a loader.
- **`get_store(collection)`** is cached with `@lru_cache` — one PGVector instance per collection per process.
- **`config.py` is the single source of truth** for all settings — never hardcode values elsewhere.
- **`generation/chain.py` is stateless** — it takes `(question, docs)` and returns a string. No retrieval inside generation.
- **Metadata filter** on `/query` and `/search` matches pgvector JSONB metadata fields set during ingestion.
