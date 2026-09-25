"""
Analysis agent. An HTTP service on port 8002.

Started by run_all.py, or manually with:
    uvicorn agents.analysis.main:app --port 8002
"""
import sys

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, ".")
from shared.schemas import AnalysisRequest, AnalysisResponse, Entity
from agents.analysis import nlp_tools

app = FastAPI(title="CineMate Analysis Agent", version="1.0")


@app.get("/health")
def health():
    """Used by run_all.py and by the Orchestrator's fallback check."""
    return {"status": "ok", "agent": "analysis"}


@app.post("/analyse", response_model=AnalysisResponse)
def analyse(request: AnalysisRequest):
    """Analyse the review text for one film."""
    result = nlp_tools.analyse_text(request.text, request.doc_id)

    return AnalysisResponse(
        doc_id=result["doc_id"],
        entities=[Entity(**e) for e in result["entities"]],
        sentiment=result["sentiment"],
        sentiment_score=result["sentiment_score"],
        summary=result["summary"],
        review_count=result["review_count"],
    )


@app.post("/analyse-batch", response_model=list[AnalysisResponse])
def analyse_batch(requests: list[AnalysisRequest]):
    """
    Analyse several films in one call.

    The Orchestrator sends all five retrieved films together. Five
    separate HTTP calls would add unnecessary round trips.
    """
    return [analyse(r) for r in requests]