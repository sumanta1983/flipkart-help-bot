# How the RAG System Works

## What is RAG?

**Retrieval-Augmented Generation (RAG)** is a technique that makes an LLM answer questions using *your own data* instead of only its training knowledge.

Instead of asking GPT-4o "what does our return policy say?", RAG first searches your documents for the relevant paragraphs, hands them to GPT-4o as context, and then GPT-4o answers based only on what it just read.

```
Your question
      │
      ▼
 [Search your docs]  ←── your PDFs, websites, database rows
      │
      ▼
 Top-k relevant chunks
      │
      ▼
 [GPT-4o reads chunks + question]
      │
      ▼
 Grounded answer + sources
```

---

## Two Phases

Every RAG system has two separate phases:

| Phase | When it runs | What happens |
|-------|-------------|--------------|
| **Ingestion** | Once per data source | Load → chunk → embed → store in DB |
| **Query** | Every user question | Embed question → search DB → LLM answers |

---

## Phase 1 — Ingestion

```
Source data
    │
    ▼
[Loader]          ← reads raw content, returns LangChain Documents
    │
    ▼
[Chunker]         ← splits long docs into ~1000-token overlapping pieces
    │
    ▼
[OpenAI Embedder] ← converts each chunk to a 1536-dim float vector
    │
    ▼
[pgvector store]  ← saves (vector, text, metadata) to PostgreSQL
```

### Step 1 — Load

`ingestion/loaders/` has one loader per source type:

| Source type | Loader file | How it reads |
|-------------|-------------|--------------|
| `pdf` | `pdf_loader.py` | `PyPDFLoader` — one Document per page |
| `url` (static) | `web_loader.py` | `requests` + BeautifulSoup |
| `url` (JS sites) | `web_loader.py` | Playwright headless Chromium |
| `text` / `.md` | `text_loader.py` | Plain file read |
| `database` | `db_loader.py` | SQL query → rows as Documents |

Every loader returns `list[Document]` — a LangChain object with `page_content` (text) and `metadata` (dict of info like file name, URL, page number).

### Step 2 — Chunk

`ingestion/pipeline.py` splits every Document using `RecursiveCharacterTextSplitter`:

```
"Long document text ....................."
         │
         ▼
["chunk 1 ......", "...chunk 2......", "...chunk 3"]
         ↑200-token overlap↑
```

- **Chunk size**: 1000 tokens (configurable via `CHUNK_SIZE` in `.env`)
- **Overlap**: 200 tokens — so context at chunk boundaries is not lost

### Step 3 — Embed

Each chunk is sent to OpenAI's `text-embedding-3-small` model which returns a **1536-dimensional vector** — a list of numbers that encodes the *meaning* of the text.

Semantically similar text → similar vectors (small cosine distance).

### Step 4 — Store

`vector_store.py` saves each chunk into **PostgreSQL with pgvector**:

```
pgvector table row:
  id         │ uuid
  embedding  │ vector(1536)   ← the float array
  document   │ text           ← the chunk text
  cmetadata  │ jsonb          ← metadata (source, page, etc.)
  collection │ text           ← logical namespace (e.g. "flipkart-faq")
```

`get_store(collection)` is cached with `@lru_cache` — one DB connection per collection per process.

---

## Phase 2 — Query

```
User question: "How do I return an order?"
      │
      ▼
[Embed question]       ← same OpenAI model, same vector space
      │
      ▼
[pgvector similarity search]
      │  SELECT ... ORDER BY embedding <=> query_vector LIMIT 5
      ▼
Top 5 most relevant chunks
      │
      ▼
[Build prompt]
      │   System: "Answer using ONLY the context below."
      │   Context: chunk1 \n --- \n chunk2 \n --- \n ...
      │   Question: "How do I return an order?"
      ▼
[GPT-4o]
      │
      ▼
Answer + list of sources (file / URL / page)
```

### Why cosine similarity?

The pgvector operator `<=>` computes **cosine distance** between two vectors. When the user's question is embedded, the resulting vector points in the same mathematical "direction" as chunks that discuss the same topic — regardless of the exact words used.

So "What is the refund process?" will match a chunk that says "To return a product and receive your money back..." even though the words are different.

---

## Collections (Namespaces)

Every ingest call targets a **collection** — a named partition in pgvector. Collections let you keep separate knowledge bases in the same database:

```
"flipkart-faq"   → scraped Flipkart help centre
"company-wiki"   → internal documentation PDFs
"product-db"     → rows from a products SQL table
```

Query with the same collection name to search only that namespace. Different collections never mix results.

---

## Code Flow — Ingest Request

```
POST /ingest { source_type: "pdf", source: "/docs/policy.pdf", collection: "hr" }
      │
      ▼
api/main.py :: ingest_route()
      │
      ▼
ingestion/pipeline.py :: ingest()
      │  ├── load_pdf("/docs/policy.pdf")    → [Document, Document, ...]
      │  ├── _chunk(docs)                    → [chunk1, chunk2, ...]  (e.g. 42 chunks)
      │  └── get_store("hr").add_documents() → embeds + stores all chunks
      ▼
Returns: { "collection": "hr", "chunks_stored": 42 }
```

## Code Flow — Query Request

```
POST /query { question: "What is the leave policy?", collection: "hr" }
      │
      ▼
api/main.py :: query_route()
      │
      ▼
retrieval/retriever.py :: retrieve()
      │  └── get_store("hr").similarity_search(question, k=5)
      │        → top 5 Document chunks
      ▼
generation/chain.py :: answer(question, docs)
      │  └── _PROMPT | ChatOpenAI(gpt-4o) | StrOutputParser()
      ▼
Returns: { "answer": "...", "sources": [{...}, {...}] }
```

---

## Key Design Decisions

| Decision | Why |
|----------|-----|
| One loader per source type | Easy to add new sources — just add a file, no other changes |
| Chunking only in pipeline | Loaders stay simple; chunk config is centralised |
| Stateless `answer()` | Takes `(question, docs)`, returns string — no DB calls, easy to test |
| `@lru_cache` on `get_store()` | One PGVector connection per collection — avoids reconnecting on every request |
| Collections | One DB, many knowledge bases — no schema changes needed |
| `js=True` flag on URL | Static scraping is fast by default; Playwright only when needed |
| `OPENAI_API_KEY` in `.env` | Never hardcoded; loaded via pydantic-settings |

---

## Where Each File Lives

```
rag/
├── config.py                  ← All settings (reads .env)
├── vector_store.py            ← PGVector singleton per collection
│
├── ingestion/
│   ├── pipeline.py            ← load → chunk → embed → store  (orchestrator)
│   └── loaders/
│       ├── pdf_loader.py      ← PDFs (PyPDFLoader)
│       ├── web_loader.py      ← URLs (requests or Playwright)
│       ├── text_loader.py     ← .txt / .md files
│       └── db_loader.py       ← SQL rows
│
├── retrieval/
│   └── retriever.py           ← similarity_search wrapper
│
├── generation/
│   └── chain.py               ← prompt + GPT-4o → answer string
│
├── api/
│   └── main.py                ← FastAPI: /ingest  /query  /search
│
└── scripts/
    └── scrape_flipkart_faq.py ← Special scraper for JS-heavy sites
```

---

## Adding a New Data Source

1. Create `ingestion/loaders/<type>_loader.py` with a `load_<type>(source) -> list[Document]` function.
2. Add a new value to `SourceType` enum in `ingestion/pipeline.py`.
3. Add one `elif` branch in `ingest()` in `ingestion/pipeline.py`.

Nothing else needs to change — the chunker, embedder, vector store, retriever, and generation layer are all source-agnostic.
