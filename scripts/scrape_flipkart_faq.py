"""
Scrape all FAQs from https://www.flipkart.com/helpcentre

How it works:
  Flipkart's help centre is a React SPA backed by a private REST API at
  1.rome.api.flipkart.com. Direct calls to that API return 403 unless they
  come from the browser with the right session cookies.

  Strategy — stay inside the browser, intercept every API response:
    1. Load /helpcentre/trackorder/i/2  → triggers rootCatalog API (all topics)
    2. For each topic catalogId, navigate to ?catalog=<id>&view=CATALOG
       → triggers catalog API (FAQ + sub-catalog IDs)
    3. For each faqId, navigate to ?catalog=<id>&faq=<faqId>&view=FAQ
       → triggers faq detail API (answer text)
    4. Collect everything from the intercepted responses; no DOM scraping needed.

Usage:
    python scripts/scrape_flipkart_faq.py                    # scrape only
    python scripts/scrape_flipkart_faq.py --ingest           # scrape + ingest
    python scripts/scrape_flipkart_faq.py --out custom.json  # custom output
"""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import requests as req_lib

BASE_URL   = "https://www.flipkart.com/helpcentre"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
DEFAULT_OUT = OUTPUT_DIR / "flipkart_faq.json"
API_INGEST  = "http://localhost:8000/ingest"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Strip HTML tags from Flipkart FAQ titles
_TAG_RE = re.compile(r"<[^>]+>")
def strip_html(s: str) -> str:
    return _TAG_RE.sub("", s).strip()


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

async def scrape() -> list[dict]:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    # Buckets filled by intercepted API responses
    root_catalogs:  list[dict] = []          # [{id, title}, ...]
    catalog_data:   dict[str, dict] = {}     # catalogId -> {faqs, catalogs}
    faq_answers:    dict[str, str]  = {}     # faqId -> answer text

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})

        # ── intercept every JSON response from Flipkart's self-serve API ──
        async def handle_response(resp):
            url = resp.url
            if "self-serve/helpcenter" not in url:
                return
            try:
                data = await resp.json()
                response = data.get("RESPONSE", {})
            except Exception:
                return

            if "/rootCatalog" in url:
                root_catalogs.extend(response.get("catalogs", []))

            elif "/catalog" in url:
                cid = _qs(url, "catalogId")
                if cid:
                    catalog_data[cid] = {
                        "name": response.get("catalogName", ""),
                        "faqs": response.get("faqs", []),
                        "sub_catalogs": response.get("catalogs", []),
                    }

            elif "/faq" in url:
                fid = _qs(url, "faqId")
                answer = _extract_answer(response)
                if fid and answer:
                    faq_answers[fid] = answer

        page.on("response", handle_response)

        # ── Step 1: load entry page → triggers rootCatalog API ────────────
        print("Loading help centre ...")
        await page.goto(f"{BASE_URL}/trackorder/i/2", wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(2000)

        if not root_catalogs:
            print("ERROR: rootCatalog API not intercepted. Flipkart may have changed the page.")
            await browser.close()
            return []

        print(f"Found {len(root_catalogs)} top-level topics.")

        # ── Step 2: visit each catalog page → triggers catalog API ────────
        all_catalog_ids: list[tuple[str, str]] = [
            (c["id"], c["title"]) for c in root_catalogs
        ]

        for cid, ctitle in all_catalog_ids:
            url = f"{BASE_URL}?catalog={cid}&view=CATALOG"
            try:
                await page.goto(url, wait_until="networkidle", timeout=20_000)
                await page.wait_for_timeout(800)
            except PWTimeout:
                print(f"  [timeout] {ctitle}")
                continue

            # If this catalog has sub-catalogs, visit them too
            sub = catalog_data.get(cid, {}).get("sub_catalogs", [])
            for sc in sub:
                sub_url = f"{BASE_URL}?catalog={sc['id']}&view=CATALOG"
                try:
                    await page.goto(sub_url, wait_until="networkidle", timeout=15_000)
                    await page.wait_for_timeout(600)
                except PWTimeout:
                    pass

        # Collect all (catalogId, faqId) pairs
        faq_pairs: list[tuple[str, str, str, str]] = []  # (catalog_id, catalog_name, faq_id, faq_title)
        for cid, cdata in catalog_data.items():
            for faq in cdata["faqs"]:
                faq_pairs.append((cid, cdata["name"], faq["id"], strip_html(faq["title"])))

        print(f"Collected {len(faq_pairs)} FAQ items across all topics.")
        print("Fetching answers (this may take a while) ...")

        # ── Step 3: visit each FAQ page → triggers faq detail API ─────────
        for i, (cid, cname, fid, ftitle) in enumerate(faq_pairs):
            if fid in faq_answers:
                continue
            faq_url = f"{BASE_URL}?catalog={cid}&faq={fid}&view=FAQ"
            try:
                await page.goto(faq_url, wait_until="networkidle", timeout=15_000)
                await page.wait_for_timeout(500)
            except PWTimeout:
                pass

            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(faq_pairs)} done ...")

        await browser.close()

    # ── Build result list ─────────────────────────────────────────────────
    results = []
    for cid, cname, fid, ftitle in faq_pairs:
        answer = faq_answers.get(fid, "")
        if ftitle and answer:
            results.append({
                "topic":    cname.strip(),
                "question": ftitle,
                "answer":   answer,
                "url":      f"{BASE_URL}?catalog={cid}&faq={fid}&view=FAQ",
            })

    print(f"\nTotal FAQs with answers: {len(results)} / {len(faq_pairs)}")
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qs(url: str, key: str) -> str | None:
    """Extract a query-string value from a URL."""
    for part in url.split("?")[-1].split("&"):
        if part.startswith(f"{key}="):
            return part[len(key)+1:]
    return None


def _extract_answer(response: dict) -> str:
    """Pull clean answer text from a Flipkart FAQ API response.

    The actual structure is:
        RESPONSE.result[0].htmlAnswer  ← the answer HTML
        RESPONSE.result[0].htmlQuestion
    """
    results = response.get("result", [])
    if results and isinstance(results, list):
        html = results[0].get("htmlAnswer", "")
        if html:
            return strip_html(html).strip()

    return ""


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_to_api(faqs: list[dict]) -> None:
    lines = []
    for item in faqs:
        lines.append(f"Topic: {item['topic']}")
        lines.append(f"Q: {item['question']}")
        lines.append(f"A: {item['answer']}")
        lines.append("")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_DIR / "_flipkart_faq_tmp.txt"
    tmp.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "source_type": "text",
        "source":      str(tmp.resolve()),
        "collection":  "flipkart-faq",
        "metadata":    {"source": "flipkart_helpcentre"},
    }
    print(f"Ingesting {len(faqs)} FAQs into collection 'flipkart-faq' ...")
    resp = req_lib.post(API_INGEST, json=payload, timeout=120)
    if resp.ok:
        print(f"  Stored {resp.json()['chunks_stored']} chunks.")
    else:
        print(f"  Ingest failed: {resp.status_code} {resp.text}")

    tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Flipkart Help Centre FAQs")
    parser.add_argument("--ingest", action="store_true", help="POST results to RAG API")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out)

    t0 = time.time()
    faqs = asyncio.run(scrape())
    elapsed = time.time() - t0

    if not faqs:
        print("No FAQs collected.")
        sys.exit(1)

    out_path.write_text(json.dumps(faqs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(faqs)} FAQs → {out_path}  ({elapsed:.0f}s)")

    if args.ingest:
        ingest_to_api(faqs)


if __name__ == "__main__":
    main()
