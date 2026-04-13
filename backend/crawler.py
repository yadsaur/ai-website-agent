from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import List
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from backend.config import CRAWL_DELAY_SECONDS

logger = logging.getLogger(__name__)
PRIMARY_NAVIGATION_TIMEOUT_MS = 20000
FALLBACK_NAVIGATION_TIMEOUT_MS = 15000
POST_COMMIT_WAIT_MS = 3000
NETWORK_IDLE_TIMEOUT_MS = 8000
SITE_CRAWL_DEADLINE_SECONDS = 120

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
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path, params="", fragment="")
    return urlunparse((normalized.scheme, normalized.netloc, normalized.path, "", normalized.query, ""))


def _is_skippable(candidate: str, root_netloc: str) -> bool:
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return True
    if parsed.netloc.lower() != root_netloc.lower():
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


async def crawl_site(url: str, site_id: str, max_pages: int = 40, max_depth: int = 3) -> List[PageResult]:
    del site_id
    root_url = normalize_url(url)
    root_netloc = urlparse(root_url).netloc
    visited: set[str] = set()
    queued: set[str] = {root_url}
    queue = deque([(root_url, 0)])
    results: list[PageResult] = []
    crawl_started_at = monotonic()

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
                html = await page.content()
                title = await page.title()
                status = response.status if response is not None else None
                results.append(PageResult(url=final_url, html=html, title=title or "", depth=depth, http_status=status))

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
            except PlaywrightTimeoutError:
                logger.warning("Playwright timeout for %s", current_url)
            except Exception as exc:
                logger.warning("Failed to crawl %s: %s", current_url, exc)

        await context.close()
        await browser.close()

    return results
