"""
Gemini-based content → category scoring service.

Takes arbitrary text (from PDFs, GitHub readmes, text prompts, etc.) and
asks Google Gemini to estimate relevance to each technical category.

Returns a GeminiScoringResult with structured scores 0-1 and brief
explanations for the strongest categories.

Environment
-----------
  GEMINI_API_KEY  – required (Google AI Studio or Vertex key)
  GEMINI_MODEL    – optional, defaults to "gemini-2.0-flash"
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

from .categories import CATEGORY_KEYS, CATEGORY_MAP, zero_scores
from .models import GeminiScoringResult

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
#  Configuration
# ────────────────────────────────────────────────────────────

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
MAX_CONTENT_CHARS: int = 12_000   # Trim very long uploads to save tokens


# ────────────────────────────────────────────────────────────
#  Prompt template
# ────────────────────────────────────────────────────────────

_CATEGORY_LIST_STR = "\n".join(
    f'  "{key}": "{label}"' for key, label in CATEGORY_MAP.items()
)

SCORING_PROMPT_TEMPLATE = """You are an expert computer-science educator.

Analyse the following user-uploaded content and estimate how strongly it
demonstrates knowledge, familiarity, or experience with **each** of the
technical categories listed below.

### Categories (key → label)
{categories}

### Instructions
1. For EVERY category, assign a relevance score from 0.0 to 1.0:
   - 0.0 = no evidence at all
   - 0.3 = slight or indirect mention
   - 0.6 = clear evidence of understanding
   - 0.9-1.0 = deep, hands-on expertise demonstrated
2. For each category that scores **0.3 or higher**, write one short
   sentence explaining why.
3. Write a 1–2 sentence overall summary of what this content tells us
   about the user's technical knowledge.

### Content to analyse
\"\"\"
{content}
\"\"\"

### Required JSON output
Return ONLY valid JSON (no markdown fences, no commentary) in this
exact schema:

{{
  "scores": {{
    "variables": <float>,
    "functions": <float>,
    ... (every category key)
  }},
  "explanations": {{
    "variables": "<reason or empty string>",
    ...
  }},
  "overall_summary": "<1-2 sentence summary>"
}}
"""


# ────────────────────────────────────────────────────────────
#  Public API
# ────────────────────────────────────────────────────────────

def score_content_with_gemini(
    content: str,
    source_type: str = "text_prompt",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> GeminiScoringResult:
    """
    Send *content* to Gemini and return structured category scores.

    Falls back to a keyword-based heuristic if Gemini is unavailable
    (missing key, network error, etc.) so the pipeline never hard-fails.

    Parameters
    ----------
    content      : The extracted text from the upload.
    source_type  : "text_prompt", "github_repo", or "pdf".
    api_key      : Override for GEMINI_API_KEY env var.
    model        : Override for GEMINI_MODEL env var.

    Returns
    -------
    GeminiScoringResult
    """
    key = api_key or GEMINI_API_KEY
    mdl = model or GEMINI_MODEL

    if not key:
        logger.warning("GEMINI_API_KEY not set – falling back to keyword scorer")
        return _keyword_fallback(content)

    if not content or len(content.strip()) < 10:
        logger.warning("Content too short for scoring – returning zeros")
        return GeminiScoringResult(
            scores=zero_scores(),
            overall_summary="Content was empty or too short to analyse.",
            model_used=mdl,
        )

    trimmed = content[:MAX_CONTENT_CHARS]

    prompt = SCORING_PROMPT_TEMPLATE.format(
        categories=_CATEGORY_LIST_STR,
        content=trimmed,
    )

    try:
        raw_text, token_count = _call_gemini(prompt, key, mdl)
        result = _parse_gemini_response(raw_text)
        result.model_used = mdl
        result.token_count = token_count
        return result

    except Exception as exc:
        logger.error(f"Gemini scoring failed: {exc} – falling back to keywords")
        return _keyword_fallback(content)


# ────────────────────────────────────────────────────────────
#  Gemini API call (google-genai SDK)
# ────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, api_key: str, model: str) -> tuple[str, int]:
    """Call the Gemini API and return (response_text, token_count)."""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai is required for Gemini scoring. "
            "Install with: pip install google-genai"
        )

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.1,          # Keep output deterministic
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    text = response.text or ""
    tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = getattr(response.usage_metadata, "total_token_count", 0)

    return text, tokens


# ────────────────────────────────────────────────────────────
#  Response parsing
# ────────────────────────────────────────────────────────────

def _parse_gemini_response(raw: str) -> GeminiScoringResult:
    """Parse the JSON Gemini returns into a GeminiScoringResult."""
    # Strip markdown code fences if Gemini wraps anyway
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}\nRaw: {raw[:500]}")
        return GeminiScoringResult(
            scores=zero_scores(),
            overall_summary="Failed to parse Gemini response.",
        )

    # Extract scores – clamp to [0, 1]
    raw_scores = data.get("scores", {})
    scores: Dict[str, float] = {}
    for key in CATEGORY_KEYS:
        val = raw_scores.get(key, 0.0)
        try:
            scores[key] = max(0.0, min(1.0, float(val)))
        except (TypeError, ValueError):
            scores[key] = 0.0

    explanations = {
        k: str(v) for k, v in data.get("explanations", {}).items()
        if k in CATEGORY_KEYS
    }

    return GeminiScoringResult(
        scores=scores,
        explanations=explanations,
        overall_summary=data.get("overall_summary", ""),
    )


# ────────────────────────────────────────────────────────────
#  Keyword-based fallback (no Gemini key)
# ────────────────────────────────────────────────────────────

_KEYWORD_MAP: Dict[str, list[str]] = {
    "variables":           ["variable", "var ", "let ", "const ", "assign"],
    "functions":           ["function", "def ", "lambda", "callback", "return "],
    "control_flow":        ["if ", "else", "elif", "switch", "while", "for ", "loop"],
    "recursion":           ["recursion", "recursive", "base case", "call stack"],
    "oop":                 ["object-oriented", "oop", "object oriented"],
    "classes":             ["class ", "class(", "classmethod", "staticmethod"],
    "objects":             ["object", "instance", "instantiate"],
    "inheritance":         ["inherit", "extends", "super(", "subclass", "parent class"],
    "polymorphism":        ["polymorphism", "overriding", "overloading", "duck typing"],
    "encapsulation":       ["encapsulation", "private", "protected", "getter", "setter"],
    "abstraction":         ["abstraction", "abstract class", "interface", "abc"],
    "methods":             ["method", "self.", "this."],
    "constructors":        ["constructor", "__init__", "super()", "new "],
    "data_structures":     ["data structure", "collection", "container"],
    "arrays":              ["array", "list", "vector", "slice"],
    "linked_lists":        ["linked list", "node.next", "singly linked", "doubly linked"],
    "stacks":              ["stack", "push", "pop", "lifo"],
    "queues":              ["queue", "enqueue", "dequeue", "fifo", "bfs"],
    "trees":               ["tree", "binary tree", "bst", "traversal", "root node"],
    "graphs":              ["graph", "vertex", "edge", "adjacency", "dfs", "bfs"],
    "hash_tables":         ["hash", "hashmap", "dictionary", "dict", "hashtable"],
    "algorithms":          ["algorithm", "complexity", "big-o", "optimal"],
    "sorting":             ["sort", "quicksort", "mergesort", "bubblesort", "heapsort"],
    "searching":           ["search", "binary search", "linear search", "lookup"],
    "dynamic_programming": ["dynamic programming", "memoization", "tabulation", "dp "],
    "time_complexity":     ["time complexity", "big o", "O(n)", "O(log", "runtime"],
    "space_complexity":    ["space complexity", "memory usage", "auxiliary space"],
    "databases":           ["database", "db ", "rdbms", "nosql", "mongodb", "postgres"],
    "sql":                 ["sql", "select ", "join ", "query", "insert "],
    "indexing":            ["index", "b-tree", "indexing", "primary key"],
    "apis":                ["api", "rest", "endpoint", "request", "response", "graphql"],
    "operating_systems":   ["operating system", "os ", "kernel", "process", "thread"],
    "memory_management":   ["memory", "heap", "stack memory", "garbage collect", "malloc"],
    "concurrency":         ["concurrency", "parallel", "mutex", "semaphore", "async"],
    "networking":          ["network", "tcp", "udp", "http", "socket", "ip "],
    "git":                 ["git", "commit", "branch", "merge", "pull request", "repo"],
    "testing":             ["test", "unittest", "pytest", "assert", "mock", "tdd"],
}


def _keyword_fallback(content: str) -> GeminiScoringResult:
    """Simple keyword-frequency scorer used when Gemini is unavailable."""
    lower = content.lower()
    word_count = max(len(lower.split()), 1)
    scores: Dict[str, float] = {}

    for cat, keywords in _KEYWORD_MAP.items():
        hits = sum(lower.count(kw) for kw in keywords)
        # Normalise: rough density → clamped 0-1
        raw = min(hits / (word_count * 0.02), 1.0)
        scores[cat] = round(raw, 4)

    # Fill any missing
    for key in CATEGORY_KEYS:
        scores.setdefault(key, 0.0)

    return GeminiScoringResult(
        scores=scores,
        overall_summary="Scored via keyword fallback (Gemini unavailable).",
        model_used="keyword_fallback",
    )
