"""FastAPI entrypoint for the RAG system."""
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import settings
from generation.chain import answer
from ingestion.pipeline import SourceType, ingest
from retrieval.retriever import retrieve


# ---------------------------------------------------------------------------
# DB setup — ensure pgvector extension exists
# ---------------------------------------------------------------------------

def _ensure_pgvector() -> None:
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_pgvector()
    yield


app = FastAPI(
    title="RAG API",
    description="Generic Retrieval-Augmented Generation system",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    source_type: str  # pdf | url | text | database
    source: str | list[str]
    collection: str = "default"
    metadata: dict[str, Any] | None = None
    # url-specific
    js: bool = False  # set True for JavaScript-rendered sites (uses Playwright)
    # database-specific
    db_query: str | None = None
    db_content_columns: list[str] | None = None
    db_metadata_columns: list[str] | None = None
    # json-specific
    json_content_keys: list[str] | None = None
    json_metadata_keys: list[str] | None = None


class IngestResponse(BaseModel):
    collection: str
    chunks_stored: int


class QueryRequest(BaseModel):
    question: str
    collection: str = "default"
    k: int | None = None
    filter: dict | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]


class SearchRequest(BaseModel):
    query: str
    collection: str = "default"
    k: int | None = None
    filter: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/source-types")
def source_types():
    """List all supported source types."""
    return {"source_types": [t.value for t in SourceType]}


@app.post("/ingest", response_model=IngestResponse)
def ingest_route(req: IngestRequest):
    """
    Ingest documents from any source into a pgvector collection.

    - **source_type**: `pdf` | `url` | `text` | `database`
    - **source**: file path, URL(s), or SQLAlchemy connection string
    - **collection**: logical namespace in pgvector (default: `"default"`)
    """
    try:
        n = ingest(
            source_type=req.source_type,
            source=req.source,
            collection=req.collection,
            metadata=req.metadata,
            js=req.js,
            db_query=req.db_query,
            db_content_columns=req.db_content_columns,
            db_metadata_columns=req.db_metadata_columns,
            json_content_keys=req.json_content_keys,
            json_metadata_keys=req.json_metadata_keys,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IngestResponse(collection=req.collection, chunks_stored=n)


@app.post("/query", response_model=QueryResponse)
def query_route(req: QueryRequest):
    """
    Ask a question. Returns an LLM-generated answer + source references.
    """
    try:
        docs = retrieve(
            query=req.question,
            collection=req.collection,
            k=req.k,
            filter=req.filter,
        )
        if not docs:
            return QueryResponse(answer="No relevant documents found.", sources=[])

        ans = answer(question=req.question, docs=docs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sources = [
        {"source": d.metadata.get("source", "unknown"), "snippet": d.page_content[:200]}
        for d in docs
    ]
    return QueryResponse(answer=ans, sources=sources)


@app.post("/search")
def search_route(req: SearchRequest):
    """
    Raw similarity search — returns matching chunks without LLM generation.
    Useful for debugging or building custom UIs.
    """
    try:
        docs = retrieve(
            query=req.query,
            collection=req.collection,
            k=req.k,
            filter=req.filter,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "results": [
            {
                "content": d.page_content,
                "metadata": d.metadata,
            }
            for d in docs
        ]
    }
