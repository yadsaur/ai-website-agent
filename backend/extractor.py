from __future__ import annotations

import html as html_lib
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class ExtractedContent:
    text: str
    title: str
    description: str
    headings: list[dict[str, int | str]]
    word_count: int
    canonical_url: str
    content_hash: str


def _clean_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    lines: list[str] = []
    seen_lines: set[str] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if len(line) < 3:
            continue
        if re.fullmatch(r"[\W_]+", line):
            continue
        normalized = re.sub(r"\W+", "", line.lower())
        if normalized in seen_lines:
            continue
        seen_lines.add(normalized)
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _remove_noise(soup: BeautifulSoup) -> None:
    noisy_selectors = [
        "[aria-hidden='true']",
        "[hidden]",
        "[style*='display:none']",
        "[style*='display: none']",
        ".cookie",
        ".cookies",
        ".cookie-banner",
        ".cookie-consent",
        ".newsletter",
        ".popup",
        ".modal",
        ".overlay",
        ".skip-link",
        "#cookie",
        "#cookies",
    ]
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "iframe", "svg"]):
        tag.decompose()
    for selector in noisy_selectors:
        for tag in soup.select(selector):
            tag.decompose()


def _extract_fallback_text(soup: BeautifulSoup) -> str:
    _remove_noise(soup)
    parts: list[str] = []
    for element in soup.select("main, article, section, h1, h2, h3, h4, h5, h6, p, li, dt, dd, td, th, blockquote"):
        text = element.get_text(" ", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _extract_structured_text(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    for details in soup.select("details"):
        summary = details.find("summary")
        summary_text = summary.get_text(" ", strip=True) if summary else ""
        answer = details.get_text(" ", strip=True)
        if summary_text and answer and summary_text != answer:
            parts.append(f"FAQ: {summary_text}\nAnswer: {answer}")

    for table in soup.select("table"):
        rows: list[str] = []
        for tr in table.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.select("th,td")]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            parts.append("Table:\n" + "\n".join(rows[:20]))

    for selector in ["[class*='price']", "[class*='pricing']", "[id*='price']", "[id*='pricing']", "[class*='faq']", "[id*='faq']"]:
        for block in soup.select(selector)[:8]:
            text = block.get_text(" ", strip=True)
            if text and len(text.split()) >= 5:
                parts.append(text)
    return "\n\n".join(parts)


def _extract_title(soup: BeautifulSoup) -> str:
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)
    og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    description_tag = soup.find("meta", attrs={"name": "description"})
    if description_tag and description_tag.get("content"):
        return description_tag["content"].strip()
    og_description = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
        "meta", attrs={"name": "og:description"}
    )
    if og_description and og_description.get("content"):
        return og_description["content"].strip()
    return ""


def _extract_canonical_url(soup: BeautifulSoup, url: str) -> str:
    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if canonical_tag and canonical_tag.get("href"):
        return urljoin(url, canonical_tag["href"]).strip()
    return url


def extract_content(html: str, url: str) -> ExtractedContent:
    extracted = trafilatura.extract(
        html,
        include_tables=True,
        include_links=False,
        no_fallback=False,
        favor_recall=True,
    ) or ""
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    description = _extract_description(soup)
    canonical_url = _extract_canonical_url(soup, url)
    structured_text = _extract_structured_text(soup)
    raw_text = extracted if len(extracted.strip()) >= 100 else _extract_fallback_text(BeautifulSoup(html, "lxml"))
    intro = "\n".join(part for part in [title, description] if part).strip()
    text = _clean_text("\n\n".join(part for part in [intro, structured_text, raw_text] if part))

    headings: list[dict[str, int | str]] = []
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        text_value = tag.get_text(" ", strip=True)
        if text_value:
            headings.append({"level": int(tag.name[1]), "text": text_value})

    return ExtractedContent(
        text=text,
        title=title,
        description=description,
        headings=headings,
        word_count=len(text.split()),
        canonical_url=canonical_url,
        content_hash=hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
    )
