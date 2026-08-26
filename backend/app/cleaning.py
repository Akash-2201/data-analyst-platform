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
            elif inferred_type in ("numeric", "non_negative_numeric", "identifier"):
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

        # Phase 3a: Non-numeric text values in numeric-typed columns
        if inferred_type in ("numeric", "non_negative_numeric", "identifier") or pd.api.types.is_numeric_dtype(col_series):
            non_null = col_series.dropna()
            if not non_null.empty:
                coerced = pd.to_numeric(non_null, errors="coerce")
                failed_mask = non_null.notna() & coerced.isna()
                text_val_count = int(failed_mask.sum())
                if text_val_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "coerce_numeric",
                        "params": {"column": col_name},
                        "description": f"Convert {text_val_count} non-numeric text value{'s' if text_val_count > 1 else ''} in '{col_name}' to NaN",
                        "severity": "high",
                    })

        # Phase 3b: Negative values in non_negative_numeric columns
        if inferred_type == "non_negative_numeric":
            coerced_nums = pd.to_numeric(col_series, errors="coerce")
            neg_count = int((coerced_nums < 0).sum())
            if neg_count > 0:
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_negative_values",
                    "params": {"column": col_name},
                    "description": f"Flag {neg_count} negative value{'s' if neg_count > 1 else ''} in '{col_name}' (clip to null as alternative)",
                    "severity": "medium",
                })

        # Text cleanliness checks for text/categorical columns
        if inferred_type in ("text", "categorical", "email", "phone") or str(col_series.dtype) == "object":
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
                if inferred_type not in ("numeric", "non_negative_numeric", "identifier") and (
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

        # 3. Numeric outlier checks
        numeric_stats = col.get("numeric_stats")
        if numeric_stats and numeric_stats.get("outlier_count", 0) > 0:
            outlier_cnt = numeric_stats["outlier_count"]
            suggestions.append({
                "id": str(uuid.uuid4()),
                "action": "remove_outliers",
                "params": {"column": col_name, "method": "iqr"},
                "description": f"Remove {outlier_cnt} outlier row{'s' if outlier_cnt > 1 else ''} in '{col_name}' (IQR method)",
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
                if case == "title":
                    cleaned_df.loc[non_null_mask, col] = (
                        cleaned_df.loc[non_null_mask, col].astype(str).str.title()
                    )
                elif case == "lower":
                    cleaned_df.loc[non_null_mask, col] = (
                        cleaned_df.loc[non_null_mask, col].astype(str).str.lower()
                    )
                elif case == "upper":
                    cleaned_df.loc[non_null_mask, col] = (
                        cleaned_df.loc[non_null_mask, col].astype(str).str.upper()
                    )
        elif action == "standardize_category":
            col = params.get("column")
            mapping = params.get("mapping", {})
            if col and col in cleaned_df.columns and mapping:
                cleaned_df[col] = cleaned_df[col].replace(mapping)
                resilient_mapping = {}
                for k, v in mapping.items():
                    k_str = str(k)
                    resilient_mapping[k_str] = v
                    resilient_mapping[k_str.strip()] = v
                    resilient_mapping[k_str.lower()] = v
                    resilient_mapping[k_str.upper()] = v
                    resilient_mapping[k_str.title()] = v
                cleaned_df[col] = cleaned_df[col].replace(resilient_mapping)
        elif action == "coerce_numeric":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors="coerce")
        elif action == "flag_negative_values":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                num = pd.to_numeric(cleaned_df[col], errors="coerce")
                cleaned_df[f"{col}_flag_negative"] = num < 0
        elif action == "clip_negative_to_null":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                num = pd.to_numeric(cleaned_df[col], errors="coerce")
                cleaned_df.loc[num < 0, col] = None
        elif action == "remove_outliers":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                num = pd.to_numeric(cleaned_df[col], errors="coerce")
                non_null = num.dropna()
                if not non_null.empty:
                    q1 = non_null.quantile(0.25)
                    q3 = non_null.quantile(0.75)
                    iqr = q3 - q1
                    lower_fence = q1 - 1.5 * iqr
                    upper_fence = q3 + 1.5 * iqr
                    outlier_mask = (num < lower_fence) | (num > upper_fence)
                    cleaned_df = cleaned_df[~outlier_mask]

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
