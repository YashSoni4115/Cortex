"""
Profile manager – persistence, merge logic, and history tracking.

Responsibilities
----------------
1. Create / load / save user profiles (in-memory + Backboard.io).
2. **Merge** new upload scores into the cumulative profile using
   exponential-moving-average (EMA) blending so that:
     - scores accumulate over time
     - more evidence → higher confidence
     - weak uploads barely shift the profile
3. Record per-upload snapshots for history / audit.

Merge strategy
--------------
For every category *c* with existing score S_old and new upload score S_new:

    effective_new  = S_new  × source_weight          (source-type scaling)
    α              = learning_rate / (1 + upload_count × decay)
    S_updated      = S_old + α × (effective_new − S_old)

This gives us:
  • Early uploads have a bigger impact (α is larger).
  • Later uploads nudge the score gently.
  • Strong source types (GitHub) carry more weight than plain text.
  • Scores stay in [0, 1] because EMA of bounded values is bounded.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .categories import CATEGORY_KEYS, zero_scores
from .models import (
    GeminiScoringResult,
    ProfileUpdateSummary,
    UploadScoreSnapshot,
    UserProfile,
    source_weight,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
#  In-memory store  (swap for DB / Backboard in production)
# ────────────────────────────────────────────────────────────

_profiles: Dict[str, UserProfile] = {}
_upload_history: Dict[str, List[UploadScoreSnapshot]] = {}   # user_id → list


# ────────────────────────────────────────────────────────────
#  Merge hyper-parameters
# ────────────────────────────────────────────────────────────

BASE_LEARNING_RATE: float = 0.40   # How fast scores change on early uploads
LEARNING_RATE_DECAY: float = 0.08  # Dampening per additional upload
MIN_LEARNING_RATE: float = 0.05    # Floor so scores can always evolve

DELTA_EPSILON: float = 0.001       # Deltas smaller than this → "unchanged"


# ────────────────────────────────────────────────────────────
#  Profile CRUD
# ────────────────────────────────────────────────────────────

def initialize_user_profile(user_id: str) -> UserProfile:
    """Create a fresh profile with all-zero scores."""
    profile = UserProfile(user_id=user_id)
    _profiles[user_id] = profile
    _upload_history.setdefault(user_id, [])
    logger.info(f"Initialised profile for user {user_id}")
    return deepcopy(profile)


def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """Return the current profile (or None if user doesn't exist)."""
    p = _profiles.get(user_id)
    return deepcopy(p) if p else None


def get_upload_history(user_id: str) -> List[UploadScoreSnapshot]:
    return list(_upload_history.get(user_id, []))


def _save_profile(profile: UserProfile) -> None:
    """Persist profile (currently in-memory; swap for Backboard later)."""
    profile.updated_at = datetime.now(timezone.utc)
    _profiles[profile.user_id] = profile


def _save_snapshot(snapshot: UploadScoreSnapshot) -> None:
    _upload_history.setdefault(snapshot.user_id, []).append(snapshot)


# ────────────────────────────────────────────────────────────
#  Core merge logic
# ────────────────────────────────────────────────────────────

def merge_profile_scores(
    profile: UserProfile,
    gemini_result: GeminiScoringResult,
    source_type: str,
) -> Dict[str, float]:
    """
    Blend *gemini_result.scores* into *profile.category_scores*.

    Returns a dict of deltas  { category: new_score − old_score }.
    Mutates *profile* in-place (caller should persist afterwards).
    """
    sw = source_weight(source_type)
    n = profile.upload_count  # uploads already counted

    # Adaptive learning rate: high early, decays with experience
    alpha = max(
        BASE_LEARNING_RATE / (1.0 + n * LEARNING_RATE_DECAY),
        MIN_LEARNING_RATE,
    )

    deltas: Dict[str, float] = {}

    for cat in CATEGORY_KEYS:
        s_old = profile.category_scores.get(cat, 0.0)
        s_new = gemini_result.scores.get(cat, 0.0)

        effective_new = s_new * sw
        s_updated = s_old + alpha * (effective_new - s_old)
        # Clamp to [0, 1]
        s_updated = max(0.0, min(1.0, round(s_updated, 6)))

        deltas[cat] = round(s_updated - s_old, 6)
        profile.category_scores[cat] = s_updated

    profile.upload_count += 1
    return deltas


# ────────────────────────────────────────────────────────────
#  Full update pipeline  (called by orchestrator)
# ────────────────────────────────────────────────────────────

def update_user_profile_from_upload(
    user_id: str,
    source_type: str,
    content: str,
    gemini_result: GeminiScoringResult,
) -> ProfileUpdateSummary:
    """
    Merge Gemini scores into the user's living profile and return a
    human-readable summary of what changed.

    If the user doesn't exist yet, auto-initialises a blank profile.
    """
    # 1. Load or create profile
    profile = _profiles.get(user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        _profiles[user_id] = profile
        _upload_history.setdefault(user_id, [])
        logger.info(f"Auto-created profile for user {user_id}")

    profile_before = deepcopy(profile.category_scores)

    # 2. Merge scores
    deltas = merge_profile_scores(profile, gemini_result, source_type)

    # 3. Create snapshot
    snapshot = UploadScoreSnapshot(
        user_id=user_id,
        source_type=source_type,
        content_preview=content[:200] if content else "",
        upload_scores=gemini_result.scores,
        score_deltas=deltas,
        profile_after=deepcopy(profile.category_scores),
    )
    _save_snapshot(snapshot)

    # 4. Save profile
    _save_profile(profile)

    # 5. Build summary
    return get_profile_change_summary(
        user_id=user_id,
        upload_id=snapshot.upload_id,
        source_type=source_type,
        profile_before=profile_before,
        profile_after=profile.category_scores,
        deltas=deltas,
        gemini_summary=gemini_result.overall_summary,
        upload_count=profile.upload_count,
    )


def get_profile_change_summary(
    user_id: str,
    upload_id: str,
    source_type: str,
    profile_before: Dict[str, float],
    profile_after: Dict[str, float],
    deltas: Dict[str, float],
    gemini_summary: str = "",
    upload_count: int = 0,
) -> ProfileUpdateSummary:
    """Build a structured summary of what changed."""

    increased = []
    unchanged = []

    for cat in CATEGORY_KEYS:
        d = deltas.get(cat, 0.0)
        if abs(d) < DELTA_EPSILON:
            unchanged.append(cat)
        else:
            increased.append({
                "category": cat,
                "before": round(profile_before.get(cat, 0.0), 4),
                "after": round(profile_after.get(cat, 0.0), 4),
                "delta": round(d, 4),
            })

    # Sort by absolute delta descending
    increased.sort(key=lambda x: abs(x["delta"]), reverse=True)
    top_influenced = increased[:8]

    return ProfileUpdateSummary(
        user_id=user_id,
        upload_id=upload_id,
        source_type=source_type,
        categories_increased=increased,
        categories_unchanged=unchanged,
        top_influenced=top_influenced,
        profile_before=profile_before,
        profile_after=dict(profile_after),
        gemini_summary=gemini_summary,
        upload_count=upload_count,
    )


# ────────────────────────────────────────────────────────────
#  Utilities
# ────────────────────────────────────────────────────────────

def reset_user_profile(user_id: str) -> UserProfile:
    """Reset a user's scores back to zero (keeps user_id)."""
    profile = initialize_user_profile(user_id)
    _upload_history[user_id] = []
    return profile


def list_all_profiles() -> List[UserProfile]:
    """Return all stored profiles (for admin / debug)."""
    return [deepcopy(p) for p in _profiles.values()]
