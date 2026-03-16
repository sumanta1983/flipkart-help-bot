"""RAG generation chain: retrieved context + question → answer."""
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import settings

_SYSTEM = """You are a helpful assistant. Answer the user's question using ONLY the provided context.
If the context does not contain enough information to answer, say so clearly.
Do not make up facts."""

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        (
            "human",
            "Context:\n{context}\n\nQuestion: {question}",
        ),
    ]
)


def _format_context(docs: list[Document]) -> str:
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in docs
    )


def answer(question: str, docs: list[Document]) -> str:
    """
    Generate an answer grounded in the retrieved documents.

    Args:
        question: The user's question.
        docs: Documents returned by the retriever.

    Returns:
        Answer string from the LLM.
    """
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    chain = _PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {
            "context": _format_context(docs),
            "question": question,
        }
    )
