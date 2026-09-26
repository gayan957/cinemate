"""
Guardian agent. The front door. HTTP service on port 8001.

Every request enters here and every response leaves here.

Start with:
    uvicorn agents.guardian.main:app --port 8001
"""
import sys

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

sys.path.insert(0, ".")
from shared.config import (
    ORCHESTRATOR_URL, ORCHESTRATOR_TIMEOUT, FREE_TIER_DAILY_LIMIT,
)
from shared.schemas import RegisterRequest, LoginRequest, AskRequest
from agents.guardian import auth, sanitizer, audit

app = FastAPI(title="CineMate Guardian Agent", version="1.0")


class PreferencesRequest(BaseModel):
    favourite_genres: list[str] = []
    avoid_genres: list[str] = []


def require_user(authorization: str):
    """Shared check: a valid token must be present."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing authentication token")

    payload = auth.verify_token(authorization.replace("Bearer ", "", 1))
    if not payload:
        raise HTTPException(401, "Invalid or expired token")

    return payload


@app.get("/health")
def health():
    return {"status": "ok", "agent": "guardian"}


# ==================================================================
# Accounts
# ==================================================================
@app.post("/register")
def register(request: RegisterRequest):
    ok, message = auth.register(request.username, request.password, request.age)
    if not ok:
        raise HTTPException(400, message)
    return {"message": message}


@app.post("/login")
def login(request: LoginRequest):
    token = auth.login(request.username, request.password)
    if not token:
        # Deliberately vague: never reveal which part was wrong
        raise HTTPException(401, "Incorrect username or password")
    return {"token": token}


@app.delete("/account")
def delete_account(authorization: str = Header(None)):
    payload = require_user(authorization)
    username = payload["sub"]

    if not auth.delete_user(username):
        raise HTTPException(404, "Account not found")

    audit.log_event(audit.new_trace_id(), "account_deleted", username, None)
    return {"message": "Account and all associated data deleted"}


# ==================================================================
# The main endpoint
# ==================================================================
@app.post("/ask")
def ask(request: AskRequest, authorization: str = Header(None)):
    trace_id = audit.new_trace_id()

    # --- 1. Authentication ---
    payload = require_user(authorization)
    username = payload["sub"]
    age = payload.get("age", 18)

    # --- 2. Free tier limit ---
    used = audit.queries_today(username)
    if used >= FREE_TIER_DAILY_LIMIT:
        audit.log_event(trace_id, "blocked_input", username, "daily limit")
        raise HTTPException(
            429,
            f"Daily limit of {FREE_TIER_DAILY_LIMIT} questions reached. "
            "Premium accounts have no limit.",
        )

    # --- 3. Clean the input ---
    clean = sanitizer.sanitize(request.query)

    # --- 4. Block attacks ---
    safe, reason = sanitizer.detect_injection(clean)
    if not safe:
        audit.log_event(trace_id, "blocked_input", username, reason)
        raise HTTPException(400, f"Request blocked: {reason}")

    audit.log_event(trace_id, "query_received", username, clean)

    # --- 5. Send to the Orchestrator ---
    try:
        response = requests.post(
            f"{ORCHESTRATOR_URL}/process",
            json={
                "query": clean,
                "username": username,
                "age": age,
                "max_results": 5,
            },
            timeout=ORCHESTRATOR_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()

    except requests.RequestException as e:
        audit.log_event(trace_id, "error", username, str(e)[:200])
        raise HTTPException(503, "The system is busy, please try again")

    # --- 6. Check the answer before it leaves ---
    ok, reason = sanitizer.check_output(result.get("answer", ""), age)
    if not ok:
        audit.log_event(trace_id, "blocked_output", username, reason)
        raise HTTPException(403, reason)

    # --- 7. Log what happened, not what was said ---
    audit.log_event(
        trace_id,
        "response_sent",
        username,
        {
            "agents_used": result.get("agents_used", []),
            "recommended": [
                r.get("doc_id") for r in result.get("recommendations", [])
            ],
        },
    )

    result["trace_id"] = trace_id
    return result


# ==================================================================
# Preferences and transparency
# ==================================================================
@app.post("/preferences")
def save_preferences(request: PreferencesRequest,
                     authorization: str = Header(None)):
    payload = require_user(authorization)
    saved = audit.save_preferences(payload["sub"], request.model_dump())

    if not saved:
        raise HTTPException(500, "Could not save preferences")
    return {"message": "Preferences saved, encrypted at rest"}


@app.get("/preferences")
def get_preferences(authorization: str = Header(None)):
    payload = require_user(authorization)
    return audit.load_preferences(payload["sub"])


@app.get("/audit")
def get_audit(authorization: str = Header(None)):
    """
    A user can see their own activity log.

    Demonstrated at the viva to show the audit trail is real.
    """
    payload = require_user(authorization)
    return {"logs": audit.read_logs(30, username=payload["sub"])}