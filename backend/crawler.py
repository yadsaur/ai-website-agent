from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from xml.etree import ElementTree
from typing import List
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from backend.config import CRAWL_DELAY_SECONDS, SITE_CRAWL_DEADLINE_SECONDS

logger = logging.getLogger(__name__)
PRIMARY_NAVIGATION_TIMEOUT_MS = 20000
FALLBACK_NAVIGATION_TIMEOUT_MS = 15000
POST_COMMIT_WAIT_MS = 3000
NETWORK_IDLE_TIMEOUT_MS = 8000
SITEMAP_FETCH_TIMEOUT_SECONDS = 12
MAX_SITEMAP_URLS = 250
MAX_SITEMAP_FILES = 12

REAL_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SKIP_EXTENSIONS = (".pdf", ".jpg", ".png", ".gif", ".svg", ".mp4", ".zip")
SKIP_PATH_PREFIXES = ("/wp-admin", "/login", "/logout", "/cart", "/checkout", "/account")
SKIP_QUERY_KEYS = {
    "session",
    "sessionid",
    "sid",
    "auth",
    "token",
    "password",
    "redirect",
    "return",
    "returnto",
}


@dataclass
class PageResult:
    url: str
    html: str
    title: str
    depth: int
    http_status: int | None


def normalize_url(url: str) -> str:
    candidate = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path, params="", fragment="")
    return urlunparse((normalized.scheme, normalized.netloc, normalized.path, "", normalized.query, ""))


def _canonical_host(candidate: str) -> str:
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    hostname = (parsed.hostname or parsed.netloc or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _same_site_host(candidate: str, root_netloc: str) -> bool:
    return _canonical_host(candidate) == _canonical_host(root_netloc)


def _is_skippable(candidate: str, root_netloc: str) -> bool:
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return True
    if not _same_site_host(candidate, root_netloc):
        return True
    if parsed.fragment:
        return True
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    if any(path_lower.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return True
    if parsed.query:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key.lower() in SKIP_QUERY_KEYS for key, _ in query_pairs):
            return True
        if re.search(r"(session|auth|token|password)=", parsed.query, flags=re.IGNORECASE):
            return True
    return False


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, follow_redirects=True, timeout=SITEMAP_FETCH_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            return None
        return response.text
    except Exception:
        return None


def _extract_sitemap_locations(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    locations: list[str] = []
    for node in root.iter():
        if node.tag.endswith("loc") and node.text:
            value = node.text.strip()
            if value:
                locations.append(value)
    return locations


async def _discover_sitemap_urls(root_url: str, root_netloc: str, limit: int) -> list[str]:
    parsed_root = urlparse(root_url)
    base = f"{parsed_root.scheme}://{parsed_root.netloc}"
    sitemap_candidates = [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
    discovered: list[str] = []
    seen_sitemaps: set[str] = set()

    async with httpx.AsyncClient(headers={"User-Agent": REAL_CHROME_UA}) as client:
        robots_text = await _fetch_text(client, f"{base}/robots.txt")
        if robots_text:
            for line in robots_text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        sitemap_candidates.append(sitemap_url)

        pending = deque(sitemap_candidates)
        while pending and len(seen_sitemaps) < MAX_SITEMAP_FILES and len(discovered) < limit:
            sitemap_url = pending.popleft()
            normalized_sitemap = normalize_url(sitemap_url)
            if normalized_sitemap in seen_sitemaps:
                continue
            seen_sitemaps.add(normalized_sitemap)
            xml_text = await _fetch_text(client, sitemap_url)
            if not xml_text:
                continue

            locations = _extract_sitemap_locations(xml_text)
            for location in locations:
                normalized = normalize_url(location)
                if normalized.endswith(".xml") and len(seen_sitemaps) + len(pending) < MAX_SITEMAP_FILES:
                    pending.append(normalized)
                    continue
                if _is_skippable(normalized, root_netloc):
                    continue
                if normalized not in discovered:
                    discovered.append(normalized)
                if len(discovered) >= limit:
                    break

    return discovered


async def _emit_progress(
    progress_callback: Callable[[dict[str, int | str]], Awaitable[None] | None] | None,
    payload: dict[str, int | str],
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(payload)
    if asyncio.iscoroutine(result):
        await result


async def crawl_site(
    url: str,
    site_id: str,
    max_pages: int = 40,
    max_depth: int = 3,
    progress_callback: Callable[[dict[str, int | str]], Awaitable[None] | None] | None = None,
) -> List[PageResult]:
    del site_id
    root_url = normalize_url(url)
    root_netloc = urlparse(root_url).netloc
    visited: set[str] = set()
    queued: set[str] = {root_url}
    queue = deque([(root_url, 0)])
    results: list[PageResult] = []
    crawl_started_at = monotonic()

    sitemap_urls = await _discover_sitemap_urls(root_url, root_netloc, min(MAX_SITEMAP_URLS, max_pages * 4))
    for sitemap_url in sitemap_urls:
        if sitemap_url in queued or sitemap_url == root_url:
            continue
        queue.append((sitemap_url, 1))
        queued.add(sitemap_url)

    await _emit_progress(
        progress_callback,
        {
            "pages_crawled": 0,
            "pages_discovered": len(queued),
            "current_url": root_url,
        },
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=REAL_CHROME_UA,
            ignore_https_errors=True,
        )
        page = await context.new_page()

        while queue and len(results) < max_pages:
            if results and (monotonic() - crawl_started_at) > SITE_CRAWL_DEADLINE_SECONDS:
                logger.warning(
                    "Stopping crawl for %s after %ss with %s pages collected",
                    root_url,
                    SITE_CRAWL_DEADLINE_SECONDS,
                    len(results),
                )
                break
            current_url, depth = queue.popleft()
            queued.discard(current_url)
            if current_url in visited or depth > max_depth:
                continue

            visited.add(current_url)
            await asyncio.sleep(CRAWL_DELAY_SECONDS)

            try:
                try:
                    response = await page.goto(
                        current_url,
                        wait_until="domcontentloaded",
                        timeout=PRIMARY_NAVIGATION_TIMEOUT_MS,
                    )
                except PlaywrightTimeoutError:
                    logger.warning(
                        "Primary navigation timeout for %s, retrying with commit wait",
                        current_url,
                    )
                    response = await page.goto(
                        current_url,
                        wait_until="commit",
                        timeout=FALLBACK_NAVIGATION_TIMEOUT_MS,
                    )
                    await page.wait_for_timeout(POST_COMMIT_WAIT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    logger.warning("networkidle timeout for %s", current_url)

                final_url = normalize_url(page.url)
                if final_url != current_url:
                    visited.add(final_url)
                    queued.discard(final_url)
                html = await page.content()
                title = await page.title()
                status = response.status if response is not None else None
                if final_url != current_url and any(existing.url == final_url for existing in results):
                    continue
                results.append(PageResult(url=final_url, html=html, title=title or "", depth=depth, http_status=status))
                await _emit_progress(
                    progress_callback,
                    {
                        "pages_crawled": len(results),
                        "pages_discovered": len(results) + len(queue),
                        "current_url": final_url,
                    },
                )

                if depth >= max_depth:
                    continue

                hrefs = await page.eval_on_selector_all(
                    "a[href]",
                    "elements => elements.map(el => el.getAttribute('href')).filter(Boolean)",
                )
                for href in hrefs:
                    if href.startswith("#"):
                        continue
                    absolute = normalize_url(urljoin(final_url, href))
                    if absolute in visited or absolute in queued:
                        continue
                    if _is_skippable(absolute, root_netloc):
                        continue
                    queue.append((absolute, depth + 1))
                    queued.add(absolute)
                await _emit_progress(
                    progress_callback,
                    {
                        "pages_crawled": len(results),
                        "pages_discovered": len(results) + len(queue),
                        "current_url": final_url,
                    },
                )
            except PlaywrightTimeoutError:
                logger.warning("Playwright timeout for %s", current_url)
            except Exception as exc:
                logger.warning("Failed to crawl %s: %s", current_url, exc)

        await context.close()
        await browser.close()

    return results
