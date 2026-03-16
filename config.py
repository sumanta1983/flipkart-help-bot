from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # PostgreSQL + pgvector
    database_url: str = "postgresql://postgres:acto1234@localhost:5432/rag"

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Retrieval
    retrieval_k: int = 5

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
