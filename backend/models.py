from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    trial_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    subscription_status: Mapped[str | None] = mapped_column(Text, nullable=True, default="trial")
    subscription_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sites_limit: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"), nullable=True, index=True)
    guest_session_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    site_id: Mapped[str | None] = mapped_column(Text, ForeignKey("sites.id"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    site_id: Mapped[str | None] = mapped_column(Text, ForeignKey("sites.id"))
    page_id: Mapped[str | None] = mapped_column(Text, ForeignKey("pages.id"))
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
