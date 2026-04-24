import os

from dotenv import load_dotenv

load_dotenv()

CHUNK_TARGET_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 80
MIN_CHUNK_WORDS = 20
RETRIEVAL_TOP_K = 5
RETRIEVAL_MMR_LAMBDA = 0.7
RETRIEVAL_SCORE_THRESHOLD = 0.35
UI_CHUNK_SECTION_LABEL = "UI Layout & Navigation"
UI_SCORE_BONUS = 0.25
UI_SCORE_THRESHOLD = 0.18
MAX_CRAWL_PAGES = int(os.environ.get("MAX_CRAWL_PAGES", "50"))
MAX_CRAWL_DEPTH = int(os.environ.get("MAX_CRAWL_DEPTH", "4"))
MAX_CRAWL_CONCURRENCY = int(os.environ.get("MAX_CRAWL_CONCURRENCY", "4"))
MAX_PAGE_HTML_BYTES = int(os.environ.get("MAX_PAGE_HTML_BYTES", str(2 * 1024 * 1024)))
CRAWL_DELAY_SECONDS = float(os.environ.get("CRAWL_DELAY_SECONDS", "0.05"))
RESPECT_ROBOTS_TXT = os.environ.get("RESPECT_ROBOTS_TXT", "1").lower() in {"1", "true", "yes"}
SITE_CRAWL_DEADLINE_SECONDS = int(os.environ.get("SITE_CRAWL_DEADLINE_SECONDS", "300"))
PROCESS_RETRY_ATTEMPTS = 2
PROCESS_RETRY_DELAY_SECONDS = 2.0
QUESTION_SUGGESTION_CACHE_TTL_SECONDS = 3600
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
VECTOR_CACHE_TTL_SECONDS = 1800
SESSION_TTL_SECONDS = 3600
SESSION_MAX_TURNS = 6
TRIAL_DURATION_DAYS = int(os.getenv("TRIAL_DURATION_DAYS", "14"))
DEFAULT_SITES_LIMIT = int(os.getenv("DEFAULT_SITES_LIMIT", "3"))
SUBSCRIPTION_INACTIVE_MESSAGE = os.getenv(
    "SUBSCRIPTION_INACTIVE_MESSAGE",
    "This chatbot is inactive. Please upgrade.",
)
DATA_DIR = os.environ.get("DATA_DIR", "data")
VECTORS_DIR = os.environ.get("VECTORS_DIR", os.path.join(DATA_DIR, "vectors"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "sites.db"))
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "AI Website Agent")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000")
HF_API_KEY = os.getenv("HF_API_KEY", "")
DODO_PAYMENTS_API_KEY = os.getenv("DODO_PAYMENTS_API_KEY", "")
DODO_PAYMENTS_WEBHOOK_KEY = os.getenv("DODO_PAYMENTS_WEBHOOK_KEY", "")
DODO_PAYMENTS_ENVIRONMENT = os.getenv("DODO_PAYMENTS_ENVIRONMENT", "").strip().lower()
_configured_dodo_base_url = os.getenv("DODO_PAYMENTS_BASE_URL", "").strip()
if _configured_dodo_base_url:
    DODO_PAYMENTS_BASE_URL = _configured_dodo_base_url.rstrip("/")
elif DODO_PAYMENTS_ENVIRONMENT == "test_mode":
    DODO_PAYMENTS_BASE_URL = "https://test.dodopayments.com"
else:
    DODO_PAYMENTS_BASE_URL = "https://live.dodopayments.com"
DODO_SUCCESS_URL = os.getenv("DODO_SUCCESS_URL", f"{BASE_URL}/billing/success")
DODO_CANCEL_URL = os.getenv("DODO_CANCEL_URL", f"{BASE_URL}/dashboard?billing=cancelled")
DODO_STARTER_PRICE_ID = os.getenv("DODO_STARTER_PRICE_ID", "")
DODO_GROWTH_PRICE_ID = os.getenv("DODO_GROWTH_PRICE_ID", "")
DODO_PRO_PRICE_ID = os.getenv("DODO_PRO_PRICE_ID", "")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-only-change-me")
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "fivebot_auth")
GUEST_COOKIE_NAME = os.getenv("GUEST_COOKIE_NAME", "fivebot_guest")
AUTH_COOKIE_MAX_AGE_SECONDS = int(os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", str(60 * 60 * 24 * 30)))
GUEST_COOKIE_MAX_AGE_SECONDS = int(os.getenv("GUEST_COOKIE_MAX_AGE_SECONDS", str(60 * 60 * 24 * 30)))
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "1" if BASE_URL.startswith("https://") else "0").lower() in {"1", "true", "yes"}
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_GSI_SCRIPT_URL = "https://accounts.google.com/gsi/client"

BILLING_PLAN_ORDER = ("starter", "growth", "pro")
BILLING_PLAN_CONFIG = {
    "starter": {
        "label": "Starter",
        "dodo_price_id": DODO_STARTER_PRICE_ID,
        "sites_limit": 1,
        "usage_limit": 500,
    },
    "growth": {
        "label": "Growth",
        "dodo_price_id": DODO_GROWTH_PRICE_ID,
        "sites_limit": 5,
        "usage_limit": 5000,
    },
    "pro": {
        "label": "Pro",
        "dodo_price_id": DODO_PRO_PRICE_ID,
        "sites_limit": 999999,
        "usage_limit": None,
    },
}

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VECTORS_DIR, exist_ok=True)
