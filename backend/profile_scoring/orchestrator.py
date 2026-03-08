"""
Scoring orchestrator – the single entry-point other modules call.

Flow
----
1. Receive extracted content + metadata from the ingestion pipeline.
2. Call Gemini scorer → category relevance scores.
3. Call profile manager → merge into living profile, record snapshot.
4. Return a ProfileUpdateSummary the API can forward to the frontend.

Also exposes convenience re-exports so callers only need:

    from backend.profile_scoring import update_profile_from_upload
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from .gemini_scorer import score_content_with_gemini
from .profile_manager import (
    get_upload_history,
    get_user_profile,
    initialize_user_profile as _init,
    list_all_profiles,
    reset_user_profile,
    update_user_profile_from_upload as _update,
)
from .models import ProfileUpdateSummary, UserProfile

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
#  Public helpers (re-exported via __init__)
# ────────────────────────────────────────────────────────────

def initialize_user_profile(user_id: str) -> UserProfile:
    """Create or reset a blank profile for *user_id*."""
    return _init(user_id)


def get_user_profile(user_id: str) -> Optional[UserProfile]:  # noqa: F811
    """Retrieve the current profile (or None)."""
    from .profile_manager import get_user_profile as _get
    return _get(user_id)


def get_profile_change_summary(
    user_id: str,
    upload_id: str,
) -> Optional[ProfileUpdateSummary]:
    """Look up the summary for a specific upload by scanning history."""
    history = get_upload_history(user_id)
    for snap in reversed(history):
        if snap.upload_id == upload_id:
            from .profile_manager import get_profile_change_summary as _summary
            # Reconstruct before-state from after − deltas
            before = {
                k: round(snap.profile_after.get(k, 0.0) - snap.score_deltas.get(k, 0.0), 6)
                for k in snap.profile_after
            }
            return _summary(
                user_id=user_id,
                upload_id=snap.upload_id,
                source_type=snap.source_type,
                profile_before=before,
                profile_after=snap.profile_after,
                deltas=snap.score_deltas,
            )
    return None


# ────────────────────────────────────────────────────────────
#  Main entry-point
# ────────────────────────────────────────────────────────────

def update_profile_from_upload(
    user_id: str,
    source_type: str,
    content: str,
    *,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One-call function: score content with Gemini, merge into the user's
    profile, and return a full update summary.

    Parameters
    ----------
    user_id       : Unique user identifier.
    source_type   : "text_prompt", "github_repo", or "pdf".
    content       : The extracted/chunked text from the upload.
    gemini_api_key: Optional override for GEMINI_API_KEY env var.
    gemini_model  : Optional override for GEMINI_MODEL env var.

    Returns
    -------
    dict with keys:
      - success        : bool
      - summary        : ProfileUpdateSummary (serialised)
      - gemini_scores  : raw Gemini output (for debug / transparency)
      - error          : str (only on failure)
    """
    if not content or len(content.strip()) < 5:
        logger.warning(f"Skipping profile update – content too short for user {user_id}")
        return {
            "success": False,
            "error": "Content too short for scoring (< 5 chars).",
            "summary": None,
            "gemini_scores": None,
        }

    try:
        # Step 1 — Gemini scoring
        logger.info(f"Scoring upload for user {user_id} (source={source_type})")
        gemini_result = score_content_with_gemini(
            content=content,
            source_type=source_type,
            api_key=gemini_api_key,
            model=gemini_model,
        )
        logger.info(
            f"Gemini returned scores for {sum(1 for v in gemini_result.scores.values() if v > 0)} "
            f"categories (model={gemini_result.model_used})"
        )

        # Step 2 — Merge into profile
        summary = _update(
            user_id=user_id,
            source_type=source_type,
            content=content,
            gemini_result=gemini_result,
        )

        logger.info(
            f"Profile updated for {user_id}: "
            f"{len(summary.categories_increased)} categories changed, "
            f"upload #{summary.upload_count}"
        )

        return {
            "success": True,
            "summary": summary.model_dump(),
            "gemini_scores": gemini_result.model_dump(),
            "error": None,
        }

    except Exception as exc:
        logger.exception(f"Profile scoring failed for user {user_id}: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "summary": None,
            "gemini_scores": None,
        }
