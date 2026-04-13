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
MAX_CRAWL_PAGES = int(os.environ.get("MAX_CRAWL_PAGES", "40"))
MAX_CRAWL_DEPTH = int(os.environ.get("MAX_CRAWL_DEPTH", "3"))
CRAWL_DELAY_SECONDS = 0.5
PROCESS_RETRY_ATTEMPTS = 2
PROCESS_RETRY_DELAY_SECONDS = 2.0
QUESTION_SUGGESTION_CACHE_TTL_SECONDS = 3600
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
VECTOR_CACHE_TTL_SECONDS = 1800
SESSION_TTL_SECONDS = 3600
SESSION_MAX_TURNS = 6
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

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VECTORS_DIR, exist_ok=True)
