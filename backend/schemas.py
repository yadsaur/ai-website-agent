from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, HttpUrl


class CreateSiteRequest(BaseModel):
    url: HttpUrl


class CreateSiteResponse(BaseModel):
    site_id: str
    status: Literal["pending", "crawling", "embedding", "ready", "error"]


class SiteStatusResponse(BaseModel):
    site_id: str
    status: str
    page_count: int
    chunk_count: int
    name: str | None
    error_msg: str | None


class EmbedScriptResponse(BaseModel):
    script_tag: str


class SiteSummary(BaseModel):
    site_id: str
    url: str
    name: str | None
    status: str
    page_count: int
    chunk_count: int
    error_msg: str | None


class SiteListResponse(BaseModel):
    sites: list[SiteSummary]
