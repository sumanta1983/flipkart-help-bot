"""Load rows from any SQL database into Documents."""
from langchain_community.document_loaders import SQLDatabaseLoader
from langchain_community.utilities import SQLDatabase
from langchain_core.documents import Document


def load_database(
    connection_string: str,
    query: str,
    page_content_columns: list[str] | None = None,
    metadata_columns: list[str] | None = None,
) -> list[Document]:
    """
    Run a SQL query and convert each row into a LangChain Document.

    Args:
        connection_string: SQLAlchemy-style URL, e.g.
            "postgresql+psycopg2://user:pass@localhost:5433/mydb"
        query: SQL SELECT statement to execute.
        page_content_columns: Column names whose values are joined as page_content.
            If None, all non-metadata columns are used.
        metadata_columns: Column names to store as document metadata.

    Returns:
        List of LangChain Documents (one per row).
    """
    db = SQLDatabase.from_uri(connection_string)
    loader = SQLDatabaseLoader(
        query=query,
        db=db,
        page_content_columns=page_content_columns,
        metadata_columns=metadata_columns or [],
    )
    return loader.load()
