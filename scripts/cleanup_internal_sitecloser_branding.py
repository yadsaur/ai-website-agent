from __future__ import annotations

from backend.database import session_scope
from backend.models import Page, Site


INTERNAL_SITE_URL_MARKERS = (
    "5minbot.com",
    "127.0.0.1:8016",
    "ai-website-agent-aikinley.onrender.com",
)


def _is_internal_5minbot_site(site: Site) -> bool:
    haystack = f"{site.name or ''} {site.url or ''}".lower()
    return "5minbot" in haystack or any(marker in haystack for marker in INTERNAL_SITE_URL_MARKERS)


def main() -> None:
    updated_pages = 0
    with session_scope() as db:
        pages = db.query(Page).join(Site, Site.id == Page.site_id).all()
        for page in pages:
            site = db.get(Site, page.site_id) if page.site_id else None
            if site is None or not _is_internal_5minbot_site(site):
                continue
            html = page.html_content or ""
            if "SiteCloser" not in html and "sitecloser" not in html:
                continue

            cleaned = (
                html.replace("SiteCloser", "5minBot")
                .replace("sitecloser", "5minbot")
                .replace("data-5minBot-marked", "data-5minbot-marked")
            )
            if cleaned != html:
                page.html_content = cleaned
                db.add(page)
                updated_pages += 1

    print(f"Updated {updated_pages} internal page snapshots.")


if __name__ == "__main__":
    main()
