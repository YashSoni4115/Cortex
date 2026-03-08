"""
FastAPI router for the profile scoring system.

Mount this in your main FastAPI app:

    from backend.profile_scoring.router import router as profile_router
    app.include_router(profile_router)

Endpoints
---------
  POST   /profile/{user_id}/init          – create a blank profile
  GET    /profile/{user_id}               – get current scores
  GET    /profile/{user_id}/top           – top-N categories
  POST   /profile/{user_id}/score-upload  – score content & update profile
  GET    /profile/{user_id}/history       – upload score history
  POST   /profile/{user_id}/reset         – reset to zeros
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .orchestrator import (
    update_profile_from_upload,
    initialize_user_profile,
)
from .profile_manager import (
    get_user_profile,
    get_upload_history,
    reset_user_profile,
)

router = APIRouter(prefix="/profile", tags=["Profile Scoring"])


# ── Request / response bodies ────────────────────────────────

class ScoreUploadRequest(BaseModel):
    source_type: str = Field(
        ..., description="text_prompt | github_repo | pdf"
    )
    content: str = Field(
        ..., min_length=5, description="Extracted text from the upload"
    )
    gemini_api_key: Optional[str] = Field(
        None, description="Override GEMINI_API_KEY (optional)"
    )


# ── Endpoints ────────────────────────────────────────────────

@router.post("/{user_id}/init")
def api_init_profile(user_id: str):
    """Create or re-initialise a user profile with zero scores."""
    profile = initialize_user_profile(user_id)
    return {
        "success": True,
        "profile": profile.model_dump(),
    }


@router.get("/{user_id}")
def api_get_profile(user_id: str):
    """Retrieve the user's current category scores."""
    profile = get_user_profile(user_id)
    if profile is None:
        raise HTTPException(404, f"No profile found for user {user_id}")
    return {
        "success": True,
        "profile": profile.model_dump(),
    }


@router.get("/{user_id}/top")
def api_top_categories(user_id: str, n: int = 5):
    """Return the user's top-N highest-scoring categories."""
    profile = get_user_profile(user_id)
    if profile is None:
        raise HTTPException(404, f"No profile found for user {user_id}")
    return {
        "success": True,
        "top": profile.get_top_categories(n),
        "upload_count": profile.upload_count,
    }


@router.post("/{user_id}/score-upload")
def api_score_upload(user_id: str, body: ScoreUploadRequest):
    """
    Score uploaded content with Gemini and merge into the user's profile.

    Returns the full update summary including deltas and top-influenced
    categories.
    """
    result = update_profile_from_upload(
        user_id=user_id,
        source_type=body.source_type,
        content=body.content,
        gemini_api_key=body.gemini_api_key,
    )
    if not result["success"]:
        raise HTTPException(422, result.get("error", "Scoring failed"))
    return result


@router.get("/{user_id}/history")
def api_upload_history(user_id: str, limit: int = 20):
    """Return recent upload score snapshots for the user."""
    history = get_upload_history(user_id)
    snapshots = [s.model_dump() for s in history[-limit:]]
    return {
        "success": True,
        "count": len(snapshots),
        "history": snapshots,
    }


@router.post("/{user_id}/reset")
def api_reset_profile(user_id: str):
    """Reset the user's profile back to zero scores."""
    profile = reset_user_profile(user_id)
    return {
        "success": True,
        "profile": profile.model_dump(),
    }
