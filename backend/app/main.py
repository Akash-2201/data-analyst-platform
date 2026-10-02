"""
API entrypoint.

Upload CSV/XLSX datasets, generate profiling reports, suggest rule-based
cleaning steps, persist pipeline configuration, apply cleaning transformations,
download cleaned CSV/Excel results, and handle chat/settings endpoints.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
import uuid
from typing import Any

from dotenv import load_dotenv
from google import genai
import numpy as np
import pandas as pd
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Response, UploadFile

from app.auth import AuthenticatedUser, get_current_user
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_suggestions import generate_ai_suggestions, ALLOWED_OPERATIONS
from app.gemini_config import GEMINI_MODELS_TO_TRY
from app.cleaning import apply_pipeline
from app.database import Base, engine, get_db
from app.models import Dataset, PipelineStep
from app.profiling import profile_dataframe
from app.storage import get_storage

logger = logging.getLogger(__name__)

# Load environment variables from .env file if present
load_dotenv()
load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI(title="Datalyst API", version="0.1.0")

# CORS — configurable via ALLOWED_ORIGINS env var (comma-separated).
# Defaults to both common Vite dev ports so a port shift doesn't silently break the app.
_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory dataset store, keyed by dataset_id. Fine for a single-user local MVP.
DATASETS: dict[str, pd.DataFrame] = {}


def _verify_ownership(dataset: "Dataset", user: AuthenticatedUser) -> None:
    """Raise 403 if the dataset does not belong to the authenticated user."""
    if dataset.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied: you do not own this dataset.")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def _parse_dataframe(filename: str, raw: bytes) -> pd.DataFrame:
    """Parse CSV or Excel raw bytes into a pandas DataFrame."""
    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            return pd.read_csv(io.BytesIO(raw), keep_default_na=False, na_values=[""])
        if lower.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(raw), keep_default_na=False, na_values=[""])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}") from exc

    raise HTTPException(status_code=400, detail="Only .csv, .xlsx, and .xls files are supported.")


class StepSchema(BaseModel):
    action: str
    params: dict[str, Any] | None = None
    description: str
    severity: str


class ChatRequestSchema(BaseModel):
    message: str
    dataset_id: str | None = None
    chart_context: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/datasets")
def list_datasets(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all datasets owned by the authenticated user."""
    datasets = (
        db.query(Dataset)
        .filter(Dataset.user_id == user.id)
        .order_by(Dataset.created_at.desc())
        .all()
    )
    return [
        {
            "id": ds.id,
            "filename": ds.filename,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
            "has_cleaned": ds.cleaned_storage_path is not None,
            "row_count": ds.profile_json.get("row_count") if ds.profile_json else None,
            "column_count": ds.profile_json.get("column_count") if ds.profile_json else None,
        }
        for ds in datasets
    ]


@app.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    filename = file.filename or "upload.csv"
    df = _parse_dataframe(filename, raw)
    if df.empty:
        raise HTTPException(status_code=400, detail="No rows found in the uploaded file.")

    dataset_id = str(uuid.uuid4())
    DATASETS[dataset_id] = df

    report = profile_dataframe(df)

    storage = get_storage()
    raw_path = storage.save(f"{dataset_id}_raw_{filename}", raw)

    dataset = Dataset(
        id=dataset_id,
        user_id=user.id,
        filename=filename,
        raw_storage_path=raw_path,
        profile_json=report,
    )
    db.add(dataset)
    db.commit()

    return {"dataset_id": dataset_id, "filename": filename, **report}


@app.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    df = DATASETS.get(dataset_id)
    if df is None:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        _verify_ownership(dataset, user)
        storage = get_storage()
        try:
            raw_bytes = storage.load(dataset.raw_storage_path)
            df = _parse_dataframe(dataset.filename, raw_bytes)
            DATASETS[dataset_id] = df
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not load dataset: {exc}") from exc

    return profile_dataframe(df)


@app.get("/datasets/{dataset_id}/suggestions")
def get_suggestions(dataset_id: str, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    df = DATASETS.get(dataset_id)
    if df is None:
        profile = get_profile(dataset_id, db, user)
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        storage = get_storage()
        raw_bytes = storage.load(dataset.raw_storage_path)
        df = _parse_dataframe(dataset.filename, raw_bytes)
        DATASETS[dataset_id] = df
    else:
        profile = profile_dataframe(df)

    result = generate_ai_suggestions(df, profile)
    return result


@app.get("/datasets/{dataset_id}/validation")
def get_validation(dataset_id: str, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    """Run the centralised 47-type validation rules engine on every column."""
    from app.validation_rules import validate_column, detect_semantic_type, detect_dataset_level_issues

    df = DATASETS.get(dataset_id)
    if df is None:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        _verify_ownership(dataset, user)
        storage = get_storage()
        raw_bytes = storage.load(dataset.raw_storage_path)
        df = _parse_dataframe(dataset.filename, raw_bytes)
        DATASETS[dataset_id] = df

    column_results = []
    for col in df.columns:
        sem_type = detect_semantic_type(df[col], col)
        result = validate_column(df[col], col, semantic_type=sem_type)
        column_results.append({
            "column": result.column_name,
            "semantic_type": result.semantic_type,
            "issue_count": len(result.issues),
            "issues": result.to_flagged_values(),
        })

    dataset_issues = [i.to_dict() for i in detect_dataset_level_issues(df)]

    return {
        "column_results": column_results,
        "dataset_issues": dataset_issues,
    }


@app.get("/datasets/{dataset_id}/cross-column-validation")
def get_cross_column_validation(dataset_id: str, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    """Run cross-column validation rules (DOB↔Age, Start↔End, Qty×Price, etc.)."""
    from app.validation_rules import run_all_cross_column_validations

    df = DATASETS.get(dataset_id)
    if df is None:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        _verify_ownership(dataset, user)
        storage = get_storage()
        raw_bytes = storage.load(dataset.raw_storage_path)
        df = _parse_dataframe(dataset.filename, raw_bytes)
        DATASETS[dataset_id] = df

    issues = run_all_cross_column_validations(df)
    return {
        "cross_column_issues": [i.to_dict() for i in issues],
        "total_issues": len(issues),
    }


@app.post("/datasets/{dataset_id}/pipeline")
def save_pipeline(
    dataset_id: str, steps: list[StepSchema] | dict[str, Any] = Body(...), db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    _verify_ownership(dataset, user)

    if isinstance(steps, dict):
        raw_list = steps.get("suggestions") or steps.get("steps") or []
        step_items = [StepSchema(**s) for s in raw_list]
    else:
        step_items = steps

    db.query(PipelineStep).filter(PipelineStep.dataset_id == dataset_id).delete()

    created_steps = []
    for idx, st in enumerate(step_items):
        step_obj = PipelineStep(
            dataset_id=dataset_id,
            order=idx,
            action=st.action,
            params=st.params,
            description=st.description,
            severity=st.severity,
        )
        db.add(step_obj)
        created_steps.append(step_obj)

    db.commit()

    return [
        {
            "id": st.id,
            "order": st.order,
            "action": st.action,
            "params": st.params,
            "description": st.description,
            "severity": st.severity,
        }
        for st in created_steps
    ]


@app.get("/datasets/{dataset_id}/pipeline")
def get_pipeline(dataset_id: str, db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    _verify_ownership(dataset, user)

    steps = (
        db.query(PipelineStep)
        .filter(PipelineStep.dataset_id == dataset_id)
        .order_by(PipelineStep.order.asc())
        .all()
    )

    return [
        {
            "id": st.id,
            "order": st.order,
            "action": st.action,
            "params": st.params,
            "description": st.description,
            "severity": st.severity,
        }
        for st in steps
    ]


@app.post("/datasets/{dataset_id}/apply")
def apply_cleaning_pipeline(
    dataset_id: str, db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    _verify_ownership(dataset, user)

    steps = (
        db.query(PipelineStep)
        .filter(PipelineStep.dataset_id == dataset_id)
        .order_by(PipelineStep.order.asc())
        .all()
    )
    if not steps:
        raise HTTPException(status_code=400, detail="No cleaning pipeline steps found for this dataset.")

    storage = get_storage()
    try:
        raw_bytes = storage.load(dataset.raw_storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Raw dataset file not found in storage.")

    df = _parse_dataframe(dataset.filename, raw_bytes)
    cleaned_df, log = apply_pipeline(df, steps)

    cleaned_profile = profile_dataframe(cleaned_df)
    csv_bytes = cleaned_df.to_csv(index=False).encode("utf-8")
    cleaned_path = storage.save(f"{dataset_id}_cleaned.csv", csv_bytes)

    dataset.cleaned_storage_path = cleaned_path
    dataset.cleaned_profile_json = cleaned_profile
    db.commit()

    DATASETS[dataset_id] = cleaned_df

    return {
        "log": log,
        "cleaned_profile": cleaned_profile,
        "original_row_count": len(df),
        "cleaned_row_count": len(cleaned_df),
    }


@app.post("/datasets/{dataset_id}/preview")
def preview_cleaning_pipeline(
    dataset_id: str, steps: list[StepSchema] | dict[str, Any] = Body(...), db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Dry-run the given steps in memory (no save, no DB write).

    Returns per-column value-count before/after for every column touched by the
    operations, plus overall row-count change.  The frontend shows this to the
    user before they click "Confirm & Apply".
    """
    # Load the dataframe (prefer in-memory, else reload from storage)
    df = DATASETS.get(dataset_id)
    if df is None:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        _verify_ownership(dataset, user)
        storage = get_storage()
        try:
            raw_bytes = storage.load(dataset.raw_storage_path)
            df = _parse_dataframe(dataset.filename, raw_bytes)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Raw dataset file not found in storage.")

    if isinstance(steps, dict):
        raw_list = steps.get("suggestions") or steps.get("steps") or []
        step_items = [StepSchema(**s) for s in raw_list]
    else:
        step_items = steps

    if not step_items:
        raise HTTPException(status_code=400, detail="No steps provided for preview.")

    # Figure out which columns will be affected, for before-snapshot
    affected_columns: set[str] = set()
    for step in step_items:
        col = (step.params or {}).get("column")
        if col and col in df.columns:
            affected_columns.add(col)

    # Snapshot value counts BEFORE (for categorical/object columns) and row count
    before_counts: dict[str, dict[str, int]] = {}
    for col in affected_columns:
        if df[col].dtype == object or str(df[col].dtype) == "object":
            before_counts[col] = df[col].fillna("(missing)").value_counts().to_dict()
            before_counts[col] = {str(k): int(v) for k, v in before_counts[col].items()}

    original_row_count = len(df)

    # Run the pipeline in memory (apply_pipeline returns a copy)
    step_dicts = [
        {"action": s.action, "params": s.params or {}, "description": s.description, "severity": s.severity}
        for s in steps
    ]
    cleaned_df, log = apply_pipeline(df, step_dicts)
    cleaned_row_count = len(cleaned_df)

    # Snapshot value counts AFTER for the same columns (if still present)
    column_diffs: list[dict[str, Any]] = []

    # Rows-level change (always shown)
    if cleaned_row_count != original_row_count:
        column_diffs.append({
            "column": "(row count)",
            "before": {"rows": original_row_count},
            "after": {"rows": cleaned_row_count},
            "rows_removed": original_row_count - cleaned_row_count,
            "summary": f"{original_row_count} → {cleaned_row_count} rows ({original_row_count - cleaned_row_count} removed)",
        })

    for col in sorted(affected_columns):
        if col not in cleaned_df.columns:
            # Column was dropped
            before_vc = before_counts.get(col, {})
            column_diffs.append({
                "column": col,
                "before": before_vc,
                "after": {},
                "note": "column dropped",
                "summary": f"Column '{col}' dropped entirely",
            })
            continue

        after_series = cleaned_df[col]
        if after_series.dtype == object or str(after_series.dtype) == "object":
            after_vc = after_series.fillna("(missing)").value_counts().to_dict()
            after_vc = {str(k): int(v) for k, v in after_vc.items()}
        else:
            # Numeric column: show null count before/after instead of value counts
            before_nulls = int(df[col].isna().sum()) if col in df.columns else 0
            after_nulls = int(after_series.isna().sum())
            after_vc = {"(null count)": after_nulls}
            before_counts[col] = {"(null count)": before_nulls}

        before = before_counts.get(col, {})
        if before != after_vc:  # only include columns that actually changed
            # Build a human-readable summary of the change
            before_distinct = len(before)
            after_distinct = len(after_vc)
            total_remapped = sum(
                before.get(k, 0) for k in before if k not in after_vc
            )
            parts = []
            if before_distinct != after_distinct:
                parts.append(f"{before_distinct} distinct → {after_distinct} distinct values")
            if total_remapped > 0:
                parts.append(f"{total_remapped} rows remapped")
            summary = "; ".join(parts) if parts else "values changed"

            column_diffs.append({
                "column": col,
                "before": before,
                "after": after_vc,
                "summary": summary,
            })

    return {
        "original_row_count": original_row_count,
        "cleaned_row_count": cleaned_row_count,
        "column_diffs": column_diffs,
        "step_log": log,
    }


@app.get("/datasets/{dataset_id}/download-cleaned")
def download_cleaned_dataset(
    dataset_id: str,
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset or not dataset.cleaned_storage_path:
        raise HTTPException(
            status_code=404, detail="Cleaned dataset not available. Apply cleaning first."
        )
    _verify_ownership(dataset, user)

    storage = get_storage()
    try:
        csv_bytes = storage.load(dataset.cleaned_storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Cleaned file not found in storage.")

    # Base stem name from original dataset filename
    orig_filename = dataset.filename or "dataset.csv"
    stem = Path(orig_filename).stem or "dataset"

    fmt = format.lower()
    if fmt == "xlsx":
        from openpyxl.utils import get_column_letter

        # Parse CSV bytes to DataFrame — use dtype=str so pd.read_csv never
        # silently coerces all-digit phone numbers (or other text columns) to
        # int64/float64.  We'll convert genuinely numeric columns back below.
        cleaned_df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)

        # Restore numeric dtypes for columns that are genuinely numeric,
        # while leaving phone/email/text columns as str.
        _PHONE_KEYWORDS = ("phone", "mobile", "contact")
        _EMAIL_KEYWORDS = ("email", "e-mail", "e_mail")
        text_format_col_indices: list[int] = []  # 1-based indices for openpyxl

        for col_idx_0, col_name in enumerate(cleaned_df.columns):
            col_lower = str(col_name).lower()
            is_phone = any(kw in col_lower for kw in _PHONE_KEYWORDS)
            is_email = any(kw in col_lower for kw in _EMAIL_KEYWORDS)

            if is_phone or is_email:
                # Keep as string; replace literal "nan" with empty string
                cleaned_df[col_name] = cleaned_df[col_name].replace("nan", "").replace("", "")
                text_format_col_indices.append(col_idx_0 + 1)  # openpyxl is 1-based
                logger.info(
                    "Column '%s' (idx %d) forced to text dtype for Excel export",
                    col_name, col_idx_0,
                )
            else:
                # Try to restore numeric dtype for genuinely numeric columns
                coerced = pd.to_numeric(cleaned_df[col_name], errors="coerce")
                # If ≥50% of non-empty values are valid numbers, treat as numeric
                non_empty = cleaned_df[col_name][cleaned_df[col_name] != ""]
                if len(non_empty) > 0 and coerced.notna().sum() >= len(non_empty) * 0.5:
                    cleaned_df[col_name] = coerced

        output = io.BytesIO()
        sheet_name = "Cleaned Data"
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            cleaned_df.to_excel(writer, index=False, sheet_name=sheet_name)
            ws = writer.sheets[sheet_name]

            try:
                ws.views.sheetView[0].showGridLines = True
            except Exception:  # noqa: BLE001
                pass

            # Force text format (@) on phone/email columns so Excel never
            # renders all-digit strings as numbers / scientific notation.
            try:
                for col_idx_1 in text_format_col_indices:
                    col_letter = get_column_letter(col_idx_1)
                    for row in range(1, ws.max_row + 1):
                        cell = ws[f"{col_letter}{row}"]
                        cell.number_format = "@"
                        # Re-set the value as string to clear any cached numeric type
                        if row > 1 and cell.value is not None:
                            cell.value = str(cell.value)
                logger.info(
                    "Text format (@) applied to %d column(s): indices %s",
                    len(text_format_col_indices), text_format_col_indices,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Text column formatting failed: %s", exc)

            # Auto-size each column's width based on content (sample first 500 rows for perf).
            # Wrapped in try/except so column-width failures never prevent the download.
            try:
                # Explicitly clear any default column width that could override per-column widths
                ws.sheet_format.defaultColWidth = None

                sample_df = cleaned_df.head(500)
                for col_idx, col_name in enumerate(cleaned_df.columns, start=1):
                    col_letter = get_column_letter(col_idx)
                    header_len = len(str(col_name))
                    # Cast every value to str; skip NaN/None via dropna()
                    if not sample_df.empty:
                        val_lens = [
                            len(str(v)) for v in sample_df[col_name].dropna()
                        ]
                    else:
                        val_lens = []
                    max_len = max([header_len] + val_lens) if val_lens else header_len
                    # Cap at 60 to avoid absurdly wide columns from long text values
                    # Min of 14 ensures narrow columns are still comfortably readable
                    computed_width = min(max(max_len + 3, 14), 60)
                    ws.column_dimensions[col_letter].width = computed_width
                logger.info(
                    "Column widths auto-sized for %d columns (sample size: %d rows)",
                    len(cleaned_df.columns), len(sample_df),
                )
            except Exception as exc:  # noqa: BLE001
                # If column-width auto-sizing fails for any reason, the Excel file
                # is still valid — just with default column widths.
                logger.warning("Column width auto-sizing failed: %s", exc)

            # Final: ensure worksheet has no protection and is completely editable.
            # Done AFTER all formatting to guarantee nothing re-enables protection.
            ws.protection.disable()
            ws.protection.sheet = False


        content = output.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{stem}_cleaned.xlsx"
    else:
        content = csv_bytes
        media_type = "text/csv"
        filename = f"{stem}_cleaned.csv"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@app.get("/datasets/{dataset_id}/chart-data")
def get_chart_data(
    dataset_id: str,
    chart_type: str = Query("bar"),
    x: str | None = Query(None, description="Column name for X axis / grouping"),
    y: str | None = Query(None, description="Column name for Y axis (optional for count-based charts)"),
    agg: str = Query("count", regex="^(count|sum|mean)$"),
    use_cleaned: bool = Query(True, description="Prefer cleaned dataset if available"),
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return chart-ready aggregated data for the given dataset.

    Never modifies state — read-only endpoint.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    _verify_ownership(dataset, user)

    # --- Load the appropriate dataframe ---
    storage = get_storage()
    df: pd.DataFrame | None = None

    # Try cleaned version first if requested and available
    if use_cleaned and dataset.cleaned_storage_path:
        try:
            csv_bytes = storage.load(dataset.cleaned_storage_path)
            df = pd.read_csv(io.BytesIO(csv_bytes))
        except Exception:  # noqa: BLE001
            df = None  # fall through to raw

    if df is None:
        # Fall back to raw
        df = DATASETS.get(dataset_id)
        if df is None and dataset.raw_storage_path:
            try:
                raw_bytes = storage.load(dataset.raw_storage_path)
                df = _parse_dataframe(dataset.filename, raw_bytes)
                DATASETS[dataset_id] = df
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"Could not load dataset: {exc}") from exc

    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found in storage.")

    # If x is not supplied and dataset has columns, pick the first column
    if (not x or x not in df.columns) and len(df.columns) > 0 and chart_type != "heatmap":
        if not x:
            x = list(df.columns)[0]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Column '{x}' not found. Available: {list(df.columns)}",
            )

    if y is not None and y not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Column '{y}' not found. Available: {list(df.columns)}",
        )

    # --- Aggregate ---
    MAX_GROUPS = 50

    # -----------------------------------------------------------------------
    # Correlation Heatmap
    # -----------------------------------------------------------------------
    if chart_type == "heatmap":
        num_cols = []
        for c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce")
            if s.dropna().count() >= 2:
                num_cols.append(c)

        if len(num_cols) < 2:
            raise HTTPException(
                status_code=400,
                detail="Correlation Heatmap requires at least 2 numeric columns in the dataset.",
            )

        num_cols = num_cols[:12]
        sub_df = df[num_cols].apply(pd.to_numeric, errors="coerce")
        corr_df = sub_df.corr().round(3).fillna(0.0)

        matrix = corr_df.values.tolist()
        cols = list(corr_df.columns)
        return {
            "chart_type": "heatmap",
            "cols": cols,
            "matrix": matrix,
            "x_label": "Correlation Matrix",
            "y_label": "",
            "row_count": len(df),
            "group_count": len(cols),
        }

    # -----------------------------------------------------------------------
    # Histogram
    # -----------------------------------------------------------------------
    if chart_type == "histogram":
        col_data = pd.to_numeric(df[x], errors="coerce").dropna()
        if col_data.empty:
            raise HTTPException(status_code=400, detail=f"Column '{x}' has no numeric values for histogram.")
        num_bins = min(20, max(5, int(col_data.nunique())))
        counts, bin_edges = np.histogram(col_data, bins=num_bins)
        labels = [f"{bin_edges[i]:.3g}\u2013{bin_edges[i+1]:.3g}" for i in range(len(counts))]
        values = [int(c) for c in counts]
        return {
            "labels": labels, "values": values, "chart_type": chart_type,
            "x_label": x, "y_label": "Count",
            "row_count": len(df), "group_count": len(labels),
        }

    # -----------------------------------------------------------------------
    # Box Plot
    # -----------------------------------------------------------------------
    if chart_type == "box_plot":
        col_data = pd.to_numeric(df[x], errors="coerce").dropna()
        if col_data.empty:
            raise HTTPException(status_code=400, detail=f"Column '{x}' has no numeric values for box plot.")
        if y and y in df.columns:
            groups_unique = df[y].dropna().astype(str).unique()[:MAX_GROUPS]
            labels_bp: list[str] = [str(g) for g in groups_unique]
            box_stats: list[dict] = []
            for g in groups_unique:
                mask = df[y].astype(str) == str(g)
                col_g = pd.to_numeric(df.loc[mask, x], errors="coerce").dropna()
                if col_g.empty:
                    continue
                q1, med, q3 = float(col_g.quantile(0.25)), float(col_g.quantile(0.5)), float(col_g.quantile(0.75))
                box_stats.append({"min": float(col_g.min()), "q1": q1, "median": med, "q3": q3, "max": float(col_g.max()), "iqr": round(q3 - q1, 4)})
        else:
            q1, med, q3 = float(col_data.quantile(0.25)), float(col_data.quantile(0.5)), float(col_data.quantile(0.75))
            labels_bp = [x]
            box_stats = [{"min": float(col_data.min()), "q1": q1, "median": med, "q3": q3, "max": float(col_data.max()), "iqr": round(q3 - q1, 4)}]
        return {
            "labels": labels_bp, "box_stats": box_stats,
            "values": [s["median"] for s in box_stats],
            "chart_type": chart_type,
            "x_label": (y if (y and y in df.columns) else x), "y_label": x,
            "row_count": len(df), "group_count": len(labels_bp),
        }

    # -----------------------------------------------------------------------
    # Stacked Bar & 100% Stacked Bar
    # -----------------------------------------------------------------------
    if chart_type in ("stacked_bar", "stacked_bar_100"):
        if not y or y not in df.columns:
            raise HTTPException(status_code=400, detail=f"{chart_type} requires a 'y' column for the stack dimension.")
        try:
            x_str = df[x].astype(str)
            y_str = df[y].astype(str)
            grouped_df = pd.DataFrame({"_x": x_str, "_y": y_str}).groupby(["_x", "_y"]).size().reset_index(name="count")
            x_vals = list(grouped_df["_x"].unique()[:MAX_GROUPS])
            y_vals = list(grouped_df["_y"].unique()[:MAX_GROUPS])

            totals_per_x = {}
            for xv in x_vals:
                totals_per_x[str(xv)] = int(grouped_df[grouped_df["_x"] == xv]["count"].sum())

            series: list[dict] = []
            raw_series: list[dict] = []
            for y_val in y_vals:
                sub = grouped_df[grouped_df["_y"] == y_val].set_index("_x")["count"]
                data_points = []
                raw_points = []
                for xv in x_vals:
                    raw_c = int(sub.get(str(xv), 0))
                    raw_points.append(raw_c)
                    if chart_type == "stacked_bar_100":
                        tot = totals_per_x.get(str(xv), 0)
                        pct = round((raw_c / tot * 100.0), 1) if tot > 0 else 0.0
                        data_points.append(pct)
                    else:
                        data_points.append(raw_c)
                series.append({"name": str(y_val), "data": data_points})
                raw_series.append({"name": str(y_val), "data": raw_points})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Stacked bar failed: {exc}") from exc
        return {
            "labels": [str(v) for v in x_vals], "series": series, "raw_series": raw_series, "values": [],
            "chart_type": chart_type, "x_label": x, "y_label": ("% Share" if chart_type == "stacked_bar_100" else y),
            "row_count": len(df), "group_count": len(x_vals),
        }

    # -----------------------------------------------------------------------
    # Waterfall Chart
    # -----------------------------------------------------------------------
    if chart_type == "waterfall":
        if y and y in df.columns:
            num_col = y
            cat_col = x
        else:
            num_col = x
            cat_col = None

        delta_series = pd.to_numeric(df[num_col], errors="coerce")
        if delta_series.dropna().empty:
            raise HTTPException(
                status_code=400,
                detail=f"Column '{num_col}' has no numeric values for Waterfall calculation.",
            )

        if cat_col:
            sub = df[[cat_col, num_col]].copy()
            sub["_num"] = delta_series
            wf_grouped = sub.dropna(subset=["_num"]).groupby(cat_col)["_num"].sum().head(20)
            step_labels = [str(k) for k in wf_grouped.index]
            step_deltas = [round(float(v), 2) for v in wf_grouped.values]
        else:
            valid_items = delta_series.dropna().head(20)
            step_labels = [f"Item {i+1}" for i in range(len(valid_items))]
            step_deltas = [round(float(v), 2) for v in valid_items.values]

        cumulative = 0.0
        items = []
        for lbl, delta in zip(step_labels, step_deltas):
            start = cumulative
            end = cumulative + delta
            cumulative = end
            items.append({
                "label": lbl,
                "delta": delta,
                "start": round(start, 2),
                "end": round(end, 2),
                "base": round(min(start, end), 2),
                "span": round(abs(delta), 2),
                "is_positive": delta >= 0,
                "is_total": False,
            })

        items.append({
            "label": "Total",
            "delta": round(cumulative, 2),
            "start": 0.0,
            "end": round(cumulative, 2),
            "base": 0.0 if cumulative >= 0 else round(cumulative, 2),
            "span": round(abs(cumulative), 2),
            "is_positive": cumulative >= 0,
            "is_total": True,
        })

        return {
            "chart_type": "waterfall",
            "items": items,
            "labels": [it["label"] for it in items],
            "values": [it["delta"] for it in items],
            "x_label": cat_col or "Item",
            "y_label": f"Net {num_col}",
            "row_count": len(df),
            "group_count": len(items),
        }

    # -----------------------------------------------------------------------
    # KPI / Card
    # -----------------------------------------------------------------------
    if chart_type == "kpi":
        target_col = y if (y and y in df.columns) else x
        num_s = pd.to_numeric(df[target_col], errors="coerce")
        is_numeric = num_s.dropna().count() > 0
        total_rows = len(df)
        non_null_count = int(df[target_col].notna().sum())
        unique_count = int(df[target_col].nunique())

        if is_numeric:
            s = num_s.dropna()
            metric_agg = agg if agg in ("sum", "mean") else "mean"
            stats = {
                "sum": round(float(s.sum()), 2),
                "mean": round(float(s.mean()), 2),
                "min": round(float(s.min()), 2),
                "max": round(float(s.max()), 2),
                "median": round(float(s.median()), 2),
                "count": non_null_count,
                "unique": unique_count,
            }
            display_val = stats[metric_agg]
        else:
            metric_agg = "count"
            display_val = non_null_count
            stats = {
                "count": non_null_count,
                "unique": unique_count,
                "total_rows": total_rows,
            }

        return {
            "chart_type": "kpi",
            "column": target_col,
            "is_numeric": is_numeric,
            "metric": metric_agg,
            "value": display_val,
            "stats": stats,
            "x_label": target_col,
            "y_label": metric_agg.upper(),
            "row_count": total_rows,
            "group_count": 1,
        }

    # -----------------------------------------------------------------------
    # Forecasting Chart Types
    # -----------------------------------------------------------------------
    if chart_type in ("forecast_line", "forecast_ci", "forecast_actual", "forecast_residual"):
        x_dates = pd.to_datetime(df[x], errors="coerce")
        y_nums = pd.to_numeric(df[y], errors="coerce") if (y and y in df.columns) else None

        # If x is numeric and y is date, gracefully invert
        if (x_dates.dropna().count() < 3) and (y and y in df.columns):
            y_dates = pd.to_datetime(df[y], errors="coerce")
            x_nums = pd.to_numeric(df[x], errors="coerce")
            if y_dates.dropna().count() >= 3 and x_nums.dropna().count() >= 3:
                x, y = y, x
                x_dates, y_nums = y_dates, x_nums

        if x_dates.dropna().count() < 3:
            raise HTTPException(
                status_code=400,
                detail=f"Forecasting requires a Date/Time column for X. Column '{x}' has fewer than 3 valid dates.",
            )
        if y is None or y not in df.columns or y_nums is None or y_nums.dropna().count() < 3:
            raise HTTPException(
                status_code=400,
                detail="Forecasting requires a Numeric column for Y. Please select a numeric Y column.",
            )

        valid_mask = x_dates.notna() & y_nums.notna()
        ts_df = pd.DataFrame({"date": x_dates[valid_mask], "val": y_nums[valid_mask]}).sort_values("date")
        ts_df = ts_df.groupby("date", as_index=False)["val"].mean()

        if len(ts_df) < 3:
            raise HTTPException(
                status_code=400,
                detail="Not enough distinct historical date points (minimum 3 required) for trend projection.",
            )

        if len(ts_df) > 60:
            ts_df = ts_df.tail(60).reset_index(drop=True)

        n_hist = len(ts_df)
        t = np.arange(n_hist)
        vals = ts_df["val"].values.astype(float)

        poly = np.polyfit(t, vals, 1)
        slope, intercept = float(poly[0]), float(poly[1])
        fitted_hist = slope * t + intercept
        residuals = vals - fitted_hist

        dof = max(1, n_hist - 2)
        se = float(np.sqrt(np.sum(residuals**2) / dof))

        ss_tot = float(np.sum((vals - np.mean(vals))**2))
        ss_res = float(np.sum(residuals**2))
        r2 = round(float(1.0 - (ss_res / ss_tot)), 3) if ss_tot > 0 else 0.0

        n_proj = min(12, max(5, int(n_hist * 0.25)))
        time_diffs = ts_df["date"].diff().dropna()
        median_delta = time_diffs.median() if not time_diffs.empty else pd.Timedelta(days=1)
        if median_delta <= pd.Timedelta(0):
            median_delta = pd.Timedelta(days=1)

        last_date = ts_df["date"].iloc[-1]
        future_dates = [last_date + median_delta * (i + 1) for i in range(n_proj)]
        t_future = np.arange(n_hist, n_hist + n_proj)
        forecast_vals = slope * t_future + intercept

        t_mean = np.mean(t)
        t_ss = np.sum((t - t_mean)**2) if np.sum((t - t_mean)**2) > 0 else 1.0
        se_pred = se * np.sqrt(1.0 + (1.0 / n_hist) + ((t_future - t_mean)**2 / t_ss))
        ci_margin = 1.96 * se_pred

        history_points = []
        for i in range(n_hist):
            d_str = ts_df["date"].iloc[i].strftime("%Y-%m-%d")
            history_points.append({
                "date": d_str,
                "actual": round(float(vals[i]), 2),
                "fitted": round(float(fitted_hist[i]), 2),
                "residual": round(float(residuals[i]), 2),
            })

        future_points = []
        for i in range(n_proj):
            d_str = future_dates[i].strftime("%Y-%m-%d")
            fc = round(float(forecast_vals[i]), 2)
            margin = round(float(ci_margin[i]), 2)
            future_points.append({
                "date": d_str,
                "forecast": fc,
                "ci_lower": round(fc - margin, 2),
                "ci_upper": round(fc + margin, 2),
            })

        return {
            "chart_type": chart_type,
            "history": history_points,
            "future": future_points,
            "metrics": {
                "r2": r2,
                "slope": round(slope, 4),
                "intercept": round(intercept, 2),
                "se": round(se, 2),
                "n_hist": n_hist,
                "n_proj": n_proj,
            },
            "x_label": x,
            "y_label": y,
            "row_count": len(df),
            "group_count": n_hist + n_proj,
        }

    # -----------------------------------------------------------------------
    # Map
    # -----------------------------------------------------------------------
    if chart_type == "map":
        lat_col = None
        lon_col = None
        for c in df.columns:
            clow = c.lower()
            if clow in ("lat", "latitude", "y_coord", "lat_deg"):
                lat_col = c
            elif clow in ("lon", "lng", "long", "longitude", "x_coord", "lon_deg"):
                lon_col = c

        if x and y and y in df.columns:
            lat_col = y
            lon_col = x

        if not lat_col or not lon_col:
            return {
                "chart_type": "map",
                "deferred": True,
                "message": "Geographic Map requires explicit Latitude and Longitude columns. No coordinate columns were detected.",
                "x_label": "Longitude",
                "y_label": "Latitude",
                "points": [],
                "row_count": len(df),
                "group_count": 0,
            }

        lat_s = pd.to_numeric(df[lat_col], errors="coerce")
        lon_s = pd.to_numeric(df[lon_col], errors="coerce")
        valid_coords = lat_s.notna() & lon_s.notna()

        if valid_coords.sum() == 0:
            return {
                "chart_type": "map",
                "deferred": True,
                "message": f"Columns '{lat_col}' and '{lon_col}' contain no valid numeric latitude/longitude values.",
                "x_label": lon_col,
                "y_label": lat_col,
                "points": [],
                "row_count": len(df),
                "group_count": 0,
            }

        sub = df[valid_coords].head(200)
        points = []
        for _, row in sub.iterrows():
            points.append({
                "lat": round(float(row[lat_col]), 5),
                "lon": round(float(row[lon_col]), 5),
                "label": str(row.get(x, f"{row[lat_col]}, {row[lon_col]}")),
            })

        return {
            "chart_type": "map",
            "deferred": False,
            "points": points,
            "lat_col": lat_col,
            "lon_col": lon_col,
            "x_label": lon_col,
            "y_label": lat_col,
            "row_count": len(df),
            "group_count": len(points),
        }

    # -----------------------------------------------------------------------
    # Standard aggregation for bar / line / scatter / pie / area / funnel / treemap
    # -----------------------------------------------------------------------
    try:
        if agg == "count" or y is None:
            grouped = (
                df[x]
                .astype(str)
                .value_counts()
                .head(MAX_GROUPS)
                .reset_index()
            )
            grouped.columns = ["label", "value"]
            y_label = "Count"
        elif agg == "sum":
            grouped = (
                df.groupby(x)[y]
                .sum()
                .reset_index()
                .rename(columns={x: "label", y: "value"})
                .nlargest(MAX_GROUPS, "value")
            )
            y_label = f"Sum of {y}"
        else:  # mean
            grouped = (
                df.groupby(x)[y]
                .mean()
                .reset_index()
                .rename(columns={x: "label", y: "value"})
                .nlargest(MAX_GROUPS, "value")
            )
            y_label = f"Mean of {y}"
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Aggregation failed: {exc}") from exc

    if chart_type == "funnel":
        grouped = grouped.sort_values("value", ascending=False)

    # Convert to JSON-safe types
    labels = [str(v) for v in grouped["label"].tolist()]
    values = [
        round(float(v), 4) if v is not None and str(v) not in ("nan", "None") else 0.0
        for v in grouped["value"].tolist()
    ]

    return {
        "labels": labels,
        "values": values,
        "chart_type": chart_type,
        "x_label": x,
        "y_label": y_label if (agg != "count" and y) else "Count",
        "row_count": len(df),
        "group_count": len(labels),
    }


def _build_chat_context(message: str, dataset_id: str, db: Session) -> str:
    """Build a context string for the chat prompt.

    If the user's message mentions a specific column name (case-insensitive
    substring match), enriches the context with up to 100 raw values from
    that column plus value-counts for values appearing more than once.
    Otherwise returns a lightweight summary (row count + column names only).
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        return ""

    profile = dataset.profile_json or {}
    columns_meta = profile.get("columns", [])
    col_names = [c["name"] for c in columns_meta]
    row_count = profile.get("row_count", 0)

    # Lightweight summary — always included
    base_ctx = (
        f"The user's dataset has {row_count} rows and these columns: {col_names}. "
    )

    # Check whether the message mentions any specific column (simple substring check)
    msg_lower = message.lower()

    # Visualization awareness: when user asks about charts/trends include chartable column info
    _VIZ_KW = ("chart", "graph", "plot", "trend", "distribution", "histogram",
               "average", "highest", "lowest", "visualiz", "compare", "which")
    if any(kw in msg_lower for kw in _VIZ_KW):
        chartable: list[str] = []
        for c in columns_meta:
            it = c.get("inferred_type", "")
            nm = c.get("name", "")
            uc = c.get("unique_count", 0)
            if it in ("numeric", "non_negative_numeric"):
                chartable.append(f"'{nm}' (numeric) \u2192 histogram/scatter/box plot")
            elif it == "categorical" and uc <= 50:
                chartable.append(f"'{nm}' (categorical, {uc} values) \u2192 bar/pie/stacked bar")
        if chartable:
            base_ctx += f"Chartable columns: {'; '.join(chartable)}. "
    matched_col: str | None = None
    for col_name in col_names:
        if col_name.lower() in msg_lower:
            matched_col = col_name
            break

    if matched_col is None:
        return base_ctx  # No column mentioned — keep the lightweight context

    # Load the dataframe to pull real values for the matched column
    df = DATASETS.get(dataset_id)
    if df is None and dataset.raw_storage_path:
        try:
            storage = get_storage()
            raw_bytes = storage.load(dataset.raw_storage_path)
            df = _parse_dataframe(dataset.filename, raw_bytes)
            DATASETS[dataset_id] = df
        except Exception:  # noqa: BLE001
            return base_ctx  # Storage error — fall back to lightweight context

    if df is None or matched_col not in df.columns:
        return base_ctx

    series = df[matched_col]
    sample_size = min(100, len(series))
    raw_values = series.head(sample_size).tolist()

    # Value-counts only for values that appear more than once (de-noises unique IDs)
    vc = series.value_counts()
    repeated_vc = {str(k): int(v) for k, v in vc[vc > 1].items()}

    col_ctx = (
        f"\n\nDetailed data for column '{matched_col}' "
        f"(first {sample_size} raw values): {raw_values}. "
    )
    if repeated_vc:
        col_ctx += f"Value counts (values appearing more than once): {repeated_vc}. "

    return base_ctx + col_ctx


@app.post("/chat")
def chat_endpoint(req: ChatRequestSchema, db: Session = Depends(get_db)) -> dict[str, Any]:
    from google.genai import types as genai_types

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "reply": "AI assistant isn't configured — add GEMINI_API_KEY to backend/.env and restart the server."
        }

    # Build context — column-enriched when a column name is mentioned, lightweight otherwise
    context = ""
    if req.dataset_id:
        context = _build_chat_context(req.message, req.dataset_id, db)

    # Append chart context when the frontend provides it
    if req.chart_context:
        cc = req.chart_context
        ct_name = cc.get("chartType", cc.get("chart_type", ""))
        cx_name = cc.get("x", "")
        cy_name = cc.get("y", "")
        c_labels = cc.get("labels", []) or []
        c_values = cc.get("values", []) or []
        c_box = cc.get("box_stats", []) or []
        c_series = cc.get("series", []) or []
        chart_summary = f"\n\nCurrently displayed chart: {ct_name} of '{cx_name}'"
        if cy_name:
            chart_summary += f" grouped by '{cy_name}'"
        chart_summary += "."
        if c_labels and c_values:
            pairs = [(str(l), v) for l, v in zip(c_labels, c_values) if isinstance(v, (int, float))]
            pairs.sort(key=lambda p: p[1], reverse=True)
            chart_summary += " Data (top values): " + ", ".join(f"{l}={v:g}" for l, v in pairs[:10]) + "."
        elif c_box:
            stats_strs = [
                f"{c_labels[i] if i < len(c_labels) else i}: min={s['min']:.3g} q1={s['q1']:.3g} median={s['median']:.3g} q3={s['q3']:.3g} max={s['max']:.3g}"
                for i, s in enumerate(c_box[:6])
            ]
            chart_summary += f" Box plot stats: {'; '.join(stats_strs)}."
        elif c_series:
            chart_summary += " Stacked series: " + ", ".join(s["name"] for s in c_series[:6]) + "."
        context += chart_summary

    full_prompt = f"{context}User question: {req.message}"

    client = genai.Client(api_key=api_key)
    models_to_try = GEMINI_MODELS_TO_TRY

    # --- Phase 2: define propose_cleaning_action as a Gemini function tool ---
    allowed_ops_desc = ", ".join(sorted(ALLOWED_OPERATIONS))
    propose_tool = genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(
                name="propose_cleaning_action",
                description=(
                    "Propose a single data cleaning action for a specific column. "
                    "Use this when you identify a concrete, actionable data quality issue "
                    "that can be fixed with one of the allowed operations. "
                    "Do NOT call this function for general questions — only when suggesting a fix."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "column": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="The exact column name to clean.",
                        ),
                        "operation": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description=(
                                f"The cleaning operation to apply. "
                                f"Must be exactly one of: {allowed_ops_desc}."
                            ),
                        ),
                        "reasoning": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="A concise explanation of why this fix is needed, referencing actual values where possible.",
                        ),
                    },
                    required=["column", "operation", "reasoning"],
                ),
            )
        ]
    )

    reply: str | None = None
    proposed_action: dict[str, Any] | None = None
    last_error: Exception | None = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[propose_tool],
                ),
            )

            # Inspect parts: collect function call (if any) and text parts separately
            fn_call = None
            text_parts: list[str] = []
            for candidate in (response.candidates or []):
                content = candidate.content
                if not content:
                    continue
                for part in (content.parts or []):
                    if hasattr(part, "function_call") and part.function_call is not None:
                        fn_call = part.function_call
                    elif hasattr(part, "text") and part.text:
                        text_parts.append(part.text)

            if fn_call is not None and fn_call.name == "propose_cleaning_action":
                args = dict(fn_call.args or {})
                col = str(args.get("column", "")).strip()
                op = str(args.get("operation", "")).strip()
                reasoning = str(args.get("reasoning", "")).strip()

                # Validate: operation must be in allowed list; column must exist in dataset
                col_names_for_validation: list[str] = []
                if req.dataset_id:
                    ds = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
                    if ds and ds.profile_json:
                        col_names_for_validation = [
                            c["name"] for c in ds.profile_json.get("columns", [])
                        ]

                op_valid = op in ALLOWED_OPERATIONS
                col_valid = op == "drop_duplicates" or col in col_names_for_validation

                if op_valid and col_valid:
                    proposed_action = {
                        "column": col,
                        "operation": op,
                        "reasoning": reasoning,
                        "severity": "medium",
                    }
                    # Use any accompanying text; fall back to a summary sentence
                    reply = (
                        " ".join(text_parts).strip()
                        or f"I suggest applying '{op}' to column '{col}': {reasoning}"
                    )
                else:
                    # Validation failed — surface the text parts if any, else generic message
                    reply = (
                        " ".join(text_parts).strip()
                        or "I identified a potential issue but couldn't map it to a valid operation. "
                           "Please check the column name or rephrase your question."
                    )
            else:
                # Plain text response (no function call)
                reply = " ".join(text_parts).strip() if text_parts else None
                if reply is None:
                    try:
                        reply = response.text  # SDK convenience accessor
                    except Exception:  # noqa: BLE001
                        reply = None

            if reply is not None:
                break

        except Exception as e:  # noqa: BLE001
            last_error = e
            continue

    if reply is None:
        return {"reply": f"Couldn't reach Gemini — {str(last_error)}"}

    result: dict[str, Any] = {"reply": reply}
    if proposed_action is not None:
        result["proposed_action"] = proposed_action
    return result
