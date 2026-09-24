"""
Central configuration for Gemini AI models used across the platform.

gemini-3.6-flash is placed first, per Google's current explicit recommendation.
gemini-flash-latest is included as an auto-updating alias to ensure resilient fallback
across future version deprecations.
"""

from __future__ import annotations

GEMINI_MODELS_TO_TRY: list[str] = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash",
]
