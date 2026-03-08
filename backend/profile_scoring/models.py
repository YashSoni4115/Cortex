"""
Pydantic data models for the profile scoring system.

All data that crosses module boundaries is typed here so that
serialisation, validation, and IDE auto-complete work out of the box.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .categories import CATEGORY_KEYS, zero_scores


# ────────────────────────────────────────────────────────────
#  User Profile
# ────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    """Living profile storing cumulative category scores for one user."""

    user_id: str
    category_scores: Dict[str, float] = Field(default_factory=zero_scores)
    upload_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_top_categories(self, n: int = 5) -> List[Dict]:
        """Return the n highest-scoring categories."""
        ranked = sorted(
            self.category_scores.items(), key=lambda kv: kv[1], reverse=True
        )
        return [{"category": k, "score": round(v, 4)} for k, v in ranked[:n]]


# ────────────────────────────────────────────────────────────
#  Gemini Scoring Result (per-upload)
# ────────────────────────────────────────────────────────────

class CategoryScore(BaseModel):
    """Score + optional rationale for one category from Gemini."""
    category: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class GeminiScoringResult(BaseModel):
    """Full Gemini response for one piece of content."""
    scores: Dict[str, float] = Field(default_factory=zero_scores)
    explanations: Dict[str, str] = Field(default_factory=dict)
    overall_summary: str = ""
    model_used: str = ""
    token_count: int = 0


# ────────────────────────────────────────────────────────────
#  Upload Score Snapshot
# ────────────────────────────────────────────────────────────

class UploadScoreSnapshot(BaseModel):
    """Record of how one upload affected the user's profile."""

    upload_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    source_type: str                       # text_prompt | github_repo | pdf
    content_preview: str = ""              # first 200 chars

    # Scores Gemini assigned to *this* upload
    upload_scores: Dict[str, float] = Field(default_factory=zero_scores)

    # How the user's cumulative profile changed
    score_deltas: Dict[str, float] = Field(default_factory=zero_scores)

    # Profile state after this upload
    profile_after: Dict[str, float] = Field(default_factory=zero_scores)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ────────────────────────────────────────────────────────────
#  Profile Update Summary  (returned to callers / API)
# ────────────────────────────────────────────────────────────

class ProfileUpdateSummary(BaseModel):
    """Human-readable summary of what changed after an upload."""

    user_id: str
    upload_id: str
    source_type: str

    categories_increased: List[Dict] = Field(default_factory=list)
    categories_unchanged: List[str] = Field(default_factory=list)
    top_influenced: List[Dict] = Field(default_factory=list)

    profile_before: Dict[str, float] = Field(default_factory=dict)
    profile_after: Dict[str, float] = Field(default_factory=dict)

    gemini_summary: str = ""
    upload_count: int = 0


# ────────────────────────────────────────────────────────────
#  Source-type weights
# ────────────────────────────────────────────────────────────

SOURCE_TYPE_WEIGHTS: Dict[str, float] = {
    "github_repo":  0.85,    # Strong technical evidence
    "pdf":          0.65,    # Medium evidence (notes / assignments)
    "text_prompt":  0.45,    # Weaker unless very detailed
}

DEFAULT_SOURCE_WEIGHT: float = 0.50


def source_weight(source_type: str) -> float:
    return SOURCE_TYPE_WEIGHTS.get(source_type, DEFAULT_SOURCE_WEIGHT)
