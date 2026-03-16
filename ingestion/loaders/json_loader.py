"""Load a JSON file into LangChain Documents.

Supports two shapes:
  - List of objects: each object becomes one Document.
      page_content = joined values of content_keys (default: all string fields)
      metadata     = remaining fields + source path

  - FAQ shape (auto-detected): list of objects with "question" + "answer" keys.
      page_content = "Q: <question>\nA: <answer>"
      metadata     = topic, url, source
"""
import json
from pathlib import Path

from langchain_core.documents import Document


def load_json(
    source: str,
    content_keys: list[str] | None = None,
    metadata_keys: list[str] | None = None,
) -> list[Document]:
    """
    Load a JSON file (list of objects) into LangChain Documents.

    Args:
        source:        Path to a .json file.
        content_keys:  Keys whose values are joined into page_content.
                       Defaults to auto-detection (FAQ shape) or all string fields.
        metadata_keys: Keys to keep in metadata. Defaults to everything not in content.

    Returns:
        List of LangChain Documents — one per JSON object.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"JSON source not found: {source}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a top-level list of objects.")

    docs: list[Document] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        # Auto-detect FAQ shape: {question, answer, ...}
        if _is_faq(item, content_keys):
            content = f"Q: {item['question']}\nA: {item['answer']}"
            meta = {
                "source": str(path),
                "topic":  item.get("topic", ""),
                "url":    item.get("url", ""),
            }
        else:
            c_keys = content_keys or [k for k, v in item.items() if isinstance(v, str)]
            m_keys = metadata_keys or [k for k in item if k not in c_keys]
            content = "\n".join(str(item[k]) for k in c_keys if k in item)
            meta = {k: item[k] for k in m_keys if k in item}
            meta["source"] = str(path)

        if content.strip():
            docs.append(Document(page_content=content, metadata=meta))

    return docs


def _is_faq(item: dict, content_keys: list[str] | None) -> bool:
    return content_keys is None and "question" in item and "answer" in item
