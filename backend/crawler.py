from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import List
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Request as PlaywrightRequest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from backend.config import (
    CRAWL_DELAY_SECONDS,
    MAX_CRAWL_CONCURRENCY,
    MAX_PAGE_HTML_BYTES,
    RESPECT_ROBOTS_TXT,
    SITE_CRAWL_DEADLINE_SECONDS,
)

logger = logging.getLogger(__name__)
PRIMARY_NAVIGATION_TIMEOUT_MS = 14000
FALLBACK_NAVIGATION_TIMEOUT_MS = 8000
POST_COMMIT_WAIT_MS = 1200
NETWORK_IDLE_TIMEOUT_MS = 2500
SITEMAP_FETCH_TIMEOUT_SECONDS = 10
HTTP_FALLBACK_TIMEOUT_SECONDS = 12
MAX_SITEMAP_URLS = 300
MAX_SITEMAP_FILES = 12
MAX_DISCOVERY_MULTIPLIER = 3
MAX_RAW_HTML_BYTES = 4 * 1024 * 1024

REAL_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SKIP_EXTENSIONS = (
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".gz",
    ".ico",
    ".jpg",
    ".jpeg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".webm",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
)
SKIP_PATH_PARTS = {
    "account",
    "admin",
    "basket",
    "cart",
    "checkout",
    "delete",
    "login",
    "logout",
    "my-account",
    "order",
    "password",
    "private",
    "signin",
    "signup",
    "wp-admin",
}
SKIP_QUERY_KEYS = {
    "auth",
    "password",
    "redirect",
    "return",
    "returnto",
    "session",
    "sessionid",
    "sid",
    "token",
}
TRACKING_QUERY_KEYS = {
    "_hsenc",
    "_hsmi",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "ref_src",
}
IMPORTANT_PATH_PARTS = (
    "pricing",
    "plans",
    "features",
    "product",
    "products",
    "service",
    "services",
    "about",
    "contact",
    "faq",
    "help",
    "support",
    "docs",
    "documentation",
    "integrations",
    "customers",
    "case-studies",
)
IMPORTANT_PATH_RANK = {
    "pricing": 0,
    "plans": 0,
    "features": 1,
    "product": 1,
    "products": 1,
    "service": 1,
    "services": 1,
    "faq": 2,
    "help": 2,
    "support": 2,
    "docs": 2,
    "documentation": 2,
    "integrations": 3,
    "about": 4,
    "contact": 4,
    "customers": 5,
    "case-studies": 5,
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
    if not scheme or not netloc:
        raise ValueError("URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("URLs with credentials are not supported.")
    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path.lower().endswith(("/index.html", "/index.htm")):
        path = path.rsplit("/", 1)[0] or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in TRACKING_QUERY_KEYS:
            continue
        query_pairs.append((key, value))
    query = urlencode(sorted(query_pairs), doseq=True)
    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path, params="", query=query, fragment="")
    return urlunparse((normalized.scheme, normalized.netloc, normalized.path, "", normalized.query, ""))


def _canonical_host(candidate: str) -> str:
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    hostname = (parsed.hostname or parsed.netloc or "").lower().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _same_site_host(candidate: str, root_netloc: str) -> bool:
    return _canonical_host(candidate) == _canonical_host(root_netloc)


def _is_private_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _hostname_resolves_public(hostname: str) -> bool:
    if hostname in {"localhost", "localhost.localdomain"}:
        return False
    if _is_private_ip(hostname):
        return False

    def resolve() -> list[str]:
        return [item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)]

    try:
        addresses = await asyncio.to_thread(resolve)
    except socket.gaierror:
        return False
    except Exception:
        logger.warning("Unable to resolve hostname %s", hostname, exc_info=True)
        return False
    return bool(addresses) and all(not _is_private_ip(address) for address in addresses)


def _has_skipped_path_part(path: str) -> bool:
    parts = {part for part in path.lower().split("/") if part}
    return bool(parts & SKIP_PATH_PARTS)


def _is_skippable(candidate: str, root_netloc: str) -> bool:
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return True
    if not parsed.hostname:
        return True
    if not _same_site_host(candidate, root_netloc):
        return True
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    if _has_skipped_path_part(path_lower):
        return True
    if parsed.query:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key.lower() in SKIP_QUERY_KEYS for key, _ in query_pairs):
            return True
        if re.search(r"(session|auth|token|password)=", parsed.query, flags=re.IGNORECASE):
            return True
    return False


def _page_priority(url: str, depth: int) -> tuple[int, int, str]:
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    if path in {"", "/"}:
        return (0, depth, url)
    important_ranks = [rank for part, rank in IMPORTANT_PATH_RANK.items() if part in path]
    if important_ranks:
        return (1, min(important_ranks), depth, url)
    if "blog" in path or "article" in path or "post" in path or "news" in path:
        return (4, depth, url, "")
    return (2 + min(depth, 2), depth, url, "")


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, follow_redirects=True, timeout=SITEMAP_FETCH_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            return None
        return response.text
    except Exception:
        return None


async def _fetch_html_page(client: httpx.AsyncClient, url: str) -> tuple[str, str, int] | None:
    """Fetch public HTML without browser rendering as a fallback for JS-heavy sites."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=HTTP_FALLBACK_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("HTTP fallback failed for %s: %s", url, exc)
        return None

    content_type = response.headers.get("content-type", "").lower()
    if response.status_code >= 400:
        return None
    if content_type and "html" not in content_type and "text/plain" not in content_type:
        return None
    if len(response.content) > MAX_RAW_HTML_BYTES:
        logger.info("Skipping oversized HTTP fallback page %s", response.url)
        return None
    try:
        final_url = normalize_url(str(response.url))
    except ValueError:
        return None
    return final_url, response.text, response.status_code


def _title_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    title = soup.find("title")
    return title.get_text(" ", strip=True) if title else ""


def _compact_html(html: str) -> str:
    """Drop heavy assets/scripts before the HTML is stored and extracted."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "canvas", "picture", "source"]):
        tag.decompose()
    for tag in soup.select("[srcset]"):
        tag.attrs.pop("srcset", None)
    for tag in soup.select("[style]"):
        tag.attrs.pop("style", None)
    return str(soup)


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


async def _load_robots(base: str) -> RobotFileParser | None:
    if not RESPECT_ROBOTS_TXT:
        return None
    async with httpx.AsyncClient(headers={"User-Agent": REAL_CHROME_UA}) as client:
        robots_text = await _fetch_text(client, f"{base}/robots.txt")
    if not robots_text:
        return None
    parser = RobotFileParser()
    parser.set_url(f"{base}/robots.txt")
    parser.parse(robots_text.splitlines())
    return parser


async def _discover_sitemap_urls(root_url: str, root_netloc: str, limit: int) -> tuple[list[str], RobotFileParser | None]:
    parsed_root = urlparse(root_url)
    base = f"{parsed_root.scheme}://{parsed_root.netloc}"
    sitemap_candidates = [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
    discovered: list[str] = []
    seen_sitemaps: set[str] = set()
    robots_parser: RobotFileParser | None = None

    async with httpx.AsyncClient(headers={"User-Agent": REAL_CHROME_UA}) as client:
        robots_text = await _fetch_text(client, f"{base}/robots.txt")
        if robots_text:
            robots_parser = RobotFileParser()
            robots_parser.set_url(f"{base}/robots.txt")
            robots_parser.parse(robots_text.splitlines())
            for line in robots_text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_url = line.split(":", 1)[1].strip()
                    if sitemap_url:
                        sitemap_candidates.append(sitemap_url)

        pending = deque(sitemap_candidates)
        while pending and len(seen_sitemaps) < MAX_SITEMAP_FILES and len(discovered) < limit:
            sitemap_url = pending.popleft()
            try:
                normalized_sitemap = normalize_url(sitemap_url)
            except ValueError:
                continue
            if normalized_sitemap in seen_sitemaps:
                continue
            seen_sitemaps.add(normalized_sitemap)
            xml_text = await _fetch_text(client, normalized_sitemap)
            if not xml_text:
                continue

            for location in _extract_sitemap_locations(xml_text):
                try:
                    normalized = normalize_url(location)
                except ValueError:
                    continue
                if normalized.endswith(".xml") and len(seen_sitemaps) + len(pending) < MAX_SITEMAP_FILES:
                    pending.append(normalized)
                    continue
                if _is_skippable(normalized, root_netloc):
                    continue
                if robots_parser and RESPECT_ROBOTS_TXT and not robots_parser.can_fetch(REAL_CHROME_UA, normalized):
                    continue
                if normalized not in discovered:
                    discovered.append(normalized)
                if len(discovered) >= limit:
                    break

    if robots_parser is None:
        robots_parser = await _load_robots(base)
    return discovered, robots_parser


async def _emit_progress(
    progress_callback: Callable[[dict[str, int | str]], Awaitable[None] | None] | None,
    payload: dict[str, int | str],
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(payload)
    if asyncio.iscoroutine(result):
        await result


def _extract_canonical_url(html: str, fallback_url: str, root_netloc: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if canonical and canonical.get("href"):
        try:
            normalized = normalize_url(urljoin(fallback_url, str(canonical["href"])))
            if not _is_skippable(normalized, root_netloc):
                return normalized
        except ValueError:
            pass
    return fallback_url


def _extract_hrefs(html: str, final_url: str, root_netloc: str, robots_parser: RobotFileParser | None) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.select("a[href]"):
        href = str(tag.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        try:
            absolute = normalize_url(urljoin(final_url, href))
        except ValueError:
            continue
        if _is_skippable(absolute, root_netloc):
            continue
        if robots_parser and RESPECT_ROBOTS_TXT and not robots_parser.can_fetch(REAL_CHROME_UA, absolute):
            continue
        links.append(absolute)
    return links


def _should_abort_request(request: PlaywrightRequest, root_netloc: str) -> bool:
    if request.resource_type in {"font", "image", "media", "stylesheet"}:
        return True
    try:
        parsed = urlparse(request.url)
    except Exception:
        return True
    if parsed.scheme not in {"http", "https"}:
        return request.resource_type == "document"
    if parsed.hostname and _is_private_ip(parsed.hostname):
        return True
    if request.resource_type == "document":
        return _is_skippable(request.url, root_netloc)
    return False


async def crawl_site(
    url: str,
    site_id: str,
    max_pages: int = 40,
    max_depth: int = 3,
    progress_callback: Callable[[dict[str, int | str]], Awaitable[None] | None] | None = None,
) -> List[PageResult]:
    del site_id
    root_url = normalize_url(url)
    parsed_root = urlparse(root_url)
    root_netloc = parsed_root.netloc
    if parsed_root.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs can be crawled.")
    public_host_cache: dict[str, bool] = {}

    async def host_is_public(hostname: str) -> bool:
        if hostname not in public_host_cache:
            public_host_cache[hostname] = await _hostname_resolves_public(hostname)
        return public_host_cache[hostname]

    if not parsed_root.hostname or not await host_is_public(parsed_root.hostname):
        raise ValueError("URL must resolve to a public website.")

    visited: set[str] = set()
    result_urls: set[str] = set()
    queued: set[str] = {root_url}
    queue = deque([(root_url, 0)])
    results: list[PageResult] = []
    crawl_started_at = monotonic()

    sitemap_urls, robots_parser = await _discover_sitemap_urls(root_url, root_netloc, min(MAX_SITEMAP_URLS, max_pages * 4))
    for sitemap_url in sorted(sitemap_urls, key=lambda item: _page_priority(item, 1)):
        if sitemap_url in queued or sitemap_url == root_url:
            continue
        queue.append((sitemap_url, 1))
        queued.add(sitemap_url)

    await _emit_progress(
        progress_callback,
        {"stage": "crawling", "pages_crawled": 0, "pages_discovered": len(queued), "current_url": root_url},
    )

    concurrency = max(1, min(MAX_CRAWL_CONCURRENCY, max_pages))
    queue_lock = asyncio.Lock()
    result_lock = asyncio.Lock()

    async with async_playwright() as playwright:
        browser = None
        context = None
        browser_lock = asyncio.Lock()

        async def route_handler(route, request: PlaywrightRequest) -> None:
            if _should_abort_request(request, root_netloc):
                await route.abort()
            else:
                await route.continue_()

        async def get_browser_context():
            nonlocal browser, context
            if context is not None:
                return context
            async with browser_lock:
                if context is not None:
                    return context
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1024, "height": 720},
                    user_agent=REAL_CHROME_UA,
                    ignore_https_errors=True,
                    java_script_enabled=True,
                )
                await context.route("**/*", route_handler)
                return context

        fallback_client = httpx.AsyncClient(
            headers={
                "User-Agent": REAL_CHROME_UA,
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )

        async def take_next() -> tuple[str, int] | None:
            async with queue_lock:
                while queue:
                    if len(results) >= max_pages:
                        return None
                    if results and (monotonic() - crawl_started_at) > SITE_CRAWL_DEADLINE_SECONDS:
                        return None
                    ordered = sorted(queue, key=lambda item: _page_priority(item[0], item[1]))
                    queue.clear()
                    queue.extend(ordered)
                    current_url, depth = queue.popleft()
                    queued.discard(current_url)
                    if current_url in visited or depth > max_depth:
                        continue
                    visited.add(current_url)
                    return current_url, depth
                return None

        async def enqueue_links(links: list[str], depth: int) -> None:
            if depth >= max_depth:
                return
            async with queue_lock:
                for absolute in links:
                    if len(visited) + len(queued) >= max_pages * MAX_DISCOVERY_MULTIPLIER:
                        break
                    if absolute in visited or absolute in queued:
                        continue
                    queue.append((absolute, depth + 1))
                    queued.add(absolute)

        async def record_html_page(
            source_url: str,
            html: str,
            depth: int,
            http_status: int | None,
            title: str = "",
        ) -> bool:
            try:
                final_url = normalize_url(source_url)
            except ValueError:
                return False
            if _is_skippable(final_url, root_netloc) or not _same_site_host(final_url, root_netloc):
                return False
            final_host = urlparse(final_url).hostname
            if not final_host or not await host_is_public(final_host):
                return False
            if len(html.encode("utf-8", errors="ignore")) > MAX_RAW_HTML_BYTES:
                logger.info("Skipping oversized raw page %s", final_url)
                return False

            canonical_url = _extract_canonical_url(html, final_url, root_netloc)
            if robots_parser and RESPECT_ROBOTS_TXT and not robots_parser.can_fetch(REAL_CHROME_UA, canonical_url):
                return False
            links = _extract_hrefs(html, canonical_url, root_netloc, robots_parser)
            await enqueue_links(links, depth)
            compact_html = _compact_html(html)
            if len(compact_html.encode("utf-8", errors="ignore")) > MAX_PAGE_HTML_BYTES:
                logger.info("Skipping page with oversized compact HTML %s", canonical_url)
                return False

            async with result_lock:
                if canonical_url in result_urls:
                    return False
                if len(results) >= max_pages:
                    worst_page = max(results, key=lambda page: _page_priority(page.url, page.depth))
                    if _page_priority(canonical_url, depth) >= _page_priority(worst_page.url, worst_page.depth):
                        return False
                    results.remove(worst_page)
                    result_urls.discard(worst_page.url)
                result_urls.add(canonical_url)
                results.append(
                    PageResult(
                        url=canonical_url,
                        html=compact_html,
                        title=title or _title_from_html(compact_html),
                        depth=depth,
                        http_status=http_status,
                    )
                )
                await _emit_progress(
                    progress_callback,
                    {
                        "stage": "crawling",
                        "pages_crawled": len(results),
                        "pages_discovered": len(results) + len(queue),
                        "current_url": canonical_url,
                    },
                )
                return True

        async def fetch_and_record_fallback(current_url: str, depth: int) -> bool:
            fallback = await _fetch_html_page(fallback_client, current_url)
            if fallback is None:
                return False
            final_url, html, status = fallback
            recorded = await record_html_page(final_url, html, depth, status)
            if recorded:
                logger.info("Recovered %s with HTTP fallback", final_url)
            return recorded

        async def crawl_with_browser(current_url: str, depth: int, worker_id: int) -> None:
            page = None
            try:
                active_context = await get_browser_context()
                page = await active_context.new_page()
                try:
                    response = await page.goto(
                        current_url,
                        wait_until="domcontentloaded",
                        timeout=PRIMARY_NAVIGATION_TIMEOUT_MS,
                    )
                except PlaywrightTimeoutError:
                    logger.info("Navigation timeout for %s, retrying with commit wait", current_url)
                    response = await page.goto(
                        current_url,
                        wait_until="commit",
                        timeout=FALLBACK_NAVIGATION_TIMEOUT_MS,
                    )
                    await page.wait_for_timeout(POST_COMMIT_WAIT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass

                final_url = normalize_url(page.url)
                html = await page.content()
                title = await page.title()
                status = response.status if response is not None else None
                await record_html_page(final_url, html, depth, status, title)
            except PlaywrightTimeoutError:
                logger.info("Playwright timeout for %s", current_url)
            except Exception as exc:
                logger.info("Failed to crawl %s in worker %s: %s", current_url, worker_id, exc)
            finally:
                if page is not None:
                    await page.close()

        async def crawl_worker(worker_id: int) -> None:
            try:
                while True:
                    if CRAWL_DELAY_SECONDS > 0:
                        await asyncio.sleep(CRAWL_DELAY_SECONDS)
                    item = await take_next()
                    if item is None:
                        return
                    current_url, depth = item
                    recorded = await fetch_and_record_fallback(current_url, depth)
                    if not recorded:
                        await crawl_with_browser(current_url, depth, worker_id)
            finally:
                return

        workers = [asyncio.create_task(crawl_worker(index)) for index in range(concurrency)]
        try:
            await asyncio.gather(*workers)
        finally:
            await fallback_client.aclose()
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()

    return sorted(results, key=lambda page: _page_priority(page.url, page.depth))
