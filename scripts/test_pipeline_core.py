from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import retriever
from backend.chunker import chunk_page
from backend.crawler import _is_skippable, _hostname_resolves_public, normalize_url
from backend.extractor import extract_content
from backend.main import _simple_conversational_reply


def test_url_normalization_and_filtering() -> None:
    assert normalize_url("example.com/") == "https://example.com/"
    assert normalize_url("https://www.example.com/pricing/?utm_source=x&b=2&a=1#top") == "https://www.example.com/pricing?a=1&b=2"
    assert _is_skippable("https://example.com/logo.png", "example.com")
    assert _is_skippable("https://example.com/wp-admin", "example.com")
    assert _is_skippable("https://other.com/pricing", "example.com")
    assert not _is_skippable("https://www.example.com/pricing", "example.com")


def test_private_host_blocking() -> None:
    assert asyncio.run(_hostname_resolves_public("localhost")) is False
    assert asyncio.run(_hostname_resolves_public("127.0.0.1")) is False


def test_content_extraction_and_chunking_keep_faq_pairs() -> None:
    html = """
    <html>
      <head>
        <title>Acme Pricing</title>
        <meta name="description" content="Simple plans for Acme customers.">
      </head>
      <body>
        <nav>Home Pricing Blog Home Pricing Blog</nav>
        <main>
          <h1>Acme Pricing</h1>
          <p>Starter costs $9 per month and includes one website.</p>
          <details>
            <summary>Is there a free trial?</summary>
            <p>Yes. The trial lasts 14 days and does not need a credit card.</p>
          </details>
          <table>
            <tr><th>Plan</th><th>Price</th></tr>
            <tr><td>Growth</td><td>$29/month</td></tr>
          </table>
        </main>
        <footer>Copyright Acme Home Pricing Blog</footer>
      </body>
    </html>
    """
    content = extract_content(html, "https://acme.test/pricing")
    assert "Home Pricing Blog Home Pricing Blog" not in content.text
    assert "Is there a free trial?" in content.text
    assert "$29/month" in content.text
    chunks = chunk_page(content, "https://acme.test/pricing", content.title)
    combined = "\n".join(chunk.text for chunk in chunks)
    assert "Is there a free trial?" in combined
    assert "14 days" in combined


def test_retrieval_is_site_scoped() -> None:
    chunks = [
        {
            "chunk_id": "a1",
            "site_id": "site-a",
            "text": "Acme pricing starts at $9 per month.",
            "page_url": "https://a.test/pricing",
            "page_title": "Acme Pricing",
            "section": "Pricing",
        },
        {
            "chunk_id": "b1",
            "site_id": "site-b",
            "text": "Beta pricing starts at $999 per month.",
            "page_url": "https://b.test/pricing",
            "page_title": "Beta Pricing",
            "section": "Pricing",
        },
    ]
    store = SimpleNamespace(chunks=chunks, embeddings=np.asarray([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32))

    class FakeEmbedder:
        def embed_query(self, query: str) -> np.ndarray:
            return np.asarray([1.0, 0.0], dtype=np.float32)

    original_load = retriever.load_vector_store
    original_embedder = retriever.get_embedder
    try:
        retriever.load_vector_store = lambda site_id: store
        retriever.get_embedder = lambda: FakeEmbedder()
        results, intent = retriever.retrieve("site-a", "How much does it cost?", top_k=3)
    finally:
        retriever.load_vector_store = original_load
        retriever.get_embedder = original_embedder

    assert intent == "pricing"
    assert results
    assert all(result.chunk_id.startswith("a") for result in results)
    assert all("Beta" not in result.text for result in results)


def test_simple_conversation() -> None:
    assert _simple_conversational_reply("hi")
    assert _simple_conversational_reply("good morning there")
    assert _simple_conversational_reply("thanks")
    assert _simple_conversational_reply("what is pricing?") is None


if __name__ == "__main__":
    test_url_normalization_and_filtering()
    test_private_host_blocking()
    test_content_extraction_and_chunking_keep_faq_pairs()
    test_retrieval_is_site_scoped()
    test_simple_conversation()
    print("pipeline core tests passed")
