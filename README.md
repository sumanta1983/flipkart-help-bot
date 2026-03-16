# RAG System

A generic, multi-source **Retrieval-Augmented Generation (RAG)** system built with Python, FastAPI, LangChain, pgvector, and OpenAI. Ingest documents from PDFs, websites, plain text/Markdown, or SQL databases — then ask questions and get grounded answers with source citations.

## How it works

```
Ingest: Source → Load → Chunk → Embed → pgvector
Query:  Question → Embed → Similarity search → GPT-4o → Answer + sources
```

See [HOW_IT_WORKS.md](HOW_IT_WORKS.md) for a detailed breakdown.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Orchestration | LangChain |
| LLM | OpenAI `gpt-4o` |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector DB | pgvector (PostgreSQL) |
| Web (static) | requests + BeautifulSoup |
| Web (JS-rendered) | Playwright headless Chromium |
| Settings | pydantic-settings |

## Quick Start

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Install Playwright for JS-rendered sites
playwright install chromium

# 4. Start PostgreSQL with pgvector
docker run -d \
  --name rag-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=rag \
  -p 5433:5432 \
  pgvector/pgvector:pg16

# 5. Configure environment
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and DATABASE_URL

# 6. Start the API
uvicorn api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

Full setup instructions: [SETUP.md](SETUP.md)

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/source-types` | List supported source types |
| `POST` | `/ingest` | Load documents into a collection |
| `POST` | `/query` | Ask a question, get an LLM answer + sources |
| `POST` | `/search` | Raw similarity search (no LLM) |

### Ingest a PDF

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type": "pdf", "source": "/path/to/doc.pdf", "collection": "my-docs"}'
```

### Ingest a URL

```bash
# Static site
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type": "url", "source": "https://example.com", "collection": "my-docs"}'

# JavaScript-rendered site (requires playwright install chromium)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_type": "url", "source": "https://www.flipkart.com/helpcentre", "collection": "my-docs", "js": true}'
```

### Ask a question

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the return policy?", "collection": "my-docs"}'
```

```json
{
  "answer": "The return policy states...",
  "sources": [{ "source": "doc.pdf", "snippet": "..." }]
}
```

## Collections

Collections are isolated namespaces in pgvector. Use different collection names to keep knowledge bases separate:

```
"flipkart-faq"  → scraped Flipkart Help Centre
"company-wiki"  → internal documentation PDFs
"product-db"    → rows from a products SQL table
```

## Scraper Scripts

For JS-heavy sites requiring browser navigation (clicking menus, SPAs):

```bash
# Scrape Flipkart Help Centre → data/flipkart_faq.json
python scripts/scrape_flipkart_faq.py

# Scrape + ingest into collection 'flipkart-faq'
python scripts/scrape_flipkart_faq.py --ingest
```

## Project Structure

```
.
├── api/
│   └── main.py               # FastAPI endpoints
├── ingestion/
│   ├── pipeline.py           # load → chunk → embed → store
│   └── loaders/
│       ├── pdf_loader.py
│       ├── web_loader.py     # static + JS (Playwright)
│       ├── text_loader.py
│       └── db_loader.py
├── retrieval/
│   └── retriever.py          # pgvector similarity search
├── generation/
│   └── chain.py              # LangChain prompt + GPT-4o
├── scripts/
│   └── scrape_flipkart_faq.py
├── vector_store.py           # PGVector singleton per collection
├── config.py                 # Pydantic settings
└── requirements.txt
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required** |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5433/rag` | pgvector connection |
| `OPENAI_MODEL` | `gpt-4o` | Generation model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `CHUNK_SIZE` | `1000` | Token chunk size |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `RETRIEVAL_K` | `5` | Default top-k results |

## Adding a New Source Type

1. Create `ingestion/loaders/<type>_loader.py` with `load_<type>(source) -> list[Document]`.
2. Add the enum value in `ingestion/pipeline.py`.
3. Add the branch in `ingest()` in `ingestion/pipeline.py`.

No other files need to change.
