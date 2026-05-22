"""
core/config.py
==============
Central configuration, database initialization, and shared utilities.
Uses only free resources: SQLite (built-in), local embeddings.
"""

import os
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("job_agent")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "job_agent.db"

# ── API Keys (all free tiers) ────────────────────────────────────────────────
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY", "")
PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX     = os.getenv("PINECONE_INDEX_NAME", "job-embeddings")
SERPER_API_KEY     = os.getenv("SERPER_API_KEY", "")

# ── Model Config ─────────────────────────────────────────────────────────────
EMBED_MODEL        = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")   # local, free
LLM_MODEL          = os.getenv("LLM_MODEL", "llama-3.1-70b-versatile")
LLM_TEMPERATURE    = float(os.getenv("LLM_TEMPERATURE", "0.3"))
MAX_JOBS           = int(os.getenv("MAX_JOBS_PER_SEARCH", "20"))
MIN_MATCH_SCORE    = float(os.getenv("MIN_MATCH_SCORE", "0.55"))


# ── Database ──────────────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory for dict-like rows."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    conn = get_db()
    cur = conn.cursor()

    # Candidate profiles
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            email       TEXT,
            raw_text    TEXT,
            skills      TEXT,   -- JSON list
            experience  TEXT,   -- JSON list of dicts
            education   TEXT,   -- JSON list
            certifications TEXT, -- JSON list
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Raw job postings fetched from search
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            company     TEXT,
            location    TEXT,
            url         TEXT UNIQUE,
            description TEXT,
            salary      TEXT,
            source      TEXT,   -- linkedin / indeed / google
            match_score REAL DEFAULT 0.0,
            fetched_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Application tracking
    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          INTEGER REFERENCES jobs(id),
            profile_id      INTEGER REFERENCES profiles(id),
            status          TEXT DEFAULT 'pending',  -- pending/applied/interview/rejected/offer
            tailored_resume TEXT,   -- file path
            cover_letter    TEXT,   -- file path
            interview_prep  TEXT,   -- JSON
            applied_at      TIMESTAMP,
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)


# Run on import
init_db()