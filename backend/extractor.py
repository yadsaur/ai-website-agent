from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class ExtractedContent:
    text: str
    title: str
    description: str
    headings: list[dict[str, int | str]]
    word_count: int


def _clean_text(text: str) -> str:
    text = html_lib.unescape(text or "")
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if len(line) < 3:
            continue
        if re.fullmatch(r"[\W_]+", line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_fallback_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
        tag.decompose()
    parts: list[str] = []
    for element in soup.select("p, h1, h2, h3, h4, h5, h6, li, td, th, blockquote, article, main"):
        text = element.get_text(" ", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts)


def extract_content(html: str, url: str) -> ExtractedContent:
    del url
    extracted = trafilatura.extract(
        html,
        include_tables=True,
        include_links=False,
        no_fallback=False,
        favor_recall=True,
    ) or ""
    soup = BeautifulSoup(html, "lxml")
    raw_text = extracted if len(extracted.strip()) >= 100 else _extract_fallback_text(soup)
    text = _clean_text(raw_text)

    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)

    description = ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    if description_tag and description_tag.get("content"):
        description = description_tag["content"].strip()
    if not description:
        og_description = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
            "meta", attrs={"name": "og:description"}
        )
        if og_description and og_description.get("content"):
            description = og_description["content"].strip()

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
    )
