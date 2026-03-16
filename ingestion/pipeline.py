"""Ingestion pipeline: load → chunk → embed → store in pgvector."""
from enum import StrEnum
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings
from ingestion.loaders.db_loader import load_database
from ingestion.loaders.json_loader import load_json
from ingestion.loaders.pdf_loader import load_pdf
from ingestion.loaders.text_loader import load_text
from ingestion.loaders.web_loader import load_url
from vector_store import get_store


class SourceType(StrEnum):
    PDF = "pdf"
    URL = "url"
    TEXT = "text"
    DATABASE = "database"
    JSON = "json"


def _chunk(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return splitter.split_documents(docs)


def ingest(
    source_type: str,
    source: str | list[str],
    collection: str = "default",
    metadata: dict[str, Any] | None = None,
    # URL-specific options
    js: bool = False,
    # DB-specific options
    db_query: str | None = None,
    db_content_columns: list[str] | None = None,
    db_metadata_columns: list[str] | None = None,
    # JSON-specific options
    json_content_keys: list[str] | None = None,
    json_metadata_keys: list[str] | None = None,
) -> int:
    """
    Load documents from any supported source, chunk them, and store in pgvector.

    Args:
        source_type: One of "pdf", "url", "text", "database".
        source: File path, URL(s), or SQLAlchemy connection string (for database).
        collection: pgvector collection (namespace) to store into.
        metadata: Extra metadata fields merged into every document's metadata.
        js: Use Playwright for JavaScript-rendered URLs (url source_type only).
        db_query: SQL query (required when source_type="database").
        db_content_columns: Columns to use as page content (database only).
        db_metadata_columns: Columns to store as metadata (database only).

    Returns:
        Number of chunks stored.
    """
    st = SourceType(source_type.lower())

    if st == SourceType.PDF:
        docs = load_pdf(str(source))
    elif st == SourceType.URL:
        docs = load_url(source, js=js)
    elif st == SourceType.TEXT:
        docs = load_text(str(source))
    elif st == SourceType.JSON:
        docs = load_json(
            str(source),
            content_keys=json_content_keys,
            metadata_keys=json_metadata_keys,
        )
    elif st == SourceType.DATABASE:
        if not db_query:
            raise ValueError("db_query is required for source_type='database'")
        docs = load_database(
            connection_string=str(source),
            query=db_query,
            page_content_columns=db_content_columns,
            metadata_columns=db_metadata_columns,
        )

    # Merge extra metadata
    if metadata:
        for doc in docs:
            doc.metadata.update(metadata)

    chunks = _chunk(docs)
    store = get_store(collection)
    store.add_documents(chunks)

    return len(chunks)
