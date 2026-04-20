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


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str


class UserSummary(BaseModel):
    id: str
    email: str
    subscription_id: str | None = None
    subscription_status: str
    subscription_plan: str | None
    trial_start_at: str | None
    trial_ends_at: str | None
    current_period_end: str | None = None
    days_remaining: int | None
    sites_limit: int | None


class AuthResponse(BaseModel):
    authenticated: bool
    user: UserSummary | None
    guest_session_id: str | None = None


class LogoutResponse(BaseModel):
    ok: bool


class AuthProviderConfigResponse(BaseModel):
    google_enabled: bool
    google_client_id: str | None = None


class BillingPlanSummary(BaseModel):
    key: str
    label: str
    sites_limit: int
    usage_limit: int | None = None
    checkout_enabled: bool
    current: bool = False


class BillingPlansResponse(BaseModel):
    plans: list[BillingPlanSummary]


class BillingCheckoutRequest(BaseModel):
    plan: str


class BillingCheckoutResponse(BaseModel):
    checkout_url: str


class BillingStatusResponse(BaseModel):
    authenticated: bool
    user: UserSummary | None
    plans: list[BillingPlanSummary]
    guest_session_id: str | None = None
