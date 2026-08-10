"""
Profiling engine.

Takes a pandas DataFrame and produces a JSON-serializable report describing
the shape and quality of the data: missing values, types, duplicates,
cardinality, and simple outlier detection for numeric columns.

This is intentionally rule-based (no LLM calls) so it's fast, deterministic,
and free to run on every upload.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _safe(value: Any) -> Any:
    """Convert numpy/pandas scalars into plain JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _infer_semantic_type(series: pd.Series, dtype_str: str) -> str:
    """A light heuristic on top of the pandas dtype, useful before the user
    tells us what a column actually means."""
    name = series.name.lower() if isinstance(series.name, str) else ""

    if "date" in dtype_str or "datetime" in dtype_str:
        return "datetime"
    if dtype_str.startswith(("int", "float")):
        if any(key in name for key in ("id", "code", "zip", "postal")):
            return "identifier"
        return "numeric"
    if dtype_str == "bool":
        return "boolean"

    # object / string column heuristics
    non_null = series.dropna()
    if non_null.empty:
        return "text"
    sample = non_null.astype(str).head(200)
    if any(key in name for key in ("email",)):
        return "email"
    if any(key in name for key in ("phone", "mobile", "contact_no")):
        return "phone"
    if sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.5:
        return "datetime"
    unique_ratio = non_null.nunique() / max(len(non_null), 1)
    if unique_ratio < 0.05 and non_null.nunique() < 50:
        return "categorical"
    return "text"


def _numeric_stats(series: pd.Series) -> dict[str, Any] | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = numeric[(numeric < lower_fence) | (numeric > upper_fence)]

    return {
        "min": _safe(numeric.min()),
        "max": _safe(numeric.max()),
        "mean": _safe(round(numeric.mean(), 4)),
        "median": _safe(numeric.median()),
        "std": _safe(round(numeric.std(), 4)) if len(numeric) > 1 else 0,
        "outlier_count": int(outliers.shape[0]),
        "outlier_pct": _safe(round(100 * outliers.shape[0] / len(numeric), 2)),
    }


def profile_column(series: pd.Series) -> dict[str, Any]:
    total = len(series)
    missing = int(series.isna().sum())
    dtype_str = str(series.dtype)
    non_null = series.dropna()

    column_report: dict[str, Any] = {
        "name": series.name,
        "dtype": dtype_str,
        "inferred_type": _infer_semantic_type(series, dtype_str),
        "missing_count": missing,
        "missing_pct": _safe(round(100 * missing / total, 2)) if total else 0,
        "unique_count": int(non_null.nunique()),
        "unique_pct": _safe(round(100 * non_null.nunique() / total, 2)) if total else 0,
        "sample_values": [_safe(v) for v in non_null.astype(str).unique()[:5]],
    }

    numeric_stats = _numeric_stats(series)
    if numeric_stats:
        column_report["numeric_stats"] = numeric_stats

    return column_report


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    duplicate_rows = int(df.duplicated().sum())

    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "duplicate_row_count": duplicate_rows,
        "duplicate_row_pct": _safe(round(100 * duplicate_rows / len(df), 2)) if len(df) else 0,
        "columns": [profile_column(df[col]) for col in df.columns],
    }
