"""
AI-powered cleaning suggestions.

Key design principles:
  - Gemini reasons about MEANING (semantic grouping), not just character similarity.
    Active/Inactive are never merged because they mean opposite things, even though
    difflib would group them due to shared characters.
  - standardize_category mappings come from Gemini's semantic analysis of ALL
    distinct values + counts (not just 5 samples).
  - Mechanical sanity checks are applied on top of Gemini's output:
      * Edit-distance check: reject variant if it differs from canonical by > 50%
        of canonical length (guards against obviously wrong groupings).
      * Large-group flag: if a group covers > 40% of column rows, mark as
        recommended=False with a review warning.
  - If ANY Gemini call fails, fall back to the difflib-based rule engine.
  - Every suggestion is validated before it reaches apply_pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import difflib
import pandas as pd

from app.cleaning import suggest_cleaning_steps, find_near_duplicate_categories

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed operations -- must match exactly what apply_pipeline() handles.
# ---------------------------------------------------------------------------
ALLOWED_OPERATIONS: set[str] = {
    "drop_duplicates",
    "drop_column",
    "drop_missing",
    "fill_missing",
    "trim_whitespace",
    "normalize_case",
    "standardize_category",
    "coerce_numeric",
    "flag_negative_values",
    "clip_negative_to_null",
    "remove_outliers",
}

ALLOWED_SEVERITIES: set[str] = {"high", "medium", "low"}

# Max fraction of column rows a single standardize_category group may cover before
# we flag it as requiring manual review (recommended=False).
_MAX_GROUP_FRACTION = 0.40

# Max ratio of edit distance to canonical length before we reject a variant pairing.
_MAX_EDIT_DISTANCE_RATIO = 0.50


# ---------------------------------------------------------------------------
# Sanity checks (mechanical, no AI trust involved)
# ---------------------------------------------------------------------------

def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings."""
    la, lb = len(a), len(b)
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = tmp
    return dp[lb]


def _passes_edit_distance_check(canonical: str, variant: str) -> bool:
    """Return True if the variant is close enough to the canonical to be plausible."""
    canon_l = canonical.strip().lower()
    var_l = variant.strip().lower()
    if canon_l == var_l:
        return True  # case-only difference, always OK
    max_allowed = max(1, int(len(canon_l) * _MAX_EDIT_DISTANCE_RATIO))
    return _edit_distance(canon_l, var_l) <= max_allowed


# ---------------------------------------------------------------------------
# Compact profile summary builder
# ---------------------------------------------------------------------------

def _build_compact_summary(profile: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "row_count": profile.get("row_count", 0),
        "column_count": profile.get("column_count", 0),
        "duplicate_row_count": profile.get("duplicate_row_count", 0),
        "columns": [],
    }
    for col in profile.get("columns", []):
        col_entry: dict[str, Any] = {
            "name": col["name"],
            "dtype": col.get("dtype", "object"),
            "inferred_type": col.get("inferred_type", "text"),
            "missing_count": col.get("missing_count", 0),
            "missing_pct": col.get("missing_pct", 0),
            "unique_count": col.get("unique_count", 0),
            "sample_values": col.get("sample_values", []),
        }
        ns = col.get("numeric_stats")
        if ns:
            col_entry["numeric_stats"] = {
                "min": ns.get("min"),
                "max": ns.get("max"),
                "mean": ns.get("mean"),
                "outlier_count": ns.get("outlier_count", 0),
            }
        summary["columns"].append(col_entry)
    return summary


# ---------------------------------------------------------------------------
# Phase 1: AI-driven semantic grouping per categorical column
# ---------------------------------------------------------------------------

def _semantic_grouping_prompt(column_name: str, value_counts: dict[str, int]) -> str:
    vc_str = json.dumps(value_counts, indent=2)
    return f"""You are a data quality expert analysing the column "{column_name}".

Below is a dictionary of all distinct values and their occurrence counts in this column.

YOUR TASK: Group values that represent the SAME real-world concept under one canonical form.

RULES (read carefully, these are non-negotiable):
1. Values with OPPOSITE or DIFFERENT meanings MUST NEVER be grouped together.
   Examples of things that must NOT be merged:
   - Active / Inactive  (opposites)
   - Yes / No  (opposites)
   - True / False  (opposites)
   - Pass / Fail  (opposites)
   - Open / Closed  (opposites)
2. Only group values that are clearly typos, case variants, or misspellings of the SAME meaning.
   Examples of things that SHOULD be merged:
   - "Bengaluru" / "bangalore" / "BANGALORE" / "Banglore"  (same city, different spelling/case)
   - "Marketing" / "Marekting" / "MARKETING"  (same department, typo/case)
   - "active" / "ACTIVE" / "ACTVE"  (same status word, case + typo)
3. The canonical form should be the most common or most correctly spelled variant.
4. Include a "reasoning" field explaining why you grouped (or did not group) values.
5. If no grouping is needed (all values are semantically distinct), return an empty list [].

Return ONLY a JSON array. No markdown, no prose. Schema:
[
  {{
    "canonical": "the target value",
    "variants": ["variant1", "variant2"],
    "reasoning": "one sentence explanation"
  }}
]

VALUE COUNTS FOR "{column_name}":
{vc_str}
"""


def _ai_semantic_grouping(
    series: pd.Series,
    column_name: str,
    client: Any,
    models_to_try: list[str],
) -> list[dict[str, Any]] | None:
    """
    Ask Gemini to semantically group values in a categorical column.
    Returns list of {canonical, variants, reasoning} dicts, or None on failure.
    """
    from google.genai import types as genai_types

    non_null = series.dropna().astype(str)
    if non_null.empty or non_null.nunique() < 2:
        return []

    # Send ALL distinct values + counts (categorical columns are small)
    value_counts: dict[str, int] = non_null.value_counts().to_dict()
    # Convert numpy int64 keys/values to plain Python ints for JSON serialisation
    value_counts = {str(k): int(v) for k, v in value_counts.items()}

    prompt = _semantic_grouping_prompt(column_name, value_counts)

    last_error: Exception | None = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            groups: list[dict] = json.loads(response.text)
            if not isinstance(groups, list):
                logger.warning("Semantic grouping for %r: unexpected JSON shape", column_name)
                return None
            return groups
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Semantic grouping model %s failed for %r: %s", model_name, column_name, exc)
            continue

    logger.warning("All models failed for semantic grouping of %r: %s", column_name, last_error)
    return None  # Signals: fall back to difflib for this column


def _build_mapping_from_ai_groups(
    groups: list[dict[str, Any]],
    series: pd.Series,
    total_rows: int,
) -> tuple[dict[str, str], bool, str | None]:
    """
    Convert AI semantic groups into a variant→canonical mapping.

    Returns:
        mapping:        {variant: canonical, ...}
        recommended:    False if the group is suspiciously large (> 40% of rows)
        warning_desc:   Optional description override when recommended=False
    """
    mapping: dict[str, str] = {}
    total_mapped_rows = 0
    warning_desc: str | None = None
    recommended = True

    non_null = series.dropna().astype(str)
    value_counts = non_null.value_counts()

    for group in groups:
        canonical = str(group.get("canonical", "")).strip()
        variants = [str(v).strip() for v in group.get("variants", []) if str(v).strip()]
        if not canonical or not variants:
            continue

        group_mapping: dict[str, str] = {}
        for variant in variants:
            if variant == canonical:
                continue  # no-op mapping

            # Mechanical sanity check: reject implausible variant pairings
            if not _passes_edit_distance_check(canonical, variant):
                logger.warning(
                    "Rejected AI grouping: %r → %r (edit distance too large)", variant, canonical
                )
                continue

            # Make sure the variant actually exists in the column (Gemini may hallucinate)
            if variant not in value_counts.index:
                logger.warning(
                    "Rejected AI grouping: %r not found in column (hallucinated?)", variant
                )
                continue

            group_mapping[variant] = canonical
            total_mapped_rows += int(value_counts.get(variant, 0))

        mapping.update(group_mapping)

    # Large-group flag: if this mapping would touch > 40% of rows, require manual review
    if total_rows > 0 and mapping and (total_mapped_rows / total_rows) > _MAX_GROUP_FRACTION:
        recommended = False
        warning_desc = (
            f"This standardization would affect {total_mapped_rows}/{total_rows} rows "
            f"({100 * total_mapped_rows / total_rows:.0f}%) — review carefully before applying."
        )

    return mapping, recommended, warning_desc


def _fill_standardize_mapping_ai(
    df: pd.DataFrame,
    column: str,
    client: Any,
    models_to_try: list[str],
) -> tuple[dict[str, str], bool, str | None]:
    """
    Primary path: use Gemini for semantic grouping.
    Returns (mapping, recommended, warning_desc).
    Falls back to difflib on failure.
    """
    series = df[column]
    total_rows = len(df)

    groups = _ai_semantic_grouping(series, column, client, models_to_try)

    if groups is None:
        # Gemini failed for this column — fall back to difflib
        logger.info("Falling back to difflib for column %r", column)
        clusters = find_near_duplicate_categories(series)
        mapping: dict[str, str] = {}
        for cluster in clusters:
            canonical = cluster[0]
            for variant in cluster[1:]:
                mapping[variant] = canonical
        return mapping, True, None

    mapping, recommended, warning_desc = _build_mapping_from_ai_groups(groups, series, total_rows)
    return mapping, recommended, warning_desc


def _fill_standardize_mapping_difflib(df: pd.DataFrame, column: str) -> dict[str, str]:
    """Fallback: plain difflib clustering."""
    if column not in df.columns:
        return {}
    clusters = find_near_duplicate_categories(df[column])
    mapping: dict[str, str] = {}
    for cluster in clusters:
        canonical = cluster[0]
        for variant in cluster[1:]:
            mapping[variant] = canonical
    return mapping


# ---------------------------------------------------------------------------
# Main suggestions prompt (unchanged structure, no mapping generation)
# ---------------------------------------------------------------------------

def _build_prompt(summary: dict[str, Any]) -> str:
    allowed_ops = ", ".join(sorted(ALLOWED_OPERATIONS))
    return f"""You are a data quality expert. Analyse the dataset summary below and return a JSON object (no markdown, no prose) with exactly two keys:

"suggestions": a list of per-column issue objects.
"general_notes": a list of strings for dataset-level observations (cross-column inconsistencies, suspicious patterns). Can be empty list.

Each object in "suggestions" MUST have:
  "column": the exact column name from the summary
  "issue": a short label (e.g. "missing_values", "negative_values", "mixed_case", "near_duplicate_categories", "non_numeric_in_numeric", "outliers")
  "description": a clear, specific human-readable explanation referencing actual values or statistics
  "operation": MUST be exactly one of: {allowed_ops}
  "params": a dict of parameters appropriate for the operation
  "severity": one of "high", "medium", "low"
  "reason": one sentence explaining why you chose this operation

OPERATION PARAMETER NOTES:
- fill_missing: params must include "column" (str) and "strategy" (one of "median", "mean", "mode", "value")
- normalize_case: params must include "column" (str) and "case" (one of "lower", "title", "upper")
- standardize_category: params must include only "column" (str). DO NOT include "mapping" key.
- trim_whitespace / coerce_numeric / flag_negative_values / clip_negative_to_null / remove_outliers / drop_column / drop_missing: params must include "column" (str)
- drop_duplicates: params must be {{}}

CRITICAL RULES:
1. ONLY use operations from the allowed list. NEVER invent a new operation name.
2. Each "column" value must be the exact column name string from the summary.
3. For standardize_category, DO NOT include "mapping" in params.
4. You may suggest multiple issues for the same column if genuinely distinct problems exist.
5. For general_notes, only include genuine cross-column observations. Don't pad with filler.

DATASET SUMMARY:
{json.dumps(summary, indent=2)}
"""


# ---------------------------------------------------------------------------
# Validation + enrichment
# ---------------------------------------------------------------------------

def _validate_and_enrich(
    raw: dict[str, Any],
    df: pd.DataFrame,
    mapping_cache: dict[str, dict[str, str]],
    ai_client: Any | None,
    models_to_try: list[str],
) -> dict[str, Any] | None:
    operation = raw.get("operation", "")
    column = raw.get("column", "")

    if operation not in ALLOWED_OPERATIONS:
        logger.warning("AI suggestion rejected -- unknown operation %r", operation)
        return None

    if operation != "drop_duplicates" and column not in df.columns:
        logger.warning("AI suggestion rejected -- column %r not in dataframe", column)
        return None

    params: dict[str, Any] = dict(raw.get("params") or {})
    if operation != "drop_duplicates":
        params["column"] = column

    recommended = True
    description = raw.get("description", f"Fix issue in '{column}'")

    if operation == "standardize_category":
        if column not in mapping_cache:
            if ai_client is not None:
                mapping, rec, warn_desc = _fill_standardize_mapping_ai(
                    df, column, ai_client, models_to_try
                )
            else:
                mapping = _fill_standardize_mapping_difflib(df, column)
                rec, warn_desc = True, None

            mapping_cache[column] = {"mapping": mapping, "recommended": rec, "warn_desc": warn_desc}

        cached = mapping_cache[column]
        mapping = cached["mapping"]
        recommended = cached["recommended"]
        warn_desc = cached.get("warn_desc")

        if not mapping:
            logger.warning("standardize_category for %r: no clusters found -- skipping", column)
            return None

        params["mapping"] = mapping
        if not recommended and warn_desc:
            description = warn_desc

    severity = raw.get("severity", "medium")
    if severity not in ALLOWED_SEVERITIES:
        severity = "medium"

    return {
        "id": str(uuid.uuid4()),
        "action": operation,
        "params": params,
        "description": description,
        "severity": severity,
        "ai_reason": raw.get("reason"),
        "recommended": recommended,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_ai_suggestions(
    df: pd.DataFrame,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate AI-powered cleaning suggestions.

    Returns:
        {
          "suggestions": list[dict],   # flat list with id/action/params/description/severity/recommended
          "general_notes": list[str],  # dataset-level observations
          "source": "ai" | "rule_based_fallback",
        }
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("No GEMINI_API_KEY -- using rule-based fallback")
        return {
            "suggestions": suggest_cleaning_steps(df, profile),
            "general_notes": [],
            "source": "rule_based_fallback",
        }

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)
        models_to_try = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.5-flash-lite"]

        summary = _build_compact_summary(profile)
        prompt = _build_prompt(summary)

        raw_text: str | None = None
        last_error: Exception | None = None

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                raw_text = response.text
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("Model %s failed: %s", model_name, exc)
                continue

        if raw_text is None:
            raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

        parsed: dict[str, Any] = json.loads(raw_text)
        raw_suggestions: list[dict] = parsed.get("suggestions", [])
        general_notes: list[str] = [str(n) for n in parsed.get("general_notes", []) if n]

        mapping_cache: dict[str, dict] = {}
        validated: list[dict[str, Any]] = []
        for raw_sug in raw_suggestions:
            result = _validate_and_enrich(raw_sug, df, mapping_cache, client, models_to_try)
            if result is not None:
                validated.append(result)

        # Safety net: ensure drop_duplicates is present if profile says duplicates exist
        dup_rows = profile.get("duplicate_row_count", 0)
        if dup_rows > 0 and not any(v["action"] == "drop_duplicates" for v in validated):
            validated.insert(0, {
                "id": str(uuid.uuid4()),
                "action": "drop_duplicates",
                "params": {},
                "description": f"Remove {dup_rows} duplicate row{'s' if dup_rows > 1 else ''}",
                "severity": "high",
                "ai_reason": None,
                "recommended": True,
            })

        logger.info(
            "AI suggestions: %d valid out of %d from Gemini, %d general notes",
            len(validated), len(raw_suggestions), len(general_notes),
        )
        return {
            "suggestions": validated,
            "general_notes": general_notes,
            "source": "ai",
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "AI suggestions failed (%s: %s) -- falling back to rule-based engine",
            type(exc).__name__, exc,
        )
        return {
            "suggestions": suggest_cleaning_steps(df, profile),
            "general_notes": [],
            "source": "rule_based_fallback",
        }
