from typing import List, Optional
from pydantic import BaseModel, Field


# ==================================================================
# Authentication - Frontend to Guardian
# ==================================================================

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=8)
    age: int = Field(..., ge=10, le=120)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str


# ==================================================================
# The user's question
# ==================================================================

class AskRequest(BaseModel):
    """What the frontend sends to the Guardian."""
    query: str = Field(..., min_length=3, max_length=500)


class UserQuery(BaseModel):
    """What the Guardian sends to the Orchestrator after cleaning."""
    query: str
    username: str
    age: int = 18
    max_results: int = 5


# ==================================================================
# The Orchestrator's plan - produced by the LLM
# ==================================================================

class SearchFilters(BaseModel):
    genres: List[str] = []
    max_runtime: Optional[int] = None
    min_year: Optional[int] = None
    max_age_rating: Optional[str] = None


class QueryPlan(BaseModel):
    """
    The LLM turns a messy sentence into this.
    If needs_clarification is true, we ask instead of searching.
    """
    search_query: str
    filters: SearchFilters = SearchFilters()
    needs_analysis: bool = True
    needs_clarification: bool = False
    question: Optional[str] = None
    options: List[str] = []
    user_intent: str = ""


# ==================================================================
# Retrieval agent - reached over MCP
# ==================================================================

class RetrievedMovie(BaseModel):
    """One film returned by search. Scores are per film, not per chunk."""
    doc_id: str
    tmdb_id: Optional[int] = None
    title: str
    year: int
    runtime: int
    genres: List[str] = []
    age_rating: str = "NR"
    country: Optional[str] = None      # needed for the fairness audit
    director: Optional[str] = None
    overview: str = ""
    score: float
    matched_text: str = ""


class SearchResponse(BaseModel):
    query: str
    results: List[RetrievedMovie]
    method: str                        # bm25 | fulltext | dense | hybrid | reranked | full
    total_found: int
    relaxed_filters: List[str] = []    # filters dropped to find results


# ==================================================================
# Analysis agent - reached over HTTP
# ==================================================================

class AnalysisRequest(BaseModel):
    doc_id: str
    text: str


class Entity(BaseModel):
    text: str
    label: str                         # PERSON | ORG | GPE | WORK_OF_ART | DATE


class AnalysisResponse(BaseModel):
    doc_id: str
    entities: List[Entity] = []
    sentiment: str                     # positive | neutral | negative | unavailable
    sentiment_score: float = 0.0
    summary: str = ""
    review_count: int = 0              # 0 means nothing to analyse


# ==================================================================
# The final answer
# ==================================================================

class Recommendation(BaseModel):
    doc_id: str                        # traces back to a real document
    title: str
    year: int
    reason: str
    sentiment: str = "unavailable"
    retrieval_score: float = 0.0


class FinalResponse(BaseModel):
    """
    What the user receives.

    Either an answer with recommendations, or a clarifying question.
    Never both.
    """
    answer: str = ""
    recommendations: List[Recommendation] = []
    needs_clarification: bool = False
    question: Optional[str] = None
    options: List[str] = []
    agents_used: List[str] = []
    relaxed_filters: List[str] = []
    trace_id: str = ""
    notice: Optional[str] = None       # e.g. "Review analysis unavailable"