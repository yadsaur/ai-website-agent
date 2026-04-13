from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.config import DATABASE_URL, EMBEDDING_MODEL, VECTOR_CACHE_TTL_SECONDS, VECTORS_DIR


@dataclass
class LoadedVectorStore:
    model: str
    dimension: int
    created_at: str
    chunks: list[dict[str, Any]]
    embeddings: np.ndarray
    last_accessed: float


_vector_cache: dict[str, LoadedVectorStore] = {}


def _use_postgres() -> bool:
    return bool(DATABASE_URL)


def _postgres_engine():
    database_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"sslmode": "require"},
        future=True,
    )


_pg_engine = _postgres_engine() if _use_postgres() else None
_Session = sessionmaker(bind=_pg_engine, future=True) if _pg_engine is not None else None


def _vector_path(site_id: str) -> Path:
    return Path(VECTORS_DIR) / f"{site_id}.json"


def _ensure_site_vectors_table() -> None:
    if not _use_postgres() or _pg_engine is None:
        return
    with _pg_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS site_vectors (
                    id TEXT PRIMARY KEY,
                    site_id TEXT REFERENCES sites(id) ON DELETE CASCADE,
                    chunk_id TEXT,
                    page_url TEXT,
                    page_title TEXT,
                    section TEXT,
                    position INTEGER,
                    text TEXT,
                    token_count INTEGER,
                    embedding JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_site_vectors_site_id ON site_vectors(site_id)"))


async def write_vector_store(site_id: str, chunks: list[dict[str, Any]], embeddings: np.ndarray) -> None:
    if _use_postgres():
        await asyncio.to_thread(_write_vector_store_postgres, site_id, chunks, embeddings)
        _vector_cache.pop(site_id, None)
        return

    Path(VECTORS_DIR).mkdir(parents=True, exist_ok=True)
    payload = {
        "model": EMBEDDING_MODEL,
        "dimension": int(embeddings.shape[1]) if len(embeddings.shape) == 2 and embeddings.size else 384,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunks": [],
    }
    for chunk, embedding in zip(chunks, embeddings):
        payload["chunks"].append(
            {
                "chunk_id": chunk["chunk_id"],
                "page_url": chunk["page_url"],
                "page_title": chunk["page_title"],
                "section": chunk["section"],
                "position": chunk["position"],
                "text": chunk["text"],
                "token_count": chunk["token_count"],
                "embedding": np.asarray(embedding, dtype=np.float32).tolist(),
            }
        )

    async with aiofiles.open(_vector_path(site_id), "w", encoding="utf-8") as file:
        await file.write(json.dumps(payload, ensure_ascii=False))
    _vector_cache.pop(site_id, None)


def _write_vector_store_postgres(site_id: str, chunks: list[dict[str, Any]], embeddings: np.ndarray) -> None:
    if _Session is None:
        return
    _ensure_site_vectors_table()
    with _Session() as db:
        db.execute(text("DELETE FROM site_vectors WHERE site_id = :sid"), {"sid": site_id})
        for chunk, embedding in zip(chunks, embeddings):
            db.execute(
                text(
                    """
                    INSERT INTO site_vectors
                        (id, site_id, chunk_id, page_url, page_title, section, position, text, token_count, embedding)
                    VALUES
                        (:id, :site_id, :chunk_id, :page_url, :page_title, :section, :position, :text, :token_count, CAST(:embedding AS JSONB))
                    """
                ),
                {
                    "id": chunk["chunk_id"],
                    "site_id": site_id,
                    "chunk_id": chunk["chunk_id"],
                    "page_url": chunk["page_url"],
                    "page_title": chunk["page_title"],
                    "section": chunk["section"],
                    "position": chunk["position"],
                    "text": chunk["text"],
                    "token_count": chunk["token_count"],
                    "embedding": json.dumps(np.asarray(embedding, dtype=np.float32).tolist()),
                },
            )
        db.commit()


def load_vector_store(site_id: str) -> LoadedVectorStore | None:
    evict_expired_cache()
    now = datetime.now(timezone.utc).timestamp()
    cached = _vector_cache.get(site_id)
    if cached is not None:
        cached.last_accessed = now
        return cached

    if _use_postgres():
        store = _load_vector_store_postgres(site_id, now)
        if store is not None:
            _vector_cache[site_id] = store
        return store

    path = _vector_path(site_id)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    chunks = payload.get("chunks", [])
    embeddings = np.asarray([chunk["embedding"] for chunk in chunks], dtype=np.float32) if chunks else np.empty((0, 384), dtype=np.float32)
    store = LoadedVectorStore(
        model=payload.get("model", EMBEDDING_MODEL),
        dimension=int(payload.get("dimension", 384)),
        created_at=payload.get("created_at", ""),
        chunks=chunks,
        embeddings=embeddings,
        last_accessed=now,
    )
    _vector_cache[site_id] = store
    return store


def _load_vector_store_postgres(site_id: str, now: float) -> LoadedVectorStore | None:
    if _Session is None:
        return None
    _ensure_site_vectors_table()
    with _Session() as db:
        rows = db.execute(
            text(
                """
                SELECT chunk_id, page_url, page_title, section, position, text, token_count, embedding, created_at
                FROM site_vectors
                WHERE site_id = :sid
                ORDER BY created_at ASC
                """
            ),
            {"sid": site_id},
        ).fetchall()
    if not rows:
        return None

    chunks: list[dict[str, Any]] = []
    embeddings: list[np.ndarray] = []
    created_at = ""
    for row in rows:
        embedding = row.embedding
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        if created_at == "" and getattr(row, "created_at", None) is not None:
            created_at = row.created_at.isoformat()
        chunks.append(
            {
                "chunk_id": row.chunk_id,
                "page_url": row.page_url,
                "page_title": row.page_title,
                "section": row.section,
                "position": row.position,
                "text": row.text,
                "token_count": row.token_count,
                "embedding": embedding,
            }
        )
        embeddings.append(np.asarray(embedding, dtype=np.float32))

    matrix = np.stack(embeddings) if embeddings else np.empty((0, 384), dtype=np.float32)
    return LoadedVectorStore(
        model=EMBEDDING_MODEL,
        dimension=int(matrix.shape[1]) if matrix.size else 384,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        chunks=chunks,
        embeddings=matrix,
        last_accessed=now,
    )


def evict_expired_cache() -> None:
    now = datetime.now(timezone.utc).timestamp()
    expired = [site_id for site_id, store in _vector_cache.items() if now - store.last_accessed > VECTOR_CACHE_TTL_SECONDS]
    for site_id in expired:
        _vector_cache.pop(site_id, None)


def invalidate_cache(site_id: str) -> None:
    _vector_cache.pop(site_id, None)
