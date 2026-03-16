"""Singleton pgvector store factory."""
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from config import settings


def _embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


@lru_cache(maxsize=32)
def get_store(collection: str = "default") -> PGVector:
    """Return (or create) a PGVector store for the given collection name."""
    return PGVector(
        embeddings=_embeddings(),
        collection_name=collection,
        connection=settings.database_url,
        use_jsonb=True,
    )
