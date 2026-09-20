"""
Every setting in the project, in one place.
Secrets come from .env and are never written here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# Service addresses
# ------------------------------------------------------------------
GUARDIAN_PORT = 8001
ORCHESTRATOR_PORT = 8000
ANALYSIS_PORT = 8002

GUARDIAN_URL = f"http://127.0.0.1:{GUARDIAN_PORT}"
ORCHESTRATOR_URL = f"http://127.0.0.1:{ORCHESTRATOR_PORT}"
ANALYSIS_URL = f"http://127.0.0.1:{ANALYSIS_PORT}"

# The Retrieval agent has no port. The Orchestrator launches it over MCP.
RETRIEVAL_SERVER = "agents/retrieval/mcp_server.py"

# ------------------------------------------------------------------
# Secrets - loaded from .env, never hard-coded
# ------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------
LLM_MODEL = "llama-3.3-70b-versatile"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384                    # must match VECTOR(384) in schema.sql
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
SUMMARY_MODEL = "sshleifer/distilbart-cnn-12-6"
SPACY_MODEL = "en_core_web_sm"

# ------------------------------------------------------------------
# Retrieval settings
# ------------------------------------------------------------------
CANDIDATES = 40                        # shortlist before re-ranking
FINAL_K = 5                            # results shown to the user
RRF_K = 60                             # rank fusion constant
MMR_LAMBDA = 0.7                       # 1.0 = relevance only, 0.0 = diversity only

RETRIEVAL_METHODS = [
    "bm25", "fulltext", "dense", "hybrid", "reranked", "full"
]
DEFAULT_METHOD = "full"

# ------------------------------------------------------------------
# Ingestion
# ------------------------------------------------------------------
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_DELAY = 0.25                      # seconds between requests
MAX_REVIEWS_PER_MOVIE = 5
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ------------------------------------------------------------------
# Security
# ------------------------------------------------------------------
TOKEN_HOURS = 24
MAX_QUERY_LENGTH = 500
FREE_TIER_DAILY_LIMIT = 10
LOG_RETENTION_DAYS = 30

# ------------------------------------------------------------------
# Timeouts in seconds
# ------------------------------------------------------------------
LLM_TIMEOUT = 30
ANALYSIS_TIMEOUT = 60
ORCHESTRATOR_TIMEOUT = 90