"""
User accounts: registration, login, and token verification.

Passwords are stored as bcrypt hashes and never in readable form.
Users live in Postgres so accounts survive a restart.
"""
import sys
from datetime import datetime, timedelta, timezone

import psycopg
from jose import JWTError, jwt
from passlib.context import CryptContext

sys.path.insert(0, ".")
from shared.config import DATABASE_URL, JWT_SECRET, TOKEN_HOURS

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _connect():
    return psycopg.connect(DATABASE_URL)


# ==================================================================
# Passwords
# ==================================================================
def hash_password(password: str) -> str:
    """One-way. The original can never be recovered from this."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ==================================================================
# STEP 54 — Registration
# ==================================================================
def register(username: str, password: str, age: int):
    """Create an account. Returns (success, message)."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not 10 <= age <= 120:
        return False, "Please enter a valid age"

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, age, tier)
                    VALUES (%s, %s, %s, 'free')
                    ON CONFLICT (username) DO NOTHING
                    RETURNING username
                    """,
                    (username, hash_password(password), age),
                )
                if cur.fetchone() is None:
                    return False, "That username is already taken"
                conn.commit()
    except psycopg.Error as e:
        print(f"register failed: {e}")
        return False, "Could not create the account, please try again"

    return True, "Account created"


# ==================================================================
# STEP 55 — Login
# ==================================================================
def login(username: str, password: str):
    """Returns a signed token, or None if the details are wrong."""
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT password_hash, age FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
    except psycopg.Error as e:
        print(f"login failed: {e}")
        return None

    if row is None:
        # Hash anyway, so a wrong username takes the same time as a
        # wrong password. Otherwise timing reveals which accounts exist.
        hash_password("dummy-value-for-timing")
        return None

    password_hash, age = row
    if not verify_password(password, password_hash):
        return None

    return create_token(username, age)


def create_token(username: str, age: int) -> str:
    """
    The token carries the age so the Guardian can filter content
    without querying the database on every request.
    """
    payload = {
        "sub": username,
        "age": age,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def verify_token(token: str):
    """Returns the payload, or None if invalid or expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ==================================================================
# STEP 62 — Deletion
# ==================================================================
def delete_user(username: str) -> bool:
    """
    Remove the account and everything linked to it.

    The foreign keys in schema.sql use ON DELETE CASCADE, so removing
    the user row also removes their preferences and log entries.
    """
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM users WHERE username = %s RETURNING username",
                    (username,),
                )
                deleted = cur.fetchone() is not None
                conn.commit()
        return deleted
    except psycopg.Error as e:
        print(f"delete failed: {e}")
        return False