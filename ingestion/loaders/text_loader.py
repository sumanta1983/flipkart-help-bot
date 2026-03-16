"""Load plain text or Markdown files."""
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document


def load_text(source: str) -> list[Document]:
    """
    Load a single .txt / .md file or a directory of them.

    Args:
        source: Path to a text/markdown file or a directory.

    Returns:
        List of LangChain Documents.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Text source not found: {source}")

    if path.is_dir():
        loader = DirectoryLoader(
            str(path),
            glob="**/*.{txt,md}",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
        )
    else:
        loader = TextLoader(str(path), encoding="utf-8")

    return loader.load()
