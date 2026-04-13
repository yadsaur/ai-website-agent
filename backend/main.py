from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy import delete, select, text
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.chunker import build_site_overview_chunk, chunk_page, chunk_ui_structure
from backend.config import (
    BASE_URL,
    DB_PATH,
    DATABASE_URL,
    MAX_CRAWL_DEPTH,
    MAX_CRAWL_PAGES,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    PROCESS_RETRY_ATTEMPTS,
    PROCESS_RETRY_DELAY_SECONDS,
    QUESTION_SUGGESTION_CACHE_TTL_SECONDS,
    UI_CHUNK_SECTION_LABEL,
)
from backend.crawler import crawl_site, normalize_url
from backend.database import engine, get_db, init_db, session_scope
from backend.embedder import get_embedder
from backend.extractor import extract_content
from backend.llm import generate_answer
from backend.models import Chunk, Page, Site
from backend.retriever import classify_query_intent, retrieve
from backend.schemas import CreateSiteRequest, CreateSiteResponse, EmbedScriptResponse, SiteListResponse, SiteStatusResponse, SiteSummary
from backend.session_store import append_turn, build_contextual_query, get_history
from backend.vector_store import write_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_bg_tasks: set[asyncio.Task] = set()
FALLBACK_MESSAGE = (
    "I don't have that specific information here, but the team at "
    "{site_name} would be able to give you a definitive answer. "
    "Is there anything else about the product I can help you with?"
)
SYNTHETIC_SECTIONS = {"Site Overview", "UI Layout & Navigation"}
STARTER_QUESTION_FALLBACK = [
    "What does this website do?",
    "How can I get started?",
    "What are the main features?",
]
_suggested_question_cache: dict[str, dict[str, Any]] = {}

BASE_DIR = Path(__file__).resolve().parent.parent
WIDGET_PATH = BASE_DIR / "widget" / "agent.js"
DASHBOARD_PATH = BASE_DIR / "dashboard" / "index.html"


def _parse_json_array(text_value: str, expected_length: int | None = None) -> list[str]:
    try:
        parsed = json.loads(text_value)
    except json.JSONDecodeError:
        start = text_value.find("[")
        end = text_value.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed = json.loads(text_value[start : end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
    if expected_length is not None:
        cleaned = cleaned[:expected_length]
    return cleaned


async def _openrouter_completion(system_prompt: str, user_prompt: str, max_tokens: int = 200) -> str | None:
    if not OPENROUTER_API_KEY:
        return None

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }
    timeout = httpx.Timeout(15.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return None
            return choices[0].get("message", {}).get("content", "")
    except Exception:
        logger.warning("OpenRouter completion request failed", exc_info=True)
        return None


def _is_valid_source(chunk, chunk_position: int | None) -> bool:
    if chunk.section in SYNTHETIC_SECTIONS:
        return False
    if chunk.page_title and "Site Overview" in chunk.page_title:
        return False
    if chunk_position == -1:
        return False
    return True


def _build_source_payload(chunks, positions_by_chunk_id: dict[str, int | None]) -> list[dict[str, str]]:
    seen_urls: set[str] = set()
    sources: list[dict[str, str]] = []
    for chunk in chunks:
        if not _is_valid_source(chunk, positions_by_chunk_id.get(chunk.chunk_id)):
            continue
        if not chunk.page_url or chunk.page_url in seen_urls:
            continue
        seen_urls.add(chunk.page_url)
        sources.append(
            {
                "url": chunk.page_url,
                "title": chunk.page_title,
                "section": chunk.section,
            }
        )
        if len(sources) >= 1:
            break
    return sources


def _get_cached_suggested_questions(site_id: str) -> list[str] | None:
    cached = _suggested_question_cache.get(site_id)
    if not cached:
        return None
    if time() - float(cached.get("timestamp", 0)) > QUESTION_SUGGESTION_CACHE_TTL_SECONDS:
        _suggested_question_cache.pop(site_id, None)
        return None
    return list(cached.get("questions", []))


def _set_cached_suggested_questions(site_id: str, questions: list[str]) -> None:
    _suggested_question_cache[site_id] = {"timestamp": time(), "questions": list(questions)}

app = FastAPI(title="AI Website Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    if not DATABASE_URL:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("pages")}
    if "html_content" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE pages ADD COLUMN html_content TEXT"))


def _serialize_status(site: Site) -> SiteStatusResponse:
    return SiteStatusResponse(
        site_id=site.id,
        status=site.status or "pending",
        page_count=site.page_count or 0,
        chunk_count=site.chunk_count or 0,
        name=site.name,
        error_msg=site.error_msg,
    )


async def process_site(site_id: str, root_url: str):
    try:
        with session_scope() as db:
            site = db.get(Site, site_id)
            if site is None:
                return
            site.status = "crawling"
            site.updated_at = datetime.utcnow()
        last_error: Exception | None = None
        for attempt in range(1, PROCESS_RETRY_ATTEMPTS + 1):
            try:
                with session_scope() as db:
                    db.execute(delete(Chunk).where(Chunk.site_id == site_id))
                    db.execute(delete(Page).where(Page.site_id == site_id))
                    site = db.get(Site, site_id)
                    if site is not None:
                        site.page_count = 0
                        site.chunk_count = 0
                        site.error_msg = None
                        site.updated_at = datetime.utcnow()

                pages = await crawl_site(root_url, site_id=site_id, max_pages=MAX_CRAWL_PAGES, max_depth=MAX_CRAWL_DEPTH)
                if not pages:
                    raise ValueError("No content could be extracted")

                vector_chunks: list[dict[str, object]] = []
                site_name = None
                total_pages = 0
                total_chunks = 0

                for page_result in pages:
                    extracted = await asyncio.to_thread(extract_content, page_result.html, page_result.url)
                    if not extracted.text.strip():
                        continue

                    page_title = extracted.title or page_result.title or page_result.url
                    if site_name is None:
                        site_name = page_title

                    page_id = str(uuid4())
                    page_chunks = await asyncio.to_thread(chunk_page, extracted, page_result.url, page_title)
                    if total_pages == 0:
                        overview_chunk = await asyncio.to_thread(
                            build_site_overview_chunk,
                            extracted,
                            page_result.url,
                            page_title,
                            site_name,
                        )
                        if overview_chunk is not None:
                            page_chunks = [overview_chunk] + page_chunks

                    with session_scope() as db:
                        db.add(
                            Page(
                                id=page_id,
                                site_id=site_id,
                                url=page_result.url,
                                title=page_title,
                                depth=page_result.depth,
                                word_count=extracted.word_count,
                                crawled_at=datetime.utcnow(),
                                http_status=page_result.http_status,
                                html_content=page_result.html,
                            )
                        )
                        for chunk in page_chunks:
                            chunk_id = str(uuid4())
                            db.add(
                                Chunk(
                                    id=chunk_id,
                                    site_id=site_id,
                                    page_id=page_id,
                                    page_url=chunk.page_url,
                                    page_title=chunk.page_title,
                                    section=chunk.section,
                                    position=chunk.position,
                                    text=chunk.text,
                                    token_count=chunk.token_count,
                                    created_at=datetime.utcnow(),
                                )
                            )
                            vector_chunks.append(
                                {
                                    "chunk_id": chunk_id,
                                    "page_url": chunk.page_url,
                                    "page_title": chunk.page_title,
                                    "section": chunk.section,
                                    "position": chunk.position,
                                    "text": chunk.text,
                                    "token_count": chunk.token_count,
                                    "prefixed_text": chunk.prefixed_text,
                                }
                            )
                        ui_chunk = chunk_ui_structure(
                            html=page_result.html,
                            page_url=page_result.url,
                            page_title=page_title,
                            page_id=page_id,
                            site_id=site_id,
                        )
                        if ui_chunk is not None:
                            chunk_id = str(uuid4())
                            db.add(
                                Chunk(
                                    id=chunk_id,
                                    site_id=site_id,
                                    page_id=page_id,
                                    page_url=ui_chunk.page_url,
                                    page_title=ui_chunk.page_title,
                                    section=ui_chunk.section,
                                    position=ui_chunk.position,
                                    text=ui_chunk.text,
                                    token_count=ui_chunk.token_count,
                                    created_at=datetime.utcnow(),
                                )
                            )
                            vector_chunks.append(
                                {
                                    "chunk_id": chunk_id,
                                    "page_url": ui_chunk.page_url,
                                    "page_title": ui_chunk.page_title,
                                    "section": ui_chunk.section,
                                    "position": ui_chunk.position,
                                    "text": ui_chunk.text,
                                    "token_count": ui_chunk.token_count,
                                    "prefixed_text": ui_chunk.prefixed_text,
                                }
                            )

                        site = db.get(Site, site_id)
                        if site is not None:
                            total_pages += 1
                            total_chunks += len(page_chunks) + (1 if ui_chunk is not None else 0)
                            site.page_count = total_pages
                            site.chunk_count = total_chunks
                            site.name = site_name or site.name
                            site.updated_at = datetime.utcnow()

                if total_pages == 0 or total_chunks == 0:
                    raise ValueError("No content could be extracted")

                with session_scope() as db:
                    site = db.get(Site, site_id)
                    if site is not None:
                        site.status = "embedding"
                        site.updated_at = datetime.utcnow()

                prefixed_texts = [str(item["prefixed_text"]) for item in vector_chunks]
                embeddings = await asyncio.to_thread(lambda: get_embedder().embed_chunks(prefixed_texts))
                await write_vector_store(site_id, vector_chunks, embeddings)

                with session_scope() as db:
                    site = db.get(Site, site_id)
                    if site is not None:
                        site.status = "ready"
                        site.error_msg = None
                        site.name = site_name or site.name
                        site.updated_at = datetime.utcnow()
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Processing attempt %s/%s failed for %s: %s",
                    attempt,
                    PROCESS_RETRY_ATTEMPTS,
                    site_id,
                    exc,
                    exc_info=True,
                )
                if attempt < PROCESS_RETRY_ATTEMPTS:
                    await asyncio.sleep(PROCESS_RETRY_DELAY_SECONDS)
                    with session_scope() as db:
                        site = db.get(Site, site_id)
                        if site is not None:
                            site.status = "crawling"
                            site.updated_at = datetime.utcnow()
                    continue
                raise last_error
    except Exception as exc:
        logger.exception("Failed to process site %s", site_id)
        with session_scope() as db:
            site = db.get(Site, site_id)
            if site is not None:
                site.status = "error"
                site.error_msg = str(exc)
                site.updated_at = datetime.utcnow()


@app.post("/api/sites", response_model=CreateSiteResponse)
async def create_site(payload: CreateSiteRequest, db: Session = Depends(get_db)):
    try:
        normalized_url = normalize_url(str(payload.url))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid URL: {exc}") from exc

    site_id = str(uuid4())
    db.add(
        Site(
            id=site_id,
            url=normalized_url,
            name=None,
            status="pending",
            page_count=0,
            chunk_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            error_msg=None,
        )
    )
    db.commit()
    task = asyncio.create_task(process_site(site_id, normalized_url))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return CreateSiteResponse(site_id=site_id, status="pending")


@app.get("/api/sites", response_model=SiteListResponse)
async def list_sites(db: Session = Depends(get_db)):
    sites = db.execute(select(Site).order_by(Site.created_at.desc())).scalars().all()
    return SiteListResponse(
        sites=[
            SiteSummary(
                site_id=site.id,
                url=site.url,
                name=site.name,
                status=site.status or "pending",
                page_count=site.page_count or 0,
                chunk_count=site.chunk_count or 0,
                error_msg=site.error_msg,
            )
            for site in sites
        ]
    )


async def _rebuild_site_vectors(site_id: str) -> None:
    with session_scope() as db:
        db_chunks = db.execute(select(Chunk).where(Chunk.site_id == site_id).order_by(Chunk.page_id, Chunk.position, Chunk.created_at)).scalars().all()
        vector_chunks = [
            {
                "chunk_id": chunk.id,
                "page_url": chunk.page_url or "",
                "page_title": chunk.page_title or "",
                "section": chunk.section or "",
                "position": chunk.position if chunk.position is not None else 0,
                "text": chunk.text,
                "token_count": chunk.token_count or len(chunk.text.split()),
                "prefixed_text": f"[{chunk.page_title or 'Untitled Page'} > {chunk.section or 'General'}]\n\n{chunk.text}",
            }
            for chunk in db_chunks
        ]

    if not vector_chunks:
        await write_vector_store(site_id, [], np.empty((0, 384), dtype=np.float32))
        return

    prefixed_texts = [item["prefixed_text"] for item in vector_chunks]
    embeddings = await asyncio.to_thread(lambda: get_embedder().embed_chunks(prefixed_texts))
    await write_vector_store(site_id, vector_chunks, embeddings)


@app.get("/api/sites/{site_id}/status", response_model=SiteStatusResponse)
async def site_status(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return _serialize_status(site)


@app.post("/api/sites/{site_id}/reprocess-ui")
async def reprocess_ui(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    pages = db.execute(select(Page).where(Page.site_id == site_id).order_by(Page.crawled_at.asc())).scalars().all()
    if not pages:
        raise HTTPException(status_code=404, detail="No pages found for site")

    ui_chunks_added = 0
    with session_scope() as session:
        site_record = session.get(Site, site_id)
        if site_record is not None:
            site_record.status = "embedding"
            site_record.updated_at = datetime.utcnow()

    for page in pages:
        html_content = page.html_content
        if not html_content:
            try:
                fetched_pages = await crawl_site(page.url, site_id=site_id, max_pages=1, max_depth=0)
                if fetched_pages:
                    html_content = fetched_pages[0].html
                    with session_scope() as session:
                        page_record = session.get(Page, page.id)
                        if page_record is not None:
                            page_record.html_content = html_content
            except Exception:
                logger.warning("Unable to refetch HTML for %s during UI reprocess", page.url, exc_info=True)
                continue
        if not html_content:
            continue

        ui_chunk = chunk_ui_structure(
            html=html_content,
            page_url=page.url,
            page_title=page.title or "",
            page_id=page.id,
            site_id=site_id,
        )

        with session_scope() as session:
            session.execute(
                delete(Chunk).where(
                    Chunk.page_id == page.id,
                    Chunk.section == UI_CHUNK_SECTION_LABEL,
                )
            )
            if ui_chunk is not None:
                session.add(
                    Chunk(
                        id=str(uuid4()),
                        site_id=site_id,
                        page_id=page.id,
                        page_url=ui_chunk.page_url,
                        page_title=ui_chunk.page_title,
                        section=ui_chunk.section,
                        position=ui_chunk.position,
                        text=ui_chunk.text,
                        token_count=ui_chunk.token_count,
                        created_at=datetime.utcnow(),
                    )
                )
                ui_chunks_added += 1

    with session_scope() as session:
        chunk_count = session.execute(select(Chunk).where(Chunk.site_id == site_id)).scalars().all()
        site_record = session.get(Site, site_id)
        if site_record is not None:
            site_record.chunk_count = len(chunk_count)
            site_record.status = "embedding"
            site_record.updated_at = datetime.utcnow()

    await _rebuild_site_vectors(site_id)

    with session_scope() as session:
        site_record = session.get(Site, site_id)
        if site_record is not None:
            site_record.status = "ready"
            site_record.error_msg = None
            site_record.updated_at = datetime.utcnow()

    return {"status": "ok", "ui_chunks_added": ui_chunks_added}


@app.post("/api/sites/{site_id}/retry")
async def retry_site(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    db.execute(delete(Chunk).where(Chunk.site_id == site_id))
    db.execute(delete(Page).where(Page.site_id == site_id))
    site.status = "pending"
    site.page_count = 0
    site.chunk_count = 0
    site.name = None
    site.error_msg = None
    site.updated_at = datetime.utcnow()
    db.commit()

    task = asyncio.create_task(process_site(site_id, site.url))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return {"status": "pending", "site_id": site_id}


@app.get("/api/sites/{site_id}/suggested-questions")
async def suggested_questions(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None or site.status != "ready":
        return {"questions": []}

    cached = _get_cached_suggested_questions(site_id)
    if cached is not None:
        return {"questions": cached}

    pages = db.execute(select(Page).where(Page.site_id == site_id).order_by(Page.depth.asc(), Page.crawled_at.asc())).scalars().all()
    if not pages:
        return {"questions": []}

    homepage_page_ids = {page.id for page in pages if page.depth == 0}
    first_three_page_ids = {page.id for page in pages[:3]}
    db_chunks = db.execute(select(Chunk).where(Chunk.site_id == site_id).order_by(Chunk.created_at.asc(), Chunk.position.asc())).scalars().all()

    selected_texts: list[str] = []
    seen_chunk_ids: set[str] = set()

    for chunk in db_chunks:
        if chunk.section == "Site Overview" and chunk.id not in seen_chunk_ids:
            selected_texts.append(chunk.text)
            seen_chunk_ids.add(chunk.id)
            break

    for chunk in db_chunks:
        if chunk.id in seen_chunk_ids:
            continue
        if chunk.page_id in homepage_page_ids:
            selected_texts.append(chunk.text)
            seen_chunk_ids.add(chunk.id)
        if len(selected_texts) >= 12:
            break

    for chunk in db_chunks:
        if chunk.id in seen_chunk_ids:
            continue
        if chunk.page_id in first_three_page_ids:
            selected_texts.append(chunk.text)
            seen_chunk_ids.add(chunk.id)
        if len(selected_texts) >= 12:
            break

    for chunk in db_chunks:
        if chunk.id in seen_chunk_ids:
            continue
        selected_texts.append(chunk.text)
        seen_chunk_ids.add(chunk.id)
        if len(selected_texts) >= 12:
            break

    content_sample = ""
    for sample in selected_texts:
        addition = f"{sample}\n\n"
        if len(content_sample) + len(addition) > 3000:
            content_sample += addition[: max(0, 3000 - len(content_sample))]
            break
        content_sample += addition
    content_sample = content_sample.strip()
    if not content_sample:
        return {"questions": []}

    system_prompt = """You are analyzing a website's content to generate 3 suggested questions for a chat widget that serves as an AI sales assistant. These questions should be the 3 things a new visitor is MOST LIKELY to wonder about when deciding whether to buy or sign up.

Prioritize questions about:
1. Pricing or plans (if pricing info exists in the content)
2. What the product does / who it's for
3. How to get started or whether there's a free trial

Rules:
- Each question must be answerable from the website content provided
- Maximum 9 words per question
- Sound natural and conversational — like a real person typed it
- Do NOT use phrases like "Can you tell me about..." — just ask directly
- Prioritize the questions with highest buying-decision relevance

Examples of GOOD questions:
  "How much does the Pro plan cost?"
  "Is there a free trial I can start today?"
  "What's the difference between the Basic and Pro plans?"

Examples of BAD questions:
  "Can you provide information about your service offerings?"
  "What is the nature of your enterprise solutions?"

Respond ONLY with a JSON array of exactly 3 strings. No other text."""
    user_prompt = f"Website content sample:\n{content_sample}"
    response_text = await _openrouter_completion(system_prompt, user_prompt, max_tokens=200)
    questions = _parse_json_array(response_text or "", expected_length=3)
    if len(questions) != 3:
        questions = STARTER_QUESTION_FALLBACK
    _set_cached_suggested_questions(site_id, questions)
    return {"questions": questions}


@app.post("/api/sites/{site_id}/followup-questions")
async def followup_questions(site_id: str, request: Request, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        return {"questions": []}

    try:
        payload = await request.json()
    except Exception:
        return {"questions": []}

    last_question = str(payload.get("last_question", "")).strip()
    last_answer = str(payload.get("last_answer", "")).strip()
    if not last_question or not last_answer:
        return {"questions": []}

    system_prompt = """You are an AI sales assistant analyzing a chat conversation to suggest what a website visitor might want to ask next. Your goal is to suggest follow-up questions that naturally advance the visitor toward making a purchase decision.

After the user's question and the bot's answer, suggest 2 follow-up questions using this logic:
- If the answer was about a feature: suggest a question about pricing OR about how to get started
- If the answer was about pricing: suggest a question about what's included OR about the free trial
- If the answer was about the company/trust: suggest a question about a specific feature OR about getting started
- If the answer was about integrations: suggest a question about pricing OR about setup time
- Always make at least one suggestion that moves toward action (free trial, demo, sign up, pricing)

Rules:
- Maximum 9 words per question
- Natural, conversational tone — real person language
- Must be directly relevant to what was just discussed
- Must be answerable from website content (not random generic questions)

Respond ONLY with a JSON array of exactly 2 strings. No other text."""
    user_prompt = f"User just asked: {last_question}\nBot answered: {last_answer}\n\nSuggest 2 follow-up questions."
    try:
        response_text = await _openrouter_completion(system_prompt, user_prompt, max_tokens=150)
        questions = _parse_json_array(response_text or "", expected_length=2)
        if len(questions) != 2:
            return {"questions": []}
        return {"questions": questions}
    except Exception:
        return {"questions": []}


@app.get("/api/sites/{site_id}/embed-script", response_model=EmbedScriptResponse)
async def embed_script(site_id: str, request: Request, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    base = BASE_URL or str(request.base_url).rstrip("/")
    return EmbedScriptResponse(script_tag=f"<script src='{base}/widget/agent.js' data-site-id='{site_id}'></script>")


@app.get("/api/chat")
async def chat(site_id: str = Query(...), q: str = Query(...), session_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        history = get_history(site_id, session_id)
        effective_query = build_contextual_query(q, history)
        chunks, intent = await asyncio.to_thread(retrieve, site_id, effective_query)
        fallback_text = FALLBACK_MESSAGE.format(site_name=site.name or site.url)
        if not chunks:
            append_turn(site_id, session_id, "user", q)
            append_turn(site_id, session_id, "assistant", fallback_text)
            yield f"data: {json.dumps({'type': 'token', 'content': fallback_text})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        positions_by_chunk_id = {
            chunk_row.id: chunk_row.position
            for chunk_row in db.execute(select(Chunk).where(Chunk.id.in_(chunk_ids))).scalars().all()
        }
        append_turn(site_id, session_id, "user", q)
        response_parts: list[str] = []
        async for token in generate_answer(q, chunks, site.name or site.url, intent=intent, history=history):
            response_parts.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        final_answer = "".join(response_parts).strip()
        unique_sources = _build_source_payload(chunks, positions_by_chunk_id)
        if unique_sources and final_answer != fallback_text:
            yield f"data: {json.dumps({'type': 'sources', 'urls': [item['url'] for item in unique_sources], 'sources': unique_sources})}\n\n"
        append_turn(site_id, session_id, "assistant", final_answer)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/widget/agent.js")
async def widget_script():
    return FileResponse(WIDGET_PATH, media_type="application/javascript")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
async def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")
