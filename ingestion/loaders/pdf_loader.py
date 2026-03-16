"""Load one or more PDF files into LangChain Documents."""
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, PyPDFDirectoryLoader
from langchain_core.documents import Document


def load_pdf(source: str) -> list[Document]:
    """
    Load a single PDF file or a directory of PDFs.

    Args:
        source: Absolute or relative path to a .pdf file or a directory.

    Returns:
        List of LangChain Documents (one per page by default).
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"PDF source not found: {source}")

    if path.is_dir():
        loader = PyPDFDirectoryLoader(str(path))
    else:
        loader = PyPDFLoader(str(path))

    return loader.load()
