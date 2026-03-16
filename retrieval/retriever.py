"""Similarity search over a pgvector collection."""
from langchain_core.documents import Document

from config import settings
from vector_store import get_store


def retrieve(
    query: str,
    collection: str = "default",
    k: int | None = None,
    filter: dict | None = None,
) -> list[Document]:
    """
    Return the top-k most relevant documents for a query.

    Args:
        query: Natural-language question or search string.
        collection: pgvector collection to search.
        k: Number of results (defaults to settings.retrieval_k).
        filter: Optional metadata filter dict, e.g. {"source": "report.pdf"}.

    Returns:
        List of LangChain Documents ranked by relevance.
    """
    store = get_store(collection)
    return store.similarity_search(
        query,
        k=k or settings.retrieval_k,
        filter=filter,
    )
