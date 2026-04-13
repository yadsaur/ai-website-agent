from __future__ import annotations

import math
import re
from dataclasses import dataclass

from backend.config import CHUNK_OVERLAP_TOKENS, CHUNK_TARGET_TOKENS, MIN_CHUNK_WORDS
from backend.extractor import ExtractedContent
from backend.ui_extractor import extract_ui_structure, ui_structure_to_text

PRICING_HINT_KEYWORDS = [
    "pricing", "price", "plan", "plans", "cost", "billing", "payment",
    "subscribe", "subscription", "fee", "per month", "per year", "free trial",
]


@dataclass
class ChunkData:
    text: str
    prefixed_text: str
    section: str
    position: int
    token_count: int
    page_url: str
    page_title: str
    page_id: str | None = None
    site_id: str | None = None


def build_site_overview_chunk(
    content: ExtractedContent,
    page_url: str,
    page_title: str,
    site_name: str | None = None,
) -> ChunkData | None:
    summary_parts: list[str] = []
    if content.description:
        summary_parts.append(content.description.strip())

    words = content.text.split()
    if words:
        summary_parts.append(" ".join(words[: min(140, len(words))]))

    combined = " ".join(part for part in summary_parts if part).strip()
    if len(combined.split()) < MIN_CHUNK_WORDS:
        return None

    display_name = site_name or page_title or "This Website"
    overview_text = f"{display_name} overview. {combined}".strip()
    return ChunkData(
        text=overview_text,
        prefixed_text=f"[{display_name} > Site Overview]\n\n{overview_text}",
        section="Site Overview",
        position=0,
        token_count=_token_estimate(overview_text),
        page_url=page_url,
        page_title=page_title or display_name,
    )


def _split_sentences(text: str) -> list[dict[str, int | str]]:
    pattern = re.compile(r"(?<=[.?!])(?:\s+|\n+)")
    sentences: list[dict[str, int | str]] = []
    last_end = 0
    for match in pattern.finditer(text):
        sentence = text[last_end:match.start()].strip()
        if sentence:
            sentences.append({"text": sentence, "start": last_end})
        last_end = match.end()
    tail = text[last_end:].strip()
    if tail:
        sentences.append({"text": tail, "start": last_end})
    return sentences


def _heading_positions(content: ExtractedContent) -> list[dict[str, int | str]]:
    positions: list[dict[str, int | str]] = []
    search_from = 0
    lower_text = content.text.lower()
    for heading in content.headings:
        heading_text = str(heading["text"]).strip()
        if not heading_text:
            continue
        idx = lower_text.find(heading_text.lower(), search_from)
        if idx == -1:
            idx = lower_text.find(heading_text.lower())
        if idx == -1:
            continue
        positions.append({"start": idx, "level": int(heading["level"]), "text": heading_text})
        search_from = idx + len(heading_text)
    return positions


def _token_estimate(text: str) -> int:
    return math.ceil(len(text.split()) * 1.33)


def _build_section(state: dict[int, str]) -> str:
    if state.get(3):
        if state.get(2):
            return f"{state[2]} > {state[3]}"
        if state.get(1):
            return f"{state[1]} > {state[3]}"
        return state[3]
    if state.get(2):
        if state.get(1):
            return f"{state[1]} > {state[2]}"
        return state[2]
    return state.get(1, "") or "General"


def _section_for_position(heading_positions: list[dict[str, int | str]], chunk_start: int) -> str:
    section_state: dict[int, str] = {}
    for heading in heading_positions:
        if int(heading["start"]) > chunk_start:
            break
        level = int(heading["level"])
        section_state[level] = str(heading["text"])
        if level == 1:
            section_state.pop(2, None)
            section_state.pop(3, None)
        elif level == 2:
            section_state.pop(3, None)
    return _build_section(section_state)


def should_inject_pricing_hints(page_url: str, page_title: str, section: str, text: str) -> bool:
    combined = f"{page_url} {page_title} {section} {text}".lower()
    return sum(1 for keyword in PRICING_HINT_KEYWORDS if keyword in combined) >= 2


def chunk_page(content: ExtractedContent, page_url: str, page_title: str) -> list[ChunkData]:
    sentences = _split_sentences(content.text)
    if not sentences:
        return []

    heading_positions = _heading_positions(content)
    chunks: list[ChunkData] = []
    target_words = max(1, int(CHUNK_TARGET_TOKENS / 1.33))
    overlap_words = max(1, int(CHUNK_OVERLAP_TOKENS / 1.33))
    start_index = 0
    position = 0

    while start_index < len(sentences):
        current_sentences: list[str] = []
        current_words = 0
        end_index = start_index

        while end_index < len(sentences):
            sentence_text = str(sentences[end_index]["text"])
            sentence_words = len(sentence_text.split())
            if current_sentences and current_words + sentence_words > target_words:
                break
            current_sentences.append(sentence_text)
            current_words += sentence_words
            end_index += 1
            if current_words >= target_words:
                break

        if not current_sentences:
            break

        chunk_text = " ".join(current_sentences).strip()
        if len(chunk_text.split()) >= MIN_CHUNK_WORDS:
            chunk_start = int(sentences[start_index]["start"])
            section = _section_for_position(heading_positions, chunk_start)
            if should_inject_pricing_hints(page_url, page_title or "Untitled Page", section, chunk_text):
                pricing_synonyms = "[pricing billing payment cost plans subscription fees how much per month per year charge invoice]"
                prefix = f"[{page_title or 'Untitled Page'} > {section}]\n{pricing_synonyms}\n\n"
            else:
                prefix = f"[{page_title or 'Untitled Page'} > {section}]\n\n"
            chunks.append(
                ChunkData(
                    text=chunk_text,
                    prefixed_text=prefix + chunk_text,
                    section=section,
                    position=position,
                    token_count=_token_estimate(chunk_text),
                    page_url=page_url,
                    page_title=page_title or "Untitled Page",
                )
            )
            position += 1

        if end_index >= len(sentences):
            break

        overlap_count = 0
        new_start = end_index
        while new_start > start_index:
            overlap_count += len(str(sentences[new_start - 1]["text"]).split())
            new_start -= 1
            if overlap_count >= overlap_words:
                break
        start_index = new_start if new_start != start_index else end_index

    return chunks


def chunk_ui_structure(
    html: str,
    page_url: str,
    page_title: str,
    page_id: str,
    site_id: str,
) -> ChunkData | None:
    structure = extract_ui_structure(html, page_url, page_title)
    text = ui_structure_to_text(structure)
    if not text or len(text.split()) < 15:
        return None
    prefixed = f"[{page_title or 'Untitled Page'} > UI Layout & Navigation]\n\n{text}"
    return ChunkData(
        text=text,
        prefixed_text=prefixed,
        section="UI Layout & Navigation",
        position=-1,
        token_count=len(text.split()),
        page_url=page_url,
        page_title=page_title or "Untitled Page",
        page_id=page_id,
        site_id=site_id,
    )
