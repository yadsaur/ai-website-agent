from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATA_DIR, DATABASE_URL, DB_PATH, VECTORS_DIR


class Base(DeclarativeBase):
    pass


def _build_engine():
    database_url = DATABASE_URL or os.environ.get("DATABASE_URL", "")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            future=True,
            connect_args={"sslmode": "require"},
        )

    return create_engine(
        f"sqlite:///{DB_PATH}",
        future=True,
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)


def init_db() -> None:
    from pathlib import Path
    from sqlalchemy import text

    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(VECTORS_DIR).mkdir(parents=True, exist_ok=True)
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
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
        else:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS site_vectors (
                        id TEXT PRIMARY KEY,
                        site_id TEXT,
                        chunk_id TEXT,
                        page_url TEXT,
                        page_title TEXT,
                        section TEXT,
                        position INTEGER,
                        text TEXT,
                        token_count INTEGER,
                        embedding TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
