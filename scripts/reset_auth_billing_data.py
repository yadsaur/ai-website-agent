#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select, text

from backend.database import session_scope
from backend.models import BillingWebhookEvent, Chunk, Page, Site, User


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset auth and billing test data.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to run without --yes")
        return 1

    with session_scope() as db:
        user_site_ids = db.execute(select(Site.id).where(Site.user_id.is_not(None))).scalars().all()
        if user_site_ids:
            db.execute(delete(Chunk).where(Chunk.site_id.in_(user_site_ids)))
            db.execute(delete(Page).where(Page.site_id.in_(user_site_ids)))
            for site_id in user_site_ids:
                db.execute(text("DELETE FROM site_vectors WHERE site_id = :site_id"), {"site_id": site_id})
            db.execute(delete(Site).where(Site.id.in_(user_site_ids)))

        db.execute(delete(BillingWebhookEvent))
        db.execute(delete(User))

    print("Auth and billing data reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
