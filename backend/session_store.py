from __future__ import annotations

import time
from dataclasses import dataclass, field

from backend.config import SESSION_MAX_TURNS, SESSION_TTL_SECONDS


@dataclass
class SessionState:
    site_id: str
    session_id: str
    turns: list[dict[str, str]] = field(default_factory=list)
    last_accessed: float = field(default_factory=time.time)


_sessions: dict[tuple[str, str], SessionState] = {}


def _evict_expired() -> None:
    now = time.time()
    expired = [key for key, value in _sessions.items() if now - value.last_accessed > SESSION_TTL_SECONDS]
    for key in expired:
        _sessions.pop(key, None)


def get_history(site_id: str, session_id: str | None) -> list[dict[str, str]]:
    _evict_expired()
    if not session_id:
        return []
    key = (site_id, session_id)
    session = _sessions.get(key)
    if not session:
        return []
    session.last_accessed = time.time()
    return list(session.turns)


def append_turn(site_id: str, session_id: str | None, role: str, content: str) -> None:
    if not session_id or not content.strip():
        return
    _evict_expired()
    key = (site_id, session_id)
    session = _sessions.get(key)
    if session is None:
        session = SessionState(site_id=site_id, session_id=session_id)
        _sessions[key] = session
    session.turns.append({"role": role, "content": content.strip()})
    session.turns = session.turns[-SESSION_MAX_TURNS:]
    session.last_accessed = time.time()


def build_contextual_query(query: str, history: list[dict[str, str]]) -> str:
    if not history:
        return query

    normalized = query.lower().strip()
    referential_terms = (
        "this",
        "that",
        "it",
        "they",
        "those",
        "these",
        "he",
        "she",
        "them",
        "there",
        "here",
        "top left",
        "top right",
        "left or right",
        "where",
    )
    should_expand = len(normalized.split()) <= 10 or any(term in normalized for term in referential_terms)
    if not should_expand:
        return query

    recent = history[-4:]
    history_lines = [f"{turn['role']}: {turn['content']}" for turn in recent]
    return f"{query}\n\nConversation context:\n" + "\n".join(history_lines)
