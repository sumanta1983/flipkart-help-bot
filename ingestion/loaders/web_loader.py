"""Load web pages from one or more URLs.

Two modes:
- static (default): requests + BeautifulSoup — fast, works for plain HTML sites.
- js: Playwright headless Chromium — required for JavaScript-rendered sites
  (e.g. Flipkart, Amazon, React/Vue SPAs).
"""
import asyncio

from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document


def load_url(source: str | list[str], js: bool = False) -> list[Document]:
    """
    Fetch and parse one or more URLs.

    Args:
        source: A single URL string or a list of URL strings.
        js: Set True for JavaScript-rendered pages (uses Playwright).
            Requires: pip install playwright && playwright install chromium

    Returns:
        List of LangChain Documents (one per URL).
    """
    urls = [source] if isinstance(source, str) else source

    if js:
        return _load_with_playwright(urls)

    loader = WebBaseLoader(web_paths=urls)
    return loader.load()


def _load_with_playwright(urls: list[str]) -> list[Document]:
    """Render pages with a headless Chromium browser and return Documents."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright is required for js=True. "
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from exc

    async def _fetch_all() -> list[Document]:
        docs: list[Document] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            for url in urls:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                content = await page.inner_text("body")
                docs.append(
                    Document(
                        page_content=content,
                        metadata={"source": url},
                    )
                )
            await browser.close()
        return docs

    return asyncio.run(_fetch_all())
