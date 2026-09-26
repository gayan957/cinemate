"""
Audit logging and preference encryption.

What gets logged: that a request happened, which agents ran, which
films were recommended, and any block that fired.

What does NOT get logged: the generated answer. It is reproducible
from the query and the corpus, and a question plus an answer reveals
a lot about a person. This is data minimisation applied on purpose.
"""
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from cryptography.fernet import Fernet, InvalidToken

sys.path.insert(0, ".")
from shared.config import DATABASE_URL, ENCRYPTION_KEY, LOG_RETENTION_DAYS


def new_trace_id() -> str:
    """Short id linking every event belonging to one request."""
    return str(uuid.uuid4())[:8]


# ==================================================================
# STEP 60 — Audit log
# ==================================================================
def log_event(trace_id, event, username, detail=None):
    """
    event: query_received | blocked_input | blocked_output |
           response_sent | error | account_deleted
    """
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail)

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO query_log (username, trace_id, event, detail) "
                    "VALUES (%s, %s, %s, %s)",
                    (username, trace_id, event, detail),
                )
                conn.commit()
    except psycopg.Error as e:
        # Logging must never break the request it is recording
        print(f"audit log failed: {e}")


def read_logs(limit=30, username=None):
    """Recent entries, newest first. Used in the demo to show transparency."""
    query = """
        SELECT trace_id, event, username, detail, created_at
        FROM query_log
    """
    params = []

    if username:
        query += " WHERE username = %s"
        params.append(username)

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [
                    {
                        "trace_id": r[0],
                        "event": r[1],
                        "username": r[2],
                        "detail": r[3],
                        "created_at": r[4].isoformat(),
                    }
                    for r in cur.fetchall()
                ]
    except psycopg.Error as e:
        print(f"read logs failed: {e}")
        return []


def purge_old_logs():
    """
    Delete entries older than the retention period.

    Your report says logs expire. This is where that promise becomes
    real. Run it from a scheduled task, or manually before submission.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM query_log WHERE created_at < %s", (cutoff,)
                )
                removed = cur.rowcount
                conn.commit()
        return removed
    except psycopg.Error as e:
        print(f"purge failed: {e}")
        return 0


# ==================================================================
# STEP 61 — Encrypted preferences
# ==================================================================
_fernet = Fernet(ENCRYPTION_KEY.encode()) if ENCRYPTION_KEY else None


def encrypt(text: str) -> str:
    if not _fernet:
        raise RuntimeError("ENCRYPTION_KEY is not set in .env")
    return _fernet.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    if not _fernet:
        raise RuntimeError("ENCRYPTION_KEY is not set in .env")
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        # Usually means a different key wrote this value
        return ""


def save_preferences(username: str, prefs: dict) -> bool:
    """Stored encrypted. Reading the database directly reveals nothing."""
    blob = encrypt(json.dumps(prefs))

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET prefs_encrypted = %s WHERE username = %s",
                    (blob, username),
                )
                conn.commit()
        return True
    except psycopg.Error as e:
        print(f"save preferences failed: {e}")
        return False


def load_preferences(username: str) -> dict:
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT prefs_encrypted FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
    except psycopg.Error:
        return {}

    if not row or not row[0]:
        return {}

    plain = decrypt(row[0])
    return json.loads(plain) if plain else {}


# ==================================================================
# Rate limiting for the free tier
# ==================================================================
def queries_today(username: str) -> int:
    """Counts queries in the last 24 hours. Backs the free tier limit."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM query_log "
                    "WHERE username = %s AND event = 'query_received' "
                    "AND created_at > %s",
                    (username, cutoff),
                )
                return cur.fetchone()[0]
    except psycopg.Error:
        return 0