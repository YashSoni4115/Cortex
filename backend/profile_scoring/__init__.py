"""
Personal Knowledge Profile Scoring System.

Maintains a dynamic per-user score (0-1) for every technical category,
updated automatically whenever a new upload is ingested.  Uses Gemini
for content analysis and returns structured deltas so the frontend can
visualise how a user's knowledge map evolves over time.

Public API
----------
- update_profile_from_upload()   – one-call entrypoint
- initialize_user_profile()      – create a blank profile
- get_user_profile()             – retrieve current scores
- get_profile_change_summary()   – delta breakdown for an upload

Internal services
-----------------
- gemini_scorer   – Gemini-based content → category scoring
- profile_manager – merge logic, persistence, history
- categories      – canonical list of tracked categories
- models          – Pydantic data models
"""

from .orchestrator import (
    update_profile_from_upload,
    initialize_user_profile,
    get_user_profile,
    get_profile_change_summary,
)

__all__ = [
    "update_profile_from_upload",
    "initialize_user_profile",
    "get_user_profile",
    "get_profile_change_summary",
]
