from __future__ import annotations

import asyncio
import colorsys
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlencode
from pathlib import Path
from time import time
from typing import Any, AsyncGenerator
from uuid import uuid4

import httpx
import numpy as np
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.billing import (
    BillingConfigError,
    BillingVerificationError,
    create_checkout_session,
    list_plan_definitions,
    process_webhook_event,
    verify_webhook_payload,
)
from backend.chunker import build_site_overview_chunk, chunk_page, chunk_ui_structure
from backend.config import (
    BASE_URL,
    DB_PATH,
    DATABASE_URL,
    DEFAULT_SITES_LIMIT,
    GOOGLE_CLIENT_ID,
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
    TRIAL_DURATION_DAYS,
    UI_CHUNK_SECTION_LABEL,
)
from backend.auth import (
    GOOGLE_ONLY_PASSWORD_HASH,
    build_viewer_context,
    clear_auth_cookie,
    get_current_user,
    hash_password,
    is_google_only_user,
    set_auth_cookie,
    verify_password,
)
from backend.crawler import crawl_site, normalize_url
from backend.database import engine, get_db, init_db, session_scope
from backend.embedder import get_embedder
from backend.entitlements import TRIAL_ENDED_MESSAGE, evaluate_site_entitlement, sync_user_subscription_status, trial_days_remaining
from backend.extractor import extract_content
from backend.llm import generate_answer
from backend.models import Chunk, Page, Site, User
from backend.retriever import classify_query_intent, retrieve
from backend.schemas import (
    AuthProviderConfigResponse,
    AuthResponse,
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingPlansResponse,
    BillingPlanSummary,
    BillingStatusResponse,
    CreateSiteRequest,
    CreateSiteResponse,
    EmbedScriptResponse,
    GoogleAuthRequest,
    LoginRequest,
    LogoutResponse,
    SignupRequest,
    SiteListResponse,
    SiteStatusResponse,
    SiteSummary,
    UserSummary,
)
from backend.session_store import append_turn, build_contextual_query, get_history
from backend.vector_store import invalidate_cache, write_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_bg_tasks: dict[str, asyncio.Task] = {}
FALLBACK_MESSAGE = (
    "I couldn't find that information in the website content I have for "
    "{site_name}. You may want to contact the business directly, or ask me "
    "another question about this site."
)
GREETING_RESPONSES = {
    "hi": "Hi! How can I help you today?",
    "hello": "Hello! I can help answer questions about this site.",
    "hey": "Hey! What would you like to know about this website?",
    "good morning": "Good morning! What would you like to know about this website?",
    "good afternoon": "Good afternoon! What can I help you find on this site?",
    "good evening": "Good evening! I can help answer questions about this site.",
    "thanks": "You're welcome. Anything else I can help you find on this site?",
    "thank you": "You're welcome. Anything else I can help you with?",
    "bye": "Thanks for stopping by. Have a good one.",
    "goodbye": "Thanks for stopping by. Have a good one.",
}
SYNTHETIC_SECTIONS = {"Site Overview", "UI Layout & Navigation"}
STARTER_QUESTION_FALLBACK = [
    "What does this website do?",
    "How can I get started?",
    "What are the main features?",
]
_suggested_question_cache: dict[str, dict[str, Any]] = {}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BASE_DIR = Path(__file__).resolve().parent.parent
WIDGET_PATH = BASE_DIR / "widget" / "agent.js"
DASHBOARD_PATH = BASE_DIR / "dashboard" / "index.html"
WEBSITE_DIR = BASE_DIR / "website"
HEX_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_COLOR_PATTERN = re.compile(r"rgba?\(([^)]+)\)")
THEME_COLOR_META_PATTERN = re.compile(
    r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)["\']',
    flags=re.IGNORECASE,
)


def _normalize_simple_message(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _simple_conversational_reply(query: str) -> str | None:
    normalized = _normalize_simple_message(query)
    if not normalized:
        return None
    if normalized in GREETING_RESPONSES:
        return GREETING_RESPONSES[normalized]

    tokens = normalized.split()
    if 1 <= len(tokens) <= 3 and tokens[0] in {"hi", "hello", "hey"}:
        return GREETING_RESPONSES[tokens[0]]

    for phrase in ("good morning", "good afternoon", "good evening"):
        if normalized.startswith(phrase):
            return GREETING_RESPONSES[phrase]
    if normalized in {"thanks", "thank you", "thankyou", "thx"}:
        return GREETING_RESPONSES["thanks"]
    if normalized in {"bye", "goodbye", "see you"}:
        return GREETING_RESPONSES["bye"]
    return None


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _normalize_site_input_url(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        raise ValueError("Please enter a website URL.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        candidate = f"https://{candidate}"
    return normalize_url(candidate)


def _parse_color_token(token: str) -> tuple[int, int, int] | None:
    value = token.strip()
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) in {3, 4}:
            hex_value = "".join(ch * 2 for ch in hex_value[:3])
        elif len(hex_value) >= 6:
            hex_value = hex_value[:6]
        if len(hex_value) != 6:
            return None
        try:
            return tuple(int(hex_value[index : index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            return None

    match = RGB_COLOR_PATTERN.match(value)
    if not match:
        return None
    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) < 3:
        return None
    rgb: list[int] = []
    for part in parts[:3]:
        try:
            channel = int(float(part.replace("%", "")))
        except ValueError:
            return None
        rgb.append(max(0, min(255, channel)))
    return tuple(rgb)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = [channel / 255 for channel in rgb]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _color_saturation(rgb: tuple[int, int, int]) -> float:
    return colorsys.rgb_to_hls(*(channel / 255 for channel in rgb))[2]


def _mix(rgb: tuple[int, int, int], target: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(
        max(0, min(255, round(channel * (1 - ratio) + target_channel * ratio)))
        for channel, target_channel in zip(rgb, target)
    )


def _extract_site_theme(page_html: str | None) -> dict[str, str]:
    default = {
        "accent": "#7c3aed",
        "accent_strong": "#5b21b6",
        "background": "#0a0f1d",
        "panel_top": "#111827",
        "panel_bottom": "#0b1120",
        "text": "#f8fafc",
        "muted": "#94a3b8",
    }
    if not page_html:
        return default

    tokens: list[str] = []
    theme_match = THEME_COLOR_META_PATTERN.search(page_html)
    if theme_match:
        tokens.append(theme_match.group(1))
    tokens.extend(HEX_COLOR_PATTERN.findall(page_html))
    for match in RGB_COLOR_PATTERN.finditer(page_html):
        tokens.append(match.group(0))

    parsed = [_parse_color_token(token) for token in tokens]
    colors = [item for item in parsed if item is not None]
    if not colors:
        return default

    counts = Counter(colors)
    dark_candidates = [color for color, _ in counts.most_common() if _relative_luminance(color) < 0.45]
    light_candidates = [color for color, _ in counts.most_common() if _relative_luminance(color) >= 0.45]
    accent_candidates = [
        color
        for color, _ in counts.most_common()
        if _color_saturation(color) >= 0.25 and 0.12 < _relative_luminance(color) < 0.9
    ]

    background = dark_candidates[0] if dark_candidates else _parse_color_token(default["background"])
    if background is None:
        background = (10, 15, 29)
    accent = accent_candidates[0] if accent_candidates else (124, 58, 237)
    panel_top = _mix(background, accent, 0.12)
    panel_bottom = _mix(background, (0, 0, 0), 0.2)
    text_color = (248, 250, 252) if _relative_luminance(background) < 0.58 else (15, 23, 42)
    muted_base = light_candidates[0] if light_candidates else text_color
    muted = _mix(muted_base, background, 0.35 if _relative_luminance(background) < 0.58 else 0.55)

    return {
        "accent": _rgb_to_hex(accent),
        "accent_strong": _rgb_to_hex(_mix(accent, (0, 0, 0), 0.22)),
        "background": _rgb_to_hex(background),
        "panel_top": _rgb_to_hex(panel_top),
        "panel_bottom": _rgb_to_hex(panel_bottom),
        "text": _rgb_to_hex(text_color),
        "muted": _rgb_to_hex(muted),
    }


def _resolve_site_theme(db: Session, site_id: str) -> dict[str, str]:
    homepage = db.execute(
        select(Page).where(Page.site_id == site_id).order_by(Page.depth.asc(), Page.crawled_at.asc())
    ).scalars().first()
    if homepage is None:
        return _extract_site_theme(None)
    return _extract_site_theme(homepage.html_content)


def _serialize_user(user: User | None, db: Session | None = None) -> UserSummary | None:
    if user is None:
        return None
    if db is not None:
        sync_user_subscription_status(db, user)
    return UserSummary(
        id=user.id,
        email=user.email,
        subscription_id=user.subscription_id,
        subscription_status=user.subscription_status or "trial",
        subscription_plan=user.subscription_plan,
        trial_start_at=_utc_iso(user.trial_start_at),
        trial_ends_at=_utc_iso(user.trial_ends_at),
        current_period_end=_utc_iso(user.current_period_end),
        days_remaining=trial_days_remaining(user),
        sites_limit=user.sites_limit,
    )


def _serialize_billing_plans(user: User | None = None) -> list[BillingPlanSummary]:
    current_plan = (user.subscription_plan or "").strip().lower() if user is not None else ""
    plans: list[BillingPlanSummary] = []
    for plan in list_plan_definitions():
        plans.append(
            BillingPlanSummary(
                key=plan.key,
                label=plan.label,
                sites_limit=plan.sites_limit,
                usage_limit=plan.usage_limit,
                checkout_enabled=bool(plan.dodo_price_id),
                current=current_plan == plan.key,
            )
        )
    return plans


def _validate_credentials(email: str, password: str) -> tuple[str, str]:
    normalized_email = email.strip().lower()
    if not EMAIL_PATTERN.match(normalized_email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters long.")
    return normalized_email, password


def _google_provider_config() -> AuthProviderConfigResponse:
    return AuthProviderConfigResponse(
        google_enabled=bool(GOOGLE_CLIENT_ID),
        google_client_id=GOOGLE_CLIENT_ID or None,
    )


def _verify_google_credential(credential: str) -> dict[str, Any]:
    token = credential.strip()
    if not token:
        raise HTTPException(status_code=422, detail="Missing Google credential.")
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        id_info = google_id_token.verify_oauth2_token(
            token,
            google_auth_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token.") from exc

    issuer = str(id_info.get("iss") or "")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token.")

    email = str(id_info.get("email") or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=401, detail="Google account did not return a valid email address.")
    if not id_info.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account email is not verified.")

    google_sub = str(id_info.get("sub") or "").strip()
    if not google_sub:
        raise HTTPException(status_code=401, detail="Google account ID is missing.")

    return {
        "sub": google_sub,
        "email": email,
        "name": str(id_info.get("name") or "").strip(),
        "picture": str(id_info.get("picture") or "").strip(),
    }


def _complete_google_auth(
    db: Session,
    request: Request,
    response: Response,
    google_profile: dict[str, Any],
) -> AuthResponse:
    google_sub = google_profile["sub"]
    email = google_profile["email"]
    viewer = build_viewer_context(request, db, response=response)

    user = db.execute(select(User).where(User.google_sub == google_sub)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is not None:
            conflict_user = db.execute(
                select(User).where(User.google_sub == google_sub, User.id != user.id)
            ).scalar_one_or_none()
            if conflict_user is not None:
                raise HTTPException(status_code=409, detail="This Google account is already linked to another user.")
            user.google_sub = google_sub
            db.add(user)
        else:
            now = datetime.utcnow()
            user = User(
                id=str(uuid4()),
                email=email,
                password_hash=GOOGLE_ONLY_PASSWORD_HASH,
                google_sub=google_sub,
                created_at=now,
                trial_start_at=now,
                trial_ends_at=now + timedelta(days=TRIAL_DURATION_DAYS),
                subscription_status="trial",
                subscription_plan="trial",
                sites_limit=DEFAULT_SITES_LIMIT,
            )
            db.add(user)
            db.flush()

    _transfer_guest_sites(db, viewer.guest_session_id, user.id)
    sync_user_subscription_status(db, user)
    db.commit()
    db.refresh(user)
    set_auth_cookie(response, user)
    return _auth_response(db, user, guest_session_id=viewer.guest_session_id)


def _transfer_guest_sites(db: Session, guest_session_id: str | None, user_id: str) -> int:
    if not guest_session_id:
        return 0
    guest_sites = db.execute(
        select(Site).where(Site.user_id.is_(None), Site.guest_session_id == guest_session_id)
    ).scalars().all()
    for site in guest_sites:
        site.user_id = user_id
        site.guest_session_id = None
    return len(guest_sites)


def _auth_response(db: Session, user: User | None, guest_session_id: str | None = None) -> AuthResponse:
    return AuthResponse(authenticated=user is not None, user=_serialize_user(user, db=db), guest_session_id=guest_session_id)


def _require_authenticated_viewer(request: Request, db: Session, response: Response | None = None) -> User:
    viewer = build_viewer_context(request, db, response=response)
    if viewer.user is None:
        raise HTTPException(status_code=401, detail="Please sign up or log in to continue.")
    return viewer.user


def _require_manageable_site(
    db: Session,
    site_id: str,
    request: Request,
    response: Response | None = None,
    require_user: bool = False,
) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    viewer = build_viewer_context(request, db, response=response)
    if site.user_id:
        if viewer.user is None:
            if require_user:
                raise HTTPException(status_code=401, detail="Please sign up or log in to continue.")
            raise HTTPException(status_code=404, detail="Site not found")
        if site.user_id != viewer.user.id:
            raise HTTPException(status_code=404, detail="Site not found")
        return site

    if require_user:
        raise HTTPException(status_code=401, detail="Please sign up or log in to continue.")

    if site.guest_session_id and site.guest_session_id != viewer.guest_session_id:
        raise HTTPException(status_code=404, detail="Site not found")

    return site


def _schedule_process_site(site_id: str, site_url: str) -> None:
    existing = _bg_tasks.get(site_id)
    if existing is not None and not existing.done():
        return

    task = asyncio.create_task(process_site(site_id, site_url))
    _bg_tasks[site_id] = task

    def _cleanup(completed_task: asyncio.Task) -> None:
        current = _bg_tasks.get(site_id)
        if current is completed_task:
            _bg_tasks.pop(site_id, None)

    task.add_done_callback(_cleanup)


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

app = FastAPI(title="5minBot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/website", StaticFiles(directory=WEBSITE_DIR), name="website")


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

    with session_scope() as db:
        resumable_sites = db.execute(
            select(Site.id, Site.url).where(Site.status.in_(["pending", "crawling", "embedding"]))
        ).all()

    for site_id, site_url in resumable_sites:
        logger.info("Resuming background processing for site %s (%s)", site_id, site_url)
        _schedule_process_site(site_id, site_url)


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
                invalidate_cache(site_id)

                async def crawl_progress(payload: dict[str, int | str]) -> None:
                    with session_scope() as progress_db:
                        progress_site = progress_db.get(Site, site_id)
                        if progress_site is None:
                            return
                        progress_site.status = "crawling"
                        progress_site.page_count = max(progress_site.page_count or 0, int(payload.get("pages_crawled", 0)))
                        progress_site.updated_at = datetime.utcnow()

                pages = await crawl_site(
                    root_url,
                    site_id=site_id,
                    max_pages=MAX_CRAWL_PAGES,
                    max_depth=MAX_CRAWL_DEPTH,
                    progress_callback=crawl_progress,
                )
                if not pages:
                    raise ValueError("No content could be extracted")

                vector_chunks: list[dict[str, object]] = []
                site_name = None
                total_pages = 0
                total_chunks = 0
                seen_content_hashes: set[str] = set()

                with session_scope() as db:
                    site = db.get(Site, site_id)
                    if site is not None:
                        site.status = "extracting"
                        site.updated_at = datetime.utcnow()

                for page_result in pages:
                    extracted = await asyncio.to_thread(extract_content, page_result.html, page_result.url)
                    if not extracted.text.strip():
                        continue
                    if extracted.content_hash in seen_content_hashes:
                        logger.info("Skipping duplicate extracted content for %s", page_result.url)
                        continue
                    seen_content_hashes.add(extracted.content_hash)

                    page_title = extracted.title or page_result.title or page_result.url
                    page_url = page_result.url
                    try:
                        page_url = normalize_url(extracted.canonical_url or page_result.url)
                    except Exception:
                        page_url = page_result.url
                    if site_name is None:
                        site_name = page_title

                    page_id = str(uuid4())
                    page_chunks = await asyncio.to_thread(chunk_page, extracted, page_url, page_title)
                    if total_pages == 0:
                        overview_chunk = await asyncio.to_thread(
                            build_site_overview_chunk,
                            extracted,
                            page_url,
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
                                url=page_url,
                                title=page_title,
                                depth=page_result.depth,
                                word_count=extracted.word_count,
                                crawled_at=datetime.utcnow(),
                                http_status=page_result.http_status,
                                html_content=page_result.html,
                            )
                        )
                        db.flush()
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
                            page_url=page_url,
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


@app.get("/api/auth/me", response_model=AuthResponse)
async def auth_me(request: Request, response: Response, db: Session = Depends(get_db)):
    viewer = build_viewer_context(request, db, response=response)
    return _auth_response(db, viewer.user, guest_session_id=viewer.guest_session_id)


@app.get("/api/auth/providers", response_model=AuthProviderConfigResponse)
async def auth_providers():
    return _google_provider_config()


@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Email/password signup is disabled. Continue with Google instead.")


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    raise HTTPException(status_code=410, detail="Email/password login is disabled. Continue with Google instead.")


@app.post("/api/auth/google", response_model=AuthResponse)
async def auth_google(payload: GoogleAuthRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    google_profile = _verify_google_credential(payload.credential)
    return _complete_google_auth(db, request, response, google_profile)


@app.post("/api/auth/logout", response_model=LogoutResponse)
async def logout(response: Response):
    clear_auth_cookie(response)
    return LogoutResponse(ok=True)


@app.get("/api/billing/plans", response_model=BillingPlansResponse)
async def billing_plans(request: Request, db: Session = Depends(get_db)):
    viewer = build_viewer_context(request, db)
    return BillingPlansResponse(plans=_serialize_billing_plans(viewer.user))


@app.get("/api/billing/status", response_model=BillingStatusResponse)
async def billing_status(request: Request, response: Response, db: Session = Depends(get_db)):
    viewer = build_viewer_context(request, db, response=response)
    return BillingStatusResponse(
        authenticated=viewer.user is not None,
        user=_serialize_user(viewer.user, db=db),
        plans=_serialize_billing_plans(viewer.user),
        guest_session_id=viewer.guest_session_id,
    )


@app.post("/api/billing/checkout", response_model=BillingCheckoutResponse)
async def billing_checkout(payload: BillingCheckoutRequest, request: Request, db: Session = Depends(get_db)):
    user = _require_authenticated_viewer(request, db)
    try:
        checkout = await create_checkout_session(user, payload.plan.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BillingConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Dodo checkout creation failed with status %s", exc.response.status_code)
        detail = "Unable to start checkout right now."
        try:
            error_payload = exc.response.json()
            detail = error_payload.get("message") or error_payload.get("detail") or detail
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        logger.exception("Unexpected Dodo checkout error")
        raise HTTPException(status_code=500, detail="Unable to start checkout right now.") from exc

    return BillingCheckoutResponse(checkout_url=checkout["checkout_url"])


@app.post("/api/webhooks/dodo")
async def dodo_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = (await request.body()).decode("utf-8")
    headers = {
        "webhook-id": request.headers.get("webhook-id", ""),
        "webhook-signature": request.headers.get("webhook-signature", ""),
        "webhook-timestamp": request.headers.get("webhook-timestamp", ""),
    }
    try:
        payload = verify_webhook_payload(raw_body, headers)
    except BillingVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    webhook_id = headers["webhook-id"]
    try:
        result = process_webhook_event(db, webhook_id, payload)
    except Exception as exc:
        logger.exception("Failed to process Dodo webhook %s", webhook_id)
        raise HTTPException(status_code=500, detail="Webhook processing failed.") from exc

    return {"received": True, **result}


@app.post("/api/sites", response_model=CreateSiteResponse)
async def create_site(payload: CreateSiteRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        normalized_url = _normalize_site_input_url(str(payload.url))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid URL: {exc}") from exc

    viewer = build_viewer_context(request, db, response=response)
    site_id = str(uuid4())
    db.add(
        Site(
            id=site_id,
            user_id=viewer.user.id if viewer.user is not None else None,
            guest_session_id=None if viewer.user is not None else viewer.guest_session_id,
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
    _schedule_process_site(site_id, normalized_url)
    return CreateSiteResponse(site_id=site_id, status="pending")


@app.get("/api/sites", response_model=SiteListResponse)
async def list_sites(request: Request, response: Response, db: Session = Depends(get_db)):
    viewer = build_viewer_context(request, db, response=response)
    query = select(Site).order_by(Site.created_at.desc())
    if viewer.user is not None:
        query = query.where(Site.user_id == viewer.user.id)
    else:
        query = query.where(Site.user_id.is_(None), Site.guest_session_id == viewer.guest_session_id)
    sites = db.execute(query).scalars().all()
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


@app.get("/api/public/sites/{site_id}/status", response_model=SiteStatusResponse)
async def public_site_status(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return _serialize_status(site)


@app.get("/api/public/sites/{site_id}/theme")
async def public_site_theme(site_id: str, db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return {
        "site_id": site.id,
        "name": site.name,
        "theme": _resolve_site_theme(db, site_id),
    }


@app.get("/api/sites/{site_id}/status", response_model=SiteStatusResponse)
async def site_status(site_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    site = _require_manageable_site(db, site_id, request, response=response)
    return _serialize_status(site)


@app.post("/api/sites/{site_id}/reprocess-ui")
async def reprocess_ui(site_id: str, request: Request, db: Session = Depends(get_db)):
    site = _require_manageable_site(db, site_id, request)

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
async def retry_site(site_id: str, request: Request, db: Session = Depends(get_db)):
    site = _require_manageable_site(db, site_id, request)

    db.execute(delete(Chunk).where(Chunk.site_id == site_id))
    db.execute(delete(Page).where(Page.site_id == site_id))
    invalidate_cache(site_id)
    site.status = "pending"
    site.page_count = 0
    site.chunk_count = 0
    site.name = None
    site.error_msg = None
    site.updated_at = datetime.utcnow()
    db.commit()

    _schedule_process_site(site_id, site.url)
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
    site = _require_manageable_site(db, site_id, request, require_user=True)
    base = BASE_URL or str(request.base_url).rstrip("/")
    return EmbedScriptResponse(script_tag=f"<script src='{base}/widget/agent.js' data-site-id='{site_id}'></script>")


@app.get("/api/chat")
async def chat(site_id: str = Query(...), q: str = Query(...), session_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        entitlement = evaluate_site_entitlement(db, site)
        if not entitlement.allowed:
            yield f"data: {json.dumps({'type': 'trial_ended', 'message': entitlement.message or TRIAL_ENDED_MESSAGE})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        greeting_reply = _simple_conversational_reply(q)
        if greeting_reply is not None:
            append_turn(site_id, session_id, "user", q)
            append_turn(site_id, session_id, "assistant", greeting_reply)
            yield f"data: {json.dumps({'type': 'token', 'content': greeting_reply})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        history = get_history(site_id, session_id)
        effective_query = build_contextual_query(q, history)
        chunks, intent = await asyncio.to_thread(retrieve, site_id, effective_query)
        fallback_text = FALLBACK_MESSAGE.format(site_name=site.name or site.url)
        if not chunks:
            append_turn(site_id, session_id, "user", q)
            append_turn(site_id, session_id, "assistant", fallback_text)
            yield f"data: {json.dumps({'type': 'no_answer', 'message': fallback_text})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        chunk_rows = db.execute(
            select(Chunk).where(Chunk.site_id == site_id, Chunk.id.in_(chunk_ids))
        ).scalars().all()
        positions_by_chunk_id = {chunk_row.id: chunk_row.position for chunk_row in chunk_rows}
        valid_chunk_ids = set(positions_by_chunk_id)
        if len(valid_chunk_ids) != len(chunk_ids):
            dropped = len(chunk_ids) - len(valid_chunk_ids)
            logger.warning(
                "Discarded %s retrieved chunks for site %s because they did not match the requested site",
                dropped,
                site_id,
            )
            chunks = [chunk for chunk in chunks if chunk.chunk_id in valid_chunk_ids]

        if not chunks:
            append_turn(site_id, session_id, "user", q)
            append_turn(site_id, session_id, "assistant", fallback_text)
            yield f"data: {json.dumps({'type': 'no_answer', 'message': fallback_text})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

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


def _website_file(path: str) -> FileResponse:
    return FileResponse(WEBSITE_DIR / path, media_type="text/html")


@app.get("/")
async def root():
    return _website_file("index.html")


@app.get("/features")
async def website_features():
    return _website_file("features.html")


@app.get("/pricing")
async def website_pricing():
    return _website_file("pricing.html")


@app.get("/how-it-works")
async def website_how_it_works():
    return _website_file("how-it-works.html")


@app.get("/demo")
async def website_demo():
    return _website_file("demo.html")


@app.get("/blog")
async def website_blog():
    return _website_file("blog.html")


@app.get("/blog/ai-salesman")
async def blog_ai_salesman():
    return _website_file("blog-ai-salesman.html")


@app.get("/blog/visitor-questions")
async def blog_visitor_questions():
    return _website_file("blog-visitor-questions.html")


@app.get("/blog/ui-layout-ai")
async def blog_ui_layout_ai():
    return _website_file("blog-ui-layout-ai.html")


@app.get("/privacy")
async def website_privacy():
    return _website_file("privacy.html")


@app.get("/terms")
async def website_terms():
    return _website_file("terms.html")


@app.get("/security")
async def website_security():
    return _website_file("security.html")


@app.get("/support")
async def website_support():
    return _website_file("support.html")


@app.get("/contact")
async def website_contact():
    return RedirectResponse(url="/support", status_code=307)


@app.get("/billing/success")
async def billing_success(
    plan: str | None = Query(default=None),
    subscription_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    query = {"billing": "success"}
    if plan:
        query["plan"] = plan
    if subscription_id:
        query["subscription_id"] = subscription_id
    if status:
        query["status"] = status
    return RedirectResponse(url=f"/dashboard?{urlencode(query)}", status_code=302)


@app.get("/dashboard")
async def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")
