from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import numpy as np

from backend.config import (
    RETRIEVAL_MMR_LAMBDA,
    RETRIEVAL_SCORE_THRESHOLD,
    RETRIEVAL_TOP_K,
    UI_CHUNK_SECTION_LABEL,
    UI_SCORE_BONUS,
    UI_SCORE_THRESHOLD,
)
from backend.embedder import get_embedder
from backend.vector_store import load_vector_store

logger = logging.getLogger(__name__)

INTENT_PATTERNS = {
    "pricing": [
        "cost", "price", "pricing", "plan", "plans", "how much", "fee", "fees",
        "charge", "charges", "billing", "billed", "subscription", "pay",
        "payment", "refund", "cancel", "discount", "cheaper", "affordable",
        "free trial", "free plan", "lifetime", "annual", "monthly", "tier",
        "upgrade", "downgrade", "enterprise plan", "hidden fee", "worth",
        "billing", "billed", "bill", "invoice", "invoicing", "invoiced",
        "payment method", "how do i pay", "how does payment", "how does billing",
        "subscription", "subscriptions", "renewal", "renew", "auto-renew",
        "charge", "charged", "charges", "credit card", "debit card", "paypal",
        "stripe", "receipt", "receipts", "overage", "overages", "exceed",
        "what happens if", "usage", "per month", "per year", "per user",
        "seat", "seats", "pay for", "cost me", "costs me", "will i be charged",
        "when am i charged", "how am i charged", "payment cycle", "pay annually",
        "pay monthly", "switch to annual", "switch to monthly", "included",
        "what's included", "payment method",
    ],
    "trust": [
        "review", "reviews", "testimonial", "testimonials", "customers",
        "case study", "case studies", "who uses", "clients", "ratings",
        "rating", "trust", "trusted", "legitimate", "legit", "real company",
        "how long", "founded", "award", "press", "coverage", "community",
        "uptime", "reliability", "status", "limitations",
    ],
    "security": [
        "secure", "security", "safe", "safety", "gdpr", "privacy", "encrypt",
        "encryption", "data", "store", "stored", "delete", "soc 2", "iso",
        "compliance", "compliant", "dpa", "two-factor", "2fa", "export",
        "third party", "sell data",
    ],
    "integrations": [
        "integrate", "integration", "integrations", "api", "zapier", "make",
        "import", "export", "browser", "chrome", "extension", "plugin",
        "sso", "single sign", "webhook", "webhooks", "white label",
        "whitelabel", "embed", "compatible", "works with", "connect",
    ],
    "support": [
        "support", "help", "stuck", "issue", "problem", "contact", "live chat",
        "phone", "email", "hours", "documentation", "docs", "knowledge base",
        "onboarding", "training", "video", "tutorial", "account manager",
        "response time", "bug", "report", "forum", "slack",
    ],
    "getting_started": [
        "sign up", "signup", "get started", "start", "begin", "how to start",
        "create account", "register", "credit card", "no credit card",
        "trial", "after trial", "switch plan", "demo", "schedule demo",
        "quote", "promo", "coupon", "code", "referral", "affiliate",
        "minimum contract", "day one", "what do i get", "where do i click",
        "buy now", "purchase",
    ],
    "product": [
        "what is", "what does", "how does", "who is it for", "who is this for",
        "who is this made for", "made for", "features",
        "feature", "difference", "different from", "better than", "competitor",
        "vs ", "versus", "mobile app", "offline", "language", "languages",
        "demo", "show me", "example", "use case", "work for",
    ],
}

PRICING_URL_KEYWORDS = [
    "pricing", "plans", "price", "billing", "payment", "payments",
    "subscription", "subscriptions", "checkout", "upgrade", "buy",
    "purchase", "invoice", "cost", "fees",
]

PRICING_TITLE_KEYWORDS = [
    "pricing", "plans", "price", "cost", "billing", "payment",
    "subscription", "fees", "how it works", "what's included",
    "features", "compare plans", "upgrade",
]

PRICING_SECTION_KEYWORDS = [
    "pricing", "plan", "cost", "fee", "billing", "payment",
    "subscription", "what's included", "includes", "features",
]

QUERY_EXPANSION_MAP = {
    "billing": "billing payment pricing cost plans how much",
    "how does billing work": "billing payment pricing plans cost per month",
    "how does payment work": "payment billing pricing cost plans",
    "how do i pay": "payment billing pricing cost how to pay",
    "how am i charged": "billing charges pricing cost payment",
    "how am i billed": "billing charges pricing cost payment",
    "when am i charged": "billing cycle payment pricing subscription",
    "invoice": "invoice billing payment receipt pricing",
    "is there an invoice": "invoice billing payment receipt pricing",
    "subscription": "subscription billing pricing plans monthly annual",
    "renewal": "renewal billing subscription pricing annual monthly",
    "will i be charged": "charges billing pricing cost payment",
    "what's the payment method": "payment method billing pricing stripe paypal card",
    "is this legit": "company about us team founded customers trust",
    "is this real": "company about us team founded legitimate trust",
    "can i trust": "trust security reviews testimonials customers",
    "how do i begin": "get started sign up register free trial",
    "where do i start": "get started sign up register free trial",
    "how to get started": "get started sign up register onboarding",
    "i need help": "support contact help desk customer service",
    "who do i contact": "contact support help team email",
}

INTENT_EXPANSION_SUFFIXES = {
    "pricing": "pricing cost plans price how much billing payment",
    "trust": "about company customers reviews testimonials trust",
    "security": "security privacy data compliance gdpr safe",
    "integrations": "integrations api connect apps tools",
    "support": "support help contact customer service",
    "getting_started": "get started sign up free trial register",
    "product": "features what is how does work",
}

UI_POSITION_KEYWORDS = [
    "where",
    "where is",
    "where can i find",
    "where do i",
    "how to find",
    "how do i find",
    "how to access",
    "how do i access",
    "location of",
    "find the",
    "navigate to",
    "how to navigate",
    "where is the",
    "where are the",
    "where to click",
    "which menu",
    "which tab",
    "which section",
    "which page",
    "top",
    "bottom",
    "left",
    "right",
    "corner",
    "sidebar",
    "header",
    "footer",
    "navigation",
    "nav bar",
    "menu",
    "button",
    "link",
    "icon",
    "search bar",
    "search box",
]


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page_url: str
    page_title: str
    section: str
    score: float


def classify_query_intent(query: str) -> str:
    try:
        normalized = query.lower()
        scores = {category: 0 for category in INTENT_PATTERNS}
        for category, keywords in INTENT_PATTERNS.items():
            for keyword in keywords:
                if keyword in normalized:
                    scores[category] += 1
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"
    except Exception:
        return "general"


def _is_site_overview_query(query: str) -> bool:
    normalized = query.lower().strip()
    about_terms = ("about", "what is", "who are", "overview", "summary", "purpose", "mission", "do you do")
    referential_terms = ("this site", "this website", "the site", "the website", "here", "homepage", "home page")
    return any(term in normalized for term in about_terms) and any(term in normalized for term in referential_terms)


def _is_search_query(query: str) -> bool:
    normalized = query.lower().strip()
    return "search" in normalized or "find" in normalized or "look for" in normalized


def is_ui_position_query(query: str) -> bool:
    normalized = query.lower()
    return any(keyword in normalized for keyword in UI_POSITION_KEYWORDS)


def _expand_query(query: str) -> str:
    intent = classify_query_intent(query)
    if is_ui_position_query(query):
        return (
            f"{query}\n\n"
            "ui layout navigation position location header footer sidebar top navigation search bar "
            "button link menu page structure where to click"
        )
    if intent == "pricing":
        return (
            f"{query}\n\n"
            "pricing plans plan comparison tiers monthly annual free trial billing cost price"
        )
    if intent == "trust":
        return (
            f"{query}\n\n"
            "about company customers testimonials reviews case studies founded press awards trust reliability status"
        )
    if intent == "security":
        return (
            f"{query}\n\n"
            "security privacy compliance gdpr data protection encryption soc 2 iso dpa trust center"
        )
    if intent == "integrations":
        return (
            f"{query}\n\n"
            "integrations api developers apps connect sso webhook import export compatibility"
        )
    if intent == "getting_started":
        return (
            f"{query}\n\n"
            "sign up register get started start free trial demo contact sales where do i click"
        )
    if intent == "support":
        return (
            f"{query}\n\n"
            "support help onboarding docs documentation contact response time training tutorials"
        )
    if intent == "product":
        return (
            f"{query}\n\n"
            "what this product does who it is for use case features benefits audience get started"
        )
    if _is_site_overview_query(query):
        return (
            f"{query}\n\n"
            "site overview homepage about this website mission purpose what this site offers "
            "publication organization company summary"
        )
    if _is_search_query(query):
        return (
            f"{query}\n\n"
            "search find essay article topic support help navigation discover content browse latest"
        )
    return query


def expand_query(query: str) -> str:
    """
    Expands semantically thin queries into richer versions for better
    embedding similarity against chunk content.

    Strategy: exact match first, then keyword match, then intent-aware suffix.
    """
    q_lower = query.lower().strip()

    if is_ui_position_query(query) or _is_site_overview_query(query) or _is_search_query(query):
        return _expand_query(query)

    if q_lower in QUERY_EXPANSION_MAP:
        return f"{query} {QUERY_EXPANSION_MAP[q_lower]}".strip()

    best_match = None
    best_match_len = 0
    for key, expansion in QUERY_EXPANSION_MAP.items():
        if key in q_lower and len(key) > best_match_len:
            best_match = expansion
            best_match_len = len(key)

    if best_match:
        return f"{query} {best_match}".strip()

    intent = classify_query_intent(query)
    suffix = INTENT_EXPANSION_SUFFIXES.get(intent, "")
    if suffix:
        return f"{_expand_query(query)} {suffix}".strip()

    return query


def _score_bonus(chunk: dict, is_overview_query: bool) -> float:
    bonus = 0.0
    section = str(chunk.get("section", "")).lower()
    page_title = str(chunk.get("page_title", "")).lower()
    path = urlparse(str(chunk.get("page_url", ""))).path or "/"
    if is_overview_query:
        if "site overview" in section:
            bonus += 0.25
        if path in {"", "/"}:
            bonus += 0.12
        if "about" in section or "about" in page_title:
            bonus += 0.08
    return bonus


def _ui_query_bonus(query: str, chunk: dict) -> float:
    bonus = 0.0
    text = str(chunk.get("text", "")).lower()
    page_title = str(chunk.get("page_title", "")).lower()
    path = (urlparse(str(chunk.get("page_url", ""))).path or "/").lower()
    normalized_query = query.lower()

    if str(chunk.get("section", "")) == UI_CHUNK_SECTION_LABEL:
        bonus += UI_SCORE_BONUS
        if path in {"", "/"}:
            bonus += 0.18
        if "429:" in page_title or "too many requests" in text:
            bonus -= 0.35
        if "support" in page_title:
            bonus -= 0.08
        if ("search" in normalized_query) and ("search bar" in text or "search form" in text):
            bonus += 0.2
        if ("essay" in normalized_query or "essays" in normalized_query) and '"essays" link' in text:
            bonus += 0.2
        if "logo" in normalized_query and "site logo" in text:
            bonus += 0.22
        if "footer" in normalized_query and "footer at the bottom" in text:
            bonus += 0.2
        if ("navigation" in normalized_query or "menu" in normalized_query or "links" in normalized_query) and "navigation links" in text:
            bonus += 0.2
        if any(term in normalized_query for term in ["sign up", "signup", "subscribe", "join", "register"]) and any(
            term in text for term in ['button is located', 'subscribe', 'newsletter', 'sign up', 'join', 'register']
        ):
            bonus += 0.16
    return bonus


def _minimum_score_threshold(query: str, intent: str) -> float:
    if is_ui_position_query(query):
        return UI_SCORE_THRESHOLD
    if intent in ("pricing", "getting_started"):
        return 0.25
    if _is_search_query(query):
        return UI_SCORE_THRESHOLD
    return RETRIEVAL_SCORE_THRESHOLD


def retrieve(site_id: str, query: str, top_k: int = RETRIEVAL_TOP_K) -> tuple[list[RetrievedChunk], str]:
    store = load_vector_store(site_id)
    intent = classify_query_intent(query)
    if store is None or store.embeddings.size == 0:
        return [], intent

    is_overview_query = _is_site_overview_query(query)
    is_search = _is_search_query(query)
    is_ui_query = is_ui_position_query(query)
    score_threshold = _minimum_score_threshold(query, intent)
    logger.info("Retrieval query classification for '%s': overview=%s search=%s ui=%s threshold=%.2f", query, is_overview_query, is_search, is_ui_query, score_threshold)
    expanded_query = expand_query(query)
    query_vec = get_embedder().embed_query(expanded_query)
    scores = np.dot(store.embeddings, query_vec)
    if is_overview_query:
        scores = scores + np.asarray([_score_bonus(chunk, True) for chunk in store.chunks], dtype=np.float32)
    if is_search:
        scores = scores + np.asarray(
            [
                0.14 if any(term in f"{chunk.get('page_title', '')} {chunk.get('section', '')}".lower() for term in ("support", "search", "find", "about"))
                else 0.0
                for chunk in store.chunks
            ],
            dtype=np.float32,
        )
    if is_ui_query:
        scores = scores + np.asarray(
            [
                _ui_query_bonus(query, chunk)
                for chunk in store.chunks
            ],
            dtype=np.float32,
        )
    candidate_count = min(20, len(scores))
    if candidate_count == 0:
        return [], intent

    candidate_indices = np.argsort(scores)[-candidate_count:][::-1]
    logger.info(
        "Top retrieval candidates for '%s': %s",
        query,
        [
            {
                "section": store.chunks[int(index)].get("section"),
                "title": store.chunks[int(index)].get("page_title"),
                "score": round(float(scores[int(index)]), 4),
            }
            for index in candidate_indices[:5]
        ],
    )
    selected_positions: list[int] = []

    while len(selected_positions) < min(top_k, candidate_count):
        best_position = None
        best_score = None
        for position, original_index in enumerate(candidate_indices):
            if position in selected_positions:
                continue
            relevance = float(scores[original_index])
            if not selected_positions:
                mmr_score = relevance
            else:
                candidate_vec = store.embeddings[original_index]
                selected_vecs = store.embeddings[candidate_indices[selected_positions]]
                diversity_penalty = float(np.max(np.dot(selected_vecs, candidate_vec)))
                mmr_score = RETRIEVAL_MMR_LAMBDA * relevance - (1 - RETRIEVAL_MMR_LAMBDA) * diversity_penalty
            if best_score is None or mmr_score > best_score:
                best_score = mmr_score
                best_position = position
        if best_position is None:
            break
        selected_positions.append(best_position)

    mmr_results: list[RetrievedChunk] = []
    for position in selected_positions:
        original_index = int(candidate_indices[position])
        score = float(scores[original_index])
        chunk = store.chunks[original_index]
        mmr_results.append(
            RetrievedChunk(
                chunk_id=chunk["chunk_id"],
                text=chunk["text"],
                page_url=chunk["page_url"],
                page_title=chunk["page_title"],
                section=chunk["section"],
                score=score,
            )
        )

    if intent == "pricing":
        for chunk in mmr_results:
            url_lower = (chunk.page_url or "").lower()
            title_lower = (chunk.page_title or "").lower()
            section_lower = (chunk.section or "").lower()
            if any(keyword in url_lower for keyword in PRICING_URL_KEYWORDS):
                chunk.score = min(1.0, chunk.score + 0.20)
            if any(keyword in title_lower for keyword in PRICING_TITLE_KEYWORDS):
                chunk.score = min(1.0, chunk.score + 0.15)
            if any(keyword in section_lower for keyword in PRICING_SECTION_KEYWORDS):
                chunk.score = min(1.0, chunk.score + 0.10)
    elif intent == "trust":
        for chunk in mmr_results:
            url_lower = (chunk.page_url or "").lower()
            title_lower = (chunk.page_title or "").lower()
            if any(
                keyword in url_lower
                for keyword in ["about", "customers", "case-study", "testimonial", "review", "press", "security", "trust"]
            ):
                chunk.score = min(1.0, chunk.score + 0.18)
            if any(
                keyword in title_lower
                for keyword in ["about", "customer", "story", "testimonial", "review", "trusted", "security", "compliance"]
            ):
                chunk.score = min(1.0, chunk.score + 0.12)
    elif intent == "security":
        for chunk in mmr_results:
            url_lower = (chunk.page_url or "").lower()
            title_lower = (chunk.page_title or "").lower()
            if any(keyword in url_lower for keyword in ["security", "privacy", "compliance", "gdpr", "legal", "trust"]):
                chunk.score = min(1.0, chunk.score + 0.20)
            if any(keyword in title_lower for keyword in ["security", "privacy", "compliance", "gdpr"]):
                chunk.score = min(1.0, chunk.score + 0.15)
    elif intent == "integrations":
        for chunk in mmr_results:
            url_lower = (chunk.page_url or "").lower()
            title_lower = (chunk.page_title or "").lower()
            if any(keyword in url_lower for keyword in ["integrations", "api", "developers", "connect", "apps"]):
                chunk.score = min(1.0, chunk.score + 0.20)
            if any(keyword in title_lower for keyword in ["integrations", "api", "developers", "connect", "apps"]):
                chunk.score = min(1.0, chunk.score + 0.10)
    elif intent == "getting_started":
        for chunk in mmr_results:
            url_lower = (chunk.page_url or "").lower()
            section_lower = (chunk.section or "").lower()
            if any(keyword in url_lower for keyword in ["signup", "sign-up", "register", "get-started", "trial", "start"]):
                chunk.score = min(1.0, chunk.score + 0.20)
            if "site overview" in section_lower:
                chunk.score = min(1.0, chunk.score + 0.08)

    mmr_results.sort(key=lambda item: item.score, reverse=True)
    results = [chunk for chunk in mmr_results if chunk.score >= score_threshold]
    return results, intent
