from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from standardwebhooks.webhooks import Webhook, WebhookVerificationError

from backend.config import (
    BILLING_PLAN_CONFIG,
    BILLING_PLAN_ORDER,
    DODO_CANCEL_URL,
    DODO_PAYMENTS_API_KEY,
    DODO_PAYMENTS_BASE_URL,
    DODO_PAYMENTS_WEBHOOK_KEY,
    DODO_SUCCESS_URL,
)
from backend.models import BillingWebhookEvent, User

LIVE_FALLBACK_PRODUCT_IDS = {
    "starter": "pdt_0NdER6uyezQDgsJWgN0Y0",
    "growth": "pdt_0NdER6zLsWXSeBHVgBATD",
    "pro": "pdt_0NdER71gBCOuCESTei6pY",
}


class BillingConfigError(RuntimeError):
    pass


class BillingVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanDefinition:
    key: str
    label: str
    dodo_price_id: str
    sites_limit: int
    usage_limit: int | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _normalize_datetime(parsed)


def get_plan_definition(plan_key: str) -> PlanDefinition:
    raw = BILLING_PLAN_CONFIG.get(plan_key)
    if not raw:
        raise ValueError("Unknown billing plan.")
    return PlanDefinition(
        key=plan_key,
        label=str(raw.get("label") or plan_key.title()),
        dodo_price_id=str(raw.get("dodo_price_id") or "").strip(),
        sites_limit=int(raw.get("sites_limit") or 0),
        usage_limit=int(raw["usage_limit"]) if raw.get("usage_limit") is not None else None,
    )


def list_plan_definitions() -> list[PlanDefinition]:
    return [get_plan_definition(plan_key) for plan_key in BILLING_PLAN_ORDER]


def plan_from_dodo_price_id(dodo_price_id: str | None) -> str | None:
    if not dodo_price_id:
        return None
    for plan_key in BILLING_PLAN_ORDER:
        if get_plan_definition(plan_key).dodo_price_id == dodo_price_id:
            return plan_key
        if LIVE_FALLBACK_PRODUCT_IDS.get(plan_key) == dodo_price_id:
            return plan_key
    return None


def require_billing_plan(plan_key: str) -> PlanDefinition:
    plan = get_plan_definition(plan_key)
    if not plan.dodo_price_id and not (_is_live_dodo_mode() and LIVE_FALLBACK_PRODUCT_IDS.get(plan.key)):
        raise BillingConfigError(f"Dodo plan ID is not configured for '{plan.key}'.")
    return plan


def _is_live_dodo_mode() -> bool:
    return DODO_PAYMENTS_BASE_URL.rstrip("/").startswith("https://live.dodopayments.com")


def _candidate_product_ids(plan: PlanDefinition) -> list[str]:
    candidates: list[str] = []
    configured = plan.dodo_price_id.strip()
    if configured:
        candidates.append(configured)
    fallback = LIVE_FALLBACK_PRODUCT_IDS.get(plan.key, "").strip()
    if _is_live_dodo_mode() and fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates


async def create_checkout_session(user: User, plan_key: str) -> dict[str, Any]:
    if not DODO_PAYMENTS_API_KEY:
        raise BillingConfigError("Dodo Payments API key is not configured.")

    plan = require_billing_plan(plan_key)
    headers = {
        "Authorization": f"Bearer {DODO_PAYMENTS_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(20.0, connect=10.0)
    last_http_error: httpx.HTTPStatusError | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for product_id in _candidate_product_ids(plan):
            payload = {
                "product_cart": [{"product_id": product_id, "quantity": 1}],
                "customer": {"email": user.email},
                "allowed_payment_method_types": ["credit", "debit"],
                "return_url": f"{DODO_SUCCESS_URL}?plan={plan.key}",
                "cancel_url": DODO_CANCEL_URL,
                "metadata": {
                    "user_id": user.id,
                    "plan": plan.key,
                    "sites_limit": str(plan.sites_limit),
                    "source": "workspace-upgrade",
                },
            }
            response = await client.post(f"{DODO_PAYMENTS_BASE_URL}/checkouts", json=payload, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_http_error = exc
                if product_id == plan.dodo_price_id:
                    try:
                        error_payload = response.json()
                    except ValueError:
                        error_payload = {}
                    error_text = f"{error_payload.get('code', '')} {error_payload.get('message', '')}".lower()
                    if (
                        _is_live_dodo_mode()
                        and "does not exist" in error_text
                        and LIVE_FALLBACK_PRODUCT_IDS.get(plan.key)
                        and LIVE_FALLBACK_PRODUCT_IDS[plan.key] != product_id
                    ):
                        continue
                raise

            data = response.json()
            checkout_url = str(data.get("checkout_url") or "").strip()
            if not checkout_url:
                raise BillingConfigError("Dodo Payments did not return a checkout URL.")
            return data

    if last_http_error is not None:
        raise last_http_error
    raise BillingConfigError("Dodo Payments did not return a checkout URL.")


def verify_webhook_payload(raw_body: str, headers: dict[str, str]) -> dict[str, Any]:
    if not DODO_PAYMENTS_WEBHOOK_KEY:
        raise BillingVerificationError("Dodo webhook secret is not configured.")
    webhook = Webhook(DODO_PAYMENTS_WEBHOOK_KEY)
    try:
        payload = webhook.verify(raw_body, headers)
    except WebhookVerificationError as exc:
        raise BillingVerificationError("Invalid webhook signature.") from exc
    if not isinstance(payload, dict):
        raise BillingVerificationError("Invalid webhook payload.")
    return payload


def record_webhook_event(db: Session, webhook_id: str, event_type: str, payload: dict[str, Any]) -> bool:
    db.add(
        BillingWebhookEvent(
            id=webhook_id,
            event_type=event_type,
            payload=json.dumps(payload, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _mapped_subscription_status(status: str | None) -> str | None:
    normalized = (status or "").strip().lower()
    if not normalized:
        return None
    if normalized == "active":
        return "active"
    if normalized == "on_hold":
        return "past_due"
    if normalized in {"cancelled", "expired", "trial"}:
        return normalized
    if normalized in {"failed", "pending"}:
        return "past_due"
    if normalized == "renewed":
        return "active"
    return normalized


def _resolve_user_from_payload(db: Session, payload_data: dict[str, Any]) -> User | None:
    subscription_id = str(payload_data.get("subscription_id") or "").strip()
    if subscription_id:
        user = db.execute(select(User).where(User.subscription_id == subscription_id)).scalar_one_or_none()
        if user is not None:
            return user

    metadata = payload_data.get("metadata") or {}
    if isinstance(metadata, dict):
        user_id = str(metadata.get("user_id") or "").strip()
        if user_id:
            user = db.get(User, user_id)
            if user is not None:
                return user

    customer = payload_data.get("customer") or {}
    customer_email = str(customer.get("email") or "").strip().lower()
    if customer_email:
        return db.execute(select(User).where(User.email == customer_email)).scalar_one_or_none()
    return None


def _apply_plan(user: User, plan_key: str | None) -> None:
    if not plan_key:
        return
    try:
        plan = get_plan_definition(plan_key)
    except ValueError:
        return
    user.subscription_plan = plan.key
    user.sites_limit = plan.sites_limit


def _derive_plan_key(payload_data: dict[str, Any]) -> str | None:
    metadata = payload_data.get("metadata") or {}
    if isinstance(metadata, dict):
        candidate = str(metadata.get("plan") or "").strip().lower()
        if candidate in BILLING_PLAN_CONFIG:
            return candidate
    return plan_from_dodo_price_id(str(payload_data.get("product_id") or "").strip())


def _apply_subscription_state(user: User, payload_data: dict[str, Any], forced_status: str | None = None) -> None:
    subscription_id = str(payload_data.get("subscription_id") or "").strip()
    if subscription_id:
        user.subscription_id = subscription_id

    plan_key = _derive_plan_key(payload_data)
    _apply_plan(user, plan_key)

    next_period_end = parse_datetime(payload_data.get("next_billing_date")) or parse_datetime(payload_data.get("expires_at"))
    if next_period_end is not None:
        user.current_period_end = next_period_end

    if forced_status:
        user.subscription_status = forced_status
        return

    mapped = _mapped_subscription_status(payload_data.get("status"))
    if mapped:
        user.subscription_status = mapped


def process_webhook_event(db: Session, webhook_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("type") or "").strip()
    if not event_type:
        raise ValueError("Webhook payload missing type.")

    if not record_webhook_event(db, webhook_id, event_type, payload):
        return {"ok": True, "duplicate": True, "event_type": event_type}

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    user = _resolve_user_from_payload(db, data)
    if user is not None:
        if event_type in {"checkout.completed", "subscription.active", "subscription.updated", "subscription.renewed", "subscription.plan_changed"}:
            _apply_subscription_state(user, data, forced_status="active" if event_type in {"checkout.completed", "subscription.active", "subscription.renewed"} else None)
        elif event_type == "payment.succeeded":
            if data.get("subscription_id"):
                _apply_subscription_state(user, data, forced_status="active")
        elif event_type in {"payment.failed", "subscription.failed", "subscription.on_hold"}:
            _apply_subscription_state(user, data, forced_status="past_due")
        elif event_type == "subscription.cancelled":
            _apply_subscription_state(user, data, forced_status="cancelled")
        elif event_type == "subscription.expired":
            _apply_subscription_state(user, data, forced_status="expired")

        db.add(user)

    event_record = db.get(BillingWebhookEvent, webhook_id)
    if event_record is not None:
        event_record.processed_at = datetime.utcnow()
        db.add(event_record)

    db.commit()
    return {"ok": True, "duplicate": False, "event_type": event_type, "user_id": user.id if user else None}
