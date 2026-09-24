"""
Cleaning rules engine.

Provides automated, rule-based suggestions based on profiling reports,
and executes pipeline steps sequentially on a pandas DataFrame.
"""

from __future__ import annotations

import difflib
import re
import uuid
from typing import Any

import pandas as pd


OPPOSITES: set[tuple[str, str]] = {
    ("male", "female"), ("female", "male"),
    ("active", "inactive"), ("inactive", "active"),
    ("yes", "no"), ("no", "yes"),
    ("true", "false"), ("false", "true"),
    ("pass", "fail"), ("fail", "pass"),
    ("open", "closed"), ("closed", "open"),
    ("in", "out"), ("out", "in"),
    ("on", "off"), ("off", "on"),
    ("high", "low"), ("low", "high"),
    ("good", "bad"), ("bad", "good"),
    ("m", "f"), ("f", "m"),
}

# ---------------------------------------------------------------------------
# COLUMN_TYPE_RULES — delegates to centralised validation_rules.py
# ---------------------------------------------------------------------------
# The canonical validation logic lives in validation_rules.py.
# This adapter converts ValidationIssue objects to the legacy dict format
# that the existing UI / pipeline expects (row_index, raw_value,
# suggested_value, reason).

from app.validation_rules import (
    COLUMN_VALIDATION_RULES,
    validate_column,
    detect_semantic_type,
    validate_email as _vr_validate_email,
    validate_phone as _vr_validate_phone,
    validate_name as _vr_validate_name,
    validate_age as _vr_validate_age,
    validate_gender as _vr_validate_gender,
    validate_boolean as _vr_validate_boolean,
    validate_currency as _vr_validate_currency,
    validate_percentage as _vr_validate_percentage,
    validate_zipcode as _vr_validate_zipcode,
    validate_id as _vr_validate_id,
    detect_outliers_iqr,
    detect_dataset_level_issues,
    run_all_cross_column_validations,
)


def _adapt_validation_issues(issues_list) -> list[dict]:
    """Convert ValidationIssue objects to legacy flagged_values dict format."""
    return [
        {
            "row_index": i.row_index,
            "raw_value": i.raw_value,
            "suggested_value": i.suggested_value,
            "reason": i.issue,
            "confidence": i.confidence,
            "severity": i.severity,
        }
        for i in issues_list
    ]


def _make_type_adapter(validator_fn):
    """Create a COLUMN_TYPE_RULES-compatible adapter for a validation_rules validator."""
    def adapter(series: pd.Series, column_name: str) -> list[dict]:
        issues = validator_fn(series, column_name)
        return _adapt_validation_issues(issues)
    return adapter


# Registry: maps inferred_type / semantic_type → validation function.
# Each function signature: (series: pd.Series, column_name: str) -> list[dict]
# Delegates to the canonical validators in validation_rules.py.
COLUMN_TYPE_RULES: dict[str, callable] = {
    "phone": _make_type_adapter(_vr_validate_phone),
    "email": _make_type_adapter(_vr_validate_email),
    "name": _make_type_adapter(_vr_validate_name),
    "age": _make_type_adapter(_vr_validate_age),
    "gender": _make_type_adapter(_vr_validate_gender),
    "boolean": _make_type_adapter(_vr_validate_boolean),
    "currency": _make_type_adapter(_vr_validate_currency),
    "percentage": _make_type_adapter(_vr_validate_percentage),
    "zipcode": _make_type_adapter(_vr_validate_zipcode),
    "id": _make_type_adapter(_vr_validate_id),
}



def clean_numeric_value(val: Any) -> Any:
    """Normalize numeric values by stripping currency symbols, commas, and whitespace."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/a", "na", "-"):
        return None
    # Check for negative format: leading minus, negative sign, or parentheses e.g. (1,000)
    is_neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-") or ("-" in s and not re.search(r"\d-\d", s)):
        is_neg = True
    cleaned = re.sub(r"[^\d.]", "", s)
    if not cleaned or cleaned == ".":
        return None
    try:
        num = float(cleaned) if "." in cleaned else int(cleaned)
        return -num if is_neg else num
    except (ValueError, TypeError):
        return cleaned


def find_near_duplicate_categories(
    series: pd.Series, cutoff: float = 0.6
) -> list[list[str]]:
    """Cluster near-duplicate text values in a Series using Python's difflib.
    Returns a list of clusters, where each cluster is [canonical_variant, variant2, variant3, ...].
    Canonical variant is picked as the most frequent string in the data.
    """
    non_null = series.dropna().astype(str)
    if non_null.empty:
        return []

    val_counts = non_null.value_counts()
    sorted_vals = [str(v) for v in val_counts.index if len(str(v).strip()) > 0]
    if len(sorted_vals) < 2:
        return []

    clusters: list[list[str]] = []
    assigned: set[str] = set()

    for canonical in sorted_vals:
        if canonical in assigned:
            continue

        canonical_clean = canonical.strip().lower()
        possibilities = [v for v in sorted_vals if v not in assigned and v != canonical]
        if not possibilities:
            continue

        possibility_map = {}
        for p in possibilities:
            p_clean = p.strip().lower()
            if (canonical_clean, p_clean) in OPPOSITES:
                continue
            if p_clean not in possibility_map:
                possibility_map[p_clean] = p

        if not possibility_map:
            continue

        matches_clean = difflib.get_close_matches(
            canonical_clean, list(possibility_map.keys()), n=len(possibility_map), cutoff=cutoff
        )

        cluster = [canonical]
        for m_clean in matches_clean:
            for p in possibilities:
                p_clean = p.strip().lower()
                if (canonical_clean, p_clean) in OPPOSITES:
                    continue
                if p not in assigned and p != canonical and p.strip().lower() == m_clean:
                    cluster.append(p)
                    assigned.add(p)

        if len(cluster) > 1:
            assigned.add(canonical)
            clusters.append(cluster)

    return clusters


find_near_duplicate_category_clusters = find_near_duplicate_categories


def suggest_cleaning_steps(df: pd.DataFrame, profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate rule-based cleaning step suggestions from a dataframe and its profile report."""
    suggestions: list[dict[str, Any]] = []

    # 1. Duplicate rows check
    dup_rows = profile.get("duplicate_row_count", 0)
    if dup_rows > 0:
        suggestions.append({
            "id": str(uuid.uuid4()),
            "action": "drop_duplicates",
            "params": {},
            "description": f"Remove {dup_rows} duplicate row{'s' if dup_rows > 1 else ''}",
            "severity": "high",
        })

    # 2. Column missing values, text cleanliness, fuzzy categories, and numeric validity checks
    for col in profile.get("columns", []):
        col_name = col["name"]
        if col_name not in df.columns:
            continue

        col_series = df[col_name]
        missing_count = col.get("missing_count", 0)
        missing_pct = col.get("missing_pct", 0)
        inferred_type = col.get("inferred_type", "text")
        col_lower = col_name.lower()
        is_phone_col = (inferred_type == "phone") or any(k in col_lower for k in ("phone", "mobile", "contact"))
        is_email_col = (inferred_type == "email") or any(k in col_lower for k in ("email", "e-mail"))

        # Missing values
        if missing_count > 0:
            if missing_pct >= 50.0:
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "drop_column",
                    "params": {"column": col_name},
                    "description": f"Drop column '{col_name}' ({missing_pct}% missing values)",
                    "severity": "high",
                })
            elif not is_phone_col and not is_email_col and inferred_type in ("numeric", "non_negative_numeric", "identifier"):
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "fill_missing",
                    "params": {"column": col_name, "strategy": "median"},
                    "description": f"Fill {missing_count} missing value{'s' if missing_count > 1 else ''} in '{col_name}' with median",
                    "severity": "medium",
                })
            else:
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "fill_missing",
                    "params": {"column": col_name, "strategy": "mode"},
                    "description": f"Fill {missing_count} missing value{'s' if missing_count > 1 else ''} in '{col_name}' with mode",
                    "severity": "medium",
                })

        # Centralised per-type validation via COLUMN_TYPE_RULES registry.
        # Uses the full 47-type semantic detection from validation_rules.py.
        # Determines effective type for this column and runs the registered
        # validator if one exists.
        effective_type = detect_semantic_type(col_series, col_name)
        # Backward compat overrides:
        if is_phone_col:
            effective_type = "phone"
        elif is_email_col:
            effective_type = "email"

        rule_fn = COLUMN_TYPE_RULES.get(effective_type)
        if rule_fn is not None:
            flagged_items = rule_fn(col_series, col_name)
            if flagged_items:
                action_name = f"flag_invalid_{effective_type}"
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": action_name,
                    "params": {"column": col_name, "flagged_count": len(flagged_items)},
                    "description": (
                        f"Flag {len(flagged_items)} {effective_type} value"
                        f"{'s' if len(flagged_items) > 1 else ''}"
                        f" with invalid format in '{col_name}'"
                    ),
                    "severity": "medium",
                    "recommended": True,
                    "flagged_values": flagged_items,
                })


        # Phase 3a & 4: Non-numeric text values or formatted numbers in numeric-typed columns (excluding phone)
        if not is_phone_col and not is_email_col and (
            inferred_type in ("numeric", "non_negative_numeric", "identifier") or pd.api.types.is_numeric_dtype(col_series)
        ):
            non_null = col_series.dropna()
            if not non_null.empty:
                raw_coerced = pd.to_numeric(non_null, errors="coerce")
                raw_fails = int((non_null.notna() & raw_coerced.isna()).sum())

                cleaned_non_null = non_null.apply(clean_numeric_value)
                coerced = pd.to_numeric(cleaned_non_null, errors="coerce")
                failed_mask = non_null.notna() & coerced.isna()
                unparseable_count = int(failed_mask.sum())

                is_stored_as_text = str(col_series.dtype) == "object" or not pd.api.types.is_numeric_dtype(col_series)

                if unparseable_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "coerce_numeric",
                        "params": {"column": col_name},
                        "description": f"Convert {unparseable_count} non-numeric text value{'s' if unparseable_count > 1 else ''} in '{col_name}' to NaN",
                        "severity": "high",
                    })
                elif is_stored_as_text and (inferred_type in ("numeric", "non_negative_numeric") or raw_fails > 0):
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "coerce_numeric",
                        "params": {"column": col_name},
                        "description": f"Convert '{col_name}' to numeric (strip currency symbols and commas)",
                        "severity": "medium",
                    })

        # Phase 4b: Fallback — detect currency/comma-formatted numeric columns that profiling typed as text
        # This catches columns like "Revenue" containing "₹1,500" where pd.to_numeric() alone fails,
        # causing the profiler to label them as "text" instead of "numeric".
        elif not is_phone_col and not is_email_col and (
            inferred_type in ("text", "categorical")
            and str(col_series.dtype) == "object"
        ):
            non_null = col_series.dropna()
            if len(non_null) >= 2:
                cleaned_vals = non_null.apply(clean_numeric_value)
                coerced_vals = pd.to_numeric(cleaned_vals, errors="coerce")
                valid_count = int(coerced_vals.notna().sum())
                # If ≥50% of non-null values become valid numbers after stripping
                # currency symbols and commas, this is a numeric column in disguise
                if valid_count >= max(2, len(non_null) * 0.5):
                    # Check that raw pd.to_numeric would actually fail on some values
                    # (otherwise there's nothing to clean and no suggestion needed)
                    raw_coerced = pd.to_numeric(non_null, errors="coerce")
                    raw_valid = int(raw_coerced.notna().sum())
                    if raw_valid < valid_count:
                        suggestions.append({
                            "id": str(uuid.uuid4()),
                            "action": "coerce_numeric",
                            "params": {"column": col_name},
                            "description": f"Convert '{col_name}' to numeric (strip currency symbols and commas)",
                            "severity": "medium",
                        })

        # Phase 3b: Negative values in non_negative_numeric columns (excluding phone)
        if not is_phone_col and not is_email_col and inferred_type == "non_negative_numeric":
            coerced_nums = pd.to_numeric(col_series.apply(clean_numeric_value), errors="coerce")
            neg_mask = coerced_nums < 0
            neg_count = int(neg_mask.sum())
            if neg_count > 0:
                flagged_items = []
                for idx in col_series.index[neg_mask]:
                    raw_v = col_series.loc[idx]
                    num_v = coerced_nums.loc[idx]
                    sugg_v = abs(num_v) if pd.notna(num_v) else 0
                    if hasattr(sugg_v, "item"):
                        sugg_v = sugg_v.item()
                    raw_out = raw_v
                    if hasattr(raw_out, "item"):
                        raw_out = raw_out.item()
                    elif not isinstance(raw_out, (int, float, str)):
                        raw_out = str(raw_out)

                    flagged_items.append({
                        "row_index": int(idx),
                        "raw_value": raw_out,
                        "suggested_value": sugg_v,
                        "reason": f"Negative value ({raw_v}) in non-negative column",
                    })
                val_previews = ", ".join(str(f["raw_value"]) for f in flagged_items[:3])
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_negative_values",
                    "params": {"column": col_name},
                    "description": f"Flag {neg_count} negative value{'s' if neg_count > 1 else ''} in '{col_name}': {val_previews}",
                    "severity": "medium",
                    "flagged_values": flagged_items,
                })

        # Text cleanliness checks for text/categorical columns (excluding phone)
        if not is_phone_col and (inferred_type in ("text", "categorical", "email") or str(col_series.dtype) == "object"):
            non_null_str = col_series.dropna().astype(str)
            if not non_null_str.empty:
                # 1a. Extra spaces
                space_mask = non_null_str.str.contains(r"^\s|\s$|\s{2,}", regex=True)
                space_count = int(space_mask.sum())
                if space_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "trim_whitespace",
                        "params": {"column": col_name},
                        "description": f"Trim leading/trailing and extra internal spaces in '{col_name}' ({space_count} value{'s' if space_count > 1 else ''})",
                        "severity": "low",
                    })

                # 1b. Fuzzy category consistency (standardize_category)
                has_category_clusters = False
                is_date_col = inferred_type in ("datetime", "date") or any(k in col_name.lower() for k in ("date", "dob"))
                if not is_date_col and inferred_type not in ("numeric", "non_negative_numeric", "identifier", "email") and (
                    inferred_type in ("categorical", "text")
                    or (str(col_series.dtype) == "object" and col_series.nunique() < 50)
                ):
                    clusters = find_near_duplicate_categories(col_series)
                    val_counts = non_null_str.value_counts().to_dict()
                    val_counts = {str(k): int(v) for k, v in val_counts.items()}
                    for cluster in clusters:
                        canonical = cluster[0]
                        variants = cluster[1:]
                        mapping = {v: canonical for v in variants}
                        variant_str = ", ".join(variants)
                        suggestions.append({
                            "id": str(uuid.uuid4()),
                            "action": "standardize_category",
                            "params": {
                                "column": col_name,
                                "mapping": mapping,
                                "distinct_values": val_counts,
                                "variant_confidences": {v: "high" for v in variants},
                                "groups": [{
                                    "canonical": canonical,
                                    "reasoning": f"Clustered by character similarity to '{canonical}'",
                                    "variants": [{"value": v, "confidence": "high", "count": int(val_counts.get(v, 0))} for v in cluster],
                                }],
                            },
                            "description": f"{len(cluster)} spellings of '{canonical}' found ({variant_str}) — standardize to one?",
                            "severity": "medium",
                        })
                        has_category_clusters = True

                # 1c. Inconsistent capitalization
                stripped_str = non_null_str.str.strip()
                lower_groups = stripped_str.groupby(stripped_str.str.lower()).nunique()
                inconsistent_groups = lower_groups[lower_groups > 1]
                if not inconsistent_groups.empty:
                    title_cnt = int(stripped_str.apply(lambda s: s.istitle()).sum())
                    lower_cnt = int(stripped_str.apply(lambda s: s.islower()).sum())
                    case_param = "title" if title_cnt >= lower_cnt else "lower"

                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "normalize_case",
                        "params": {"column": col_name, "case": case_param},
                        "description": f"Normalize inconsistent capitalization in '{col_name}' ({len(inconsistent_groups)} variant group{'s' if len(inconsistent_groups) > 1 else ''})",
                        "severity": "low",
                    })

        # 3. Numeric outlier checks (excluding phone)
        if not is_phone_col:
            numeric_stats = col.get("numeric_stats")
            if numeric_stats and numeric_stats.get("outlier_count", 0) > 0:
                outlier_cnt = numeric_stats["outlier_count"]
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "remove_outliers",
                    "params": {"column": col_name, "method": "iqr"},
                    "description": f"Flag {outlier_cnt} outlier{'s' if outlier_cnt > 1 else ''} in '{col_name}' with IQR method (adds '{col_name}_outlier' column)",
                    "severity": "medium",
                })

    return suggestions


def apply_pipeline(
    df: pd.DataFrame, steps: list[Any]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Execute a list of cleaning steps sequentially on a DataFrame and return (cleaned_df, log)."""
    cleaned_df = df.copy()
    log: list[dict[str, Any]] = []

    for step in steps:
        if hasattr(step, "action"):
            action = step.action
            params = step.params or {}
            description = step.description
        else:
            action = step.get("action", "")
            params = step.get("params") or {}
            description = step.get("description", "")

        rows_before = len(cleaned_df)

        if action == "drop_duplicates":
            cleaned_df = cleaned_df.drop_duplicates()
        elif action == "drop_column":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df = cleaned_df.drop(columns=[col])
        elif action == "drop_missing":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df = cleaned_df.dropna(subset=[col])
            else:
                cleaned_df = cleaned_df.dropna()
        elif action == "fill_missing":
            col = params.get("column")
            strategy = params.get("strategy", "median")
            if col and col in cleaned_df.columns:
                if strategy == "median":
                    num = pd.to_numeric(cleaned_df[col], errors="coerce")
                    fill_val = num.median() if not num.dropna().empty else 0
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                elif strategy == "mean":
                    num = pd.to_numeric(cleaned_df[col], errors="coerce")
                    fill_val = num.mean() if not num.dropna().empty else 0
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                elif strategy == "mode":
                    mode_res = cleaned_df[col].mode()
                    fill_val = mode_res.iloc[0] if not mode_res.empty else "Unknown"
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                else:
                    fill_val = params.get("value", "Unknown")
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
        elif action == "trim_whitespace":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                non_null_mask = cleaned_df[col].notna()
                cleaned_df.loc[non_null_mask, col] = (
                    cleaned_df.loc[non_null_mask, col]
                    .astype(str)
                    .str.strip()
                    .str.replace(r"\s+", " ", regex=True)
                )
        elif action == "normalize_case":
            col = params.get("column")
            case = params.get("case", "title")
            if col and col in cleaned_df.columns:
                non_null_mask = cleaned_df[col].notna()
                # When a style is applied, also strip leading/trailing whitespace and collapse internal double-spaces
                trimmed = (
                    cleaned_df.loc[non_null_mask, col]
                    .astype(str)
                    .str.strip()
                    .str.replace(r"\s+", " ", regex=True)
                )
                if case == "title":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.title()
                elif case == "lower":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.lower()
                elif case == "upper":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.upper()
        elif action == "standardize_category":
            col = params.get("column")
            mapping = params.get("mapping", {})
            if col and col in cleaned_df.columns and mapping:
                # Phase 3: Build mapping ONCE per distinct raw value before touching any rows
                norm_map: dict[str, str] = {}
                for k, v in mapping.items():
                    k_str = str(k)
                    if k_str not in norm_map:
                        norm_map[k_str] = v
                    k_strip = k_str.strip()
                    if k_strip not in norm_map:
                        norm_map[k_strip] = v
                    k_lower = k_strip.lower()
                    if k_lower not in norm_map:
                        norm_map[k_lower] = v

                distinct_vals = cleaned_df[col].dropna().unique()
                lookup: dict[Any, Any] = {}
                for val in distinct_vals:
                    v_str = str(val)
                    v_strip = v_str.strip()
                    v_lower = v_strip.lower()
                    if v_str in mapping:
                        lookup[val] = mapping[v_str]
                    elif v_strip in mapping:
                        lookup[val] = mapping[v_strip]
                    elif v_str in norm_map:
                        lookup[val] = norm_map[v_str]
                    elif v_strip in norm_map:
                        lookup[val] = norm_map[v_strip]
                    elif v_lower in norm_map:
                        lookup[val] = norm_map[v_lower]

                if lookup:
                    cleaned_df[col] = cleaned_df[col].replace(lookup)
        elif action == "standardize_date_format":
            col = params.get("column")
            value_map = params.get("value_map") or {}
            if col and col in cleaned_df.columns and value_map:
                cleaned_df[col] = cleaned_df[col].replace(value_map)
                resilient_map = {}
                for k, v in value_map.items():
                    k_str = str(k)
                    resilient_map[k_str] = v
                    resilient_map[k_str.strip()] = v
                cleaned_df[col] = cleaned_df[col].replace(resilient_map)
        elif action == "coerce_numeric":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                # Phase 1: Explicitly exclude phone columns from coerce_numeric
                col_lower = col.lower()
                is_phone = (col_lower in ("phone", "mobile", "contact_no")) or ("phone" in col_lower)
                if not is_phone:
                    # Phase 4: Strip commas and currency symbols before pd.to_numeric
                    cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                    cleaned_df[col] = pd.to_numeric(cleaned_series, errors="coerce")
        elif action == "flag_negative_values":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                cleaned_df[f"{col}_flag_negative"] = num < 0
        elif action == "clip_negative_to_null":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                cleaned_df.loc[num < 0, col] = None
        elif action == "manual_value_override":
            # Phase 6: Direct cell value overrides by row index or matching raw value
            col = params.get("column")
            overrides = params.get("overrides", {})
            if col and col in cleaned_df.columns and overrides:
                for key, new_val in overrides.items():
                    set_by_idx = False
                    try:
                        idx = int(key)
                        if idx in cleaned_df.index:
                            cleaned_df.at[idx, col] = new_val
                            set_by_idx = True
                    except (ValueError, TypeError):
                        set_by_idx = False

                    if not set_by_idx:
                        mask = cleaned_df[col].astype(str) == str(key)
                        if mask.any():
                            cleaned_df.loc[mask, col] = new_val
        elif action == "remove_outliers":
            # Non-destructive: add a boolean flag column instead of deleting rows.
            col = params.get("column")
            if col and col in cleaned_df.columns:
                col_lower = col.lower()
                is_phone = (col_lower in ("phone", "mobile", "contact_no")) or ("phone" in col_lower)
                if not is_phone:
                    cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                    num = pd.to_numeric(cleaned_series, errors="coerce")
                    non_null = num.dropna()
                    if not non_null.empty:
                        q1 = non_null.quantile(0.25)
                        q3 = non_null.quantile(0.75)
                        iqr = q3 - q1
                        lower_fence = q1 - 1.5 * iqr
                        upper_fence = q3 + 1.5 * iqr
                        outlier_mask = (num < lower_fence) | (num > upper_fence)
                        cleaned_df[f"{col}_outlier"] = outlier_mask.fillna(False)

        rows_after = len(cleaned_df)
        rows_affected = max(0, rows_before - rows_after)

        log.append({
            "action": action,
            "description": description,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_affected": rows_affected,
        })

    return cleaned_df, log
