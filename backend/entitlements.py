from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import SUBSCRIPTION_INACTIVE_MESSAGE
from backend.models import Site, User


TRIAL_ENDED_MESSAGE = SUBSCRIPTION_INACTIVE_MESSAGE
ALLOWED_SUBSCRIPTION_STATUSES = {"trial", "active"}


@dataclass
class EntitlementResult:
    allowed: bool
    state: str
    days_remaining: int | None
    message: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def trial_days_remaining(user: User | None, now: datetime | None = None) -> int | None:
    if user is None:
        return None
    if now is None:
        now = _utc_now()
    trial_end = _normalize_dt(user.trial_ends_at)
    if trial_end is None:
        return None
    remaining = trial_end - now
    if remaining.total_seconds() <= 0:
        return 0
    return max(1, remaining.days + (1 if remaining.seconds else 0))


def evaluate_user_entitlement(user: User | None, now: datetime | None = None) -> EntitlementResult:
    if user is None:
        return EntitlementResult(allowed=True, state="guest", days_remaining=None)

    if now is None:
        now = _utc_now()

    status = (user.subscription_status or "").strip().lower() or "trial"
    trial_end = _normalize_dt(user.trial_ends_at)
    current_period_end = _normalize_dt(getattr(user, "current_period_end", None))

    if status == "active":
        if current_period_end is None or current_period_end > now:
            return EntitlementResult(allowed=True, state="active", days_remaining=None)
        return EntitlementResult(allowed=False, state="expired", days_remaining=0, message=TRIAL_ENDED_MESSAGE)

    if status == "trial":
        if trial_end and trial_end > now:
            return EntitlementResult(allowed=True, state="trial", days_remaining=trial_days_remaining(user, now))
        return EntitlementResult(allowed=False, state="expired", days_remaining=0, message=TRIAL_ENDED_MESSAGE)

    if status in {"past_due", "cancelled", "expired"}:
        return EntitlementResult(allowed=False, state=status, days_remaining=trial_days_remaining(user, now), message=TRIAL_ENDED_MESSAGE)

    return EntitlementResult(allowed=False, state="expired", days_remaining=0, message=TRIAL_ENDED_MESSAGE)


def sync_user_subscription_status(db: Session, user: User | None, now: datetime | None = None) -> EntitlementResult:
    result = evaluate_user_entitlement(user, now=now)
    if user is None:
        return result
    if result.state == "expired" and user.subscription_status != "expired":
        user.subscription_status = "expired"
        db.add(user)
    return result


def evaluate_site_entitlement(db: Session, site: Site, now: datetime | None = None) -> EntitlementResult:
    if not site.user_id:
        return EntitlementResult(allowed=True, state="guest", days_remaining=None)
    owner = db.get(User, site.user_id)
    return sync_user_subscription_status(db, owner, now=now)
