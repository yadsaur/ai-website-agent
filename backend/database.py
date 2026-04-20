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
    from sqlalchemy import inspect, text

    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(VECTORS_DIR).mkdir(parents=True, exist_ok=True)
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        inspector = inspect(connection)

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

        site_columns = {column["name"] for column in inspector.get_columns("sites")}
        if "user_id" not in site_columns:
            connection.execute(text("ALTER TABLE sites ADD COLUMN user_id TEXT"))
        if "guest_session_id" not in site_columns:
            connection.execute(text("ALTER TABLE sites ADD COLUMN guest_session_id TEXT"))

        page_columns = {column["name"] for column in inspector.get_columns("pages")}
        if "html_content" not in page_columns:
            connection.execute(text("ALTER TABLE pages ADD COLUMN html_content TEXT"))

        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "google_sub" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN google_sub TEXT"))
        if "subscription_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN subscription_id TEXT"))
        if "current_period_end" not in user_columns:
            if engine.dialect.name == "postgresql":
                connection.execute(text("ALTER TABLE users ADD COLUMN current_period_end TIMESTAMPTZ"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN current_period_end TIMESTAMP"))

        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_sites_user_id ON sites (user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_sites_guest_session_id ON sites (guest_session_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub) WHERE google_sub IS NOT NULL"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_subscription_id ON users (subscription_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_processed_at ON billing_webhook_events (processed_at)"))
        else:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_sites_user_id ON sites (user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_sites_guest_session_id ON sites (guest_session_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_subscription_id ON users (subscription_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_billing_webhook_events_processed_at ON billing_webhook_events (processed_at)"))


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
