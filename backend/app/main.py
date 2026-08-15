"""
API entrypoint.

Upload CSV/XLSX datasets, generate profiling reports, suggest rule-based
cleaning steps, persist pipeline configuration, apply cleaning transformations,
download cleaned CSV/Excel results, and handle chat/settings endpoints.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import uuid
from typing import Any

from dotenv import load_dotenv
from google import genai
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_suggestions import generate_ai_suggestions
from app.cleaning import apply_pipeline
from app.database import Base, engine, get_db
from app.models import Dataset, PipelineStep
from app.profiling import profile_dataframe
from app.storage import get_storage

# Load environment variables from .env file if present
load_dotenv()
load_dotenv(Path(__file__).parent.parent / ".env")

app = FastAPI(title="Data Analyst Copilot API", version="0.1.0")

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...), db: Session = Depends(get_db)
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
        filename=filename,
        raw_storage_path=raw_path,
        profile_json=report,
    )
    db.add(dataset)
    db.commit()

    return {"dataset_id": dataset_id, "filename": filename, **report}


@app.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    df = DATASETS.get(dataset_id)
    if df is None:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        storage = get_storage()
        try:
            raw_bytes = storage.load(dataset.raw_storage_path)
            df = _parse_dataframe(dataset.filename, raw_bytes)
            DATASETS[dataset_id] = df
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not load dataset: {exc}") from exc

    return profile_dataframe(df)


@app.get("/datasets/{dataset_id}/suggestions")
def get_suggestions(dataset_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    df = DATASETS.get(dataset_id)
    if df is None:
        profile = get_profile(dataset_id, db)
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        storage = get_storage()
        raw_bytes = storage.load(dataset.raw_storage_path)
        df = _parse_dataframe(dataset.filename, raw_bytes)
        DATASETS[dataset_id] = df
    else:
        profile = profile_dataframe(df)

    result = generate_ai_suggestions(df, profile)
    # Attach general_notes and source as extra metadata so callers can inspect
    # which path ran; the suggestions list shape is unchanged for the frontend.
    suggestions = result["suggestions"]
    for sug in suggestions:
        sug.setdefault("general_notes", result["general_notes"])
        sug.setdefault("source", result["source"])
    return suggestions


@app.post("/datasets/{dataset_id}/pipeline")
def save_pipeline(
    dataset_id: str, steps: list[StepSchema], db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    db.query(PipelineStep).filter(PipelineStep.dataset_id == dataset_id).delete()

    created_steps = []
    for idx, st in enumerate(steps):
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
def get_pipeline(dataset_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")

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
    dataset_id: str, db: Session = Depends(get_db)
) -> dict[str, Any]:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")

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
    dataset_id: str, steps: list[StepSchema], db: Session = Depends(get_db)
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
        storage = get_storage()
        try:
            raw_bytes = storage.load(dataset.raw_storage_path)
            df = _parse_dataframe(dataset.filename, raw_bytes)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Raw dataset file not found in storage.")

    if not steps:
        raise HTTPException(status_code=400, detail="No steps provided for preview.")

    # Figure out which columns will be affected, for before-snapshot
    affected_columns: set[str] = set()
    for step in steps:
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
        })

    for col in sorted(affected_columns):
        if col not in cleaned_df.columns:
            # Column was dropped
            column_diffs.append({
                "column": col,
                "before": before_counts.get(col, {}),
                "after": {},
                "note": "column dropped",
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
            column_diffs.append({
                "column": col,
                "before": before,
                "after": after_vc,
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
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    db: Session = Depends(get_db),
) -> Response:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset or not dataset.cleaned_storage_path:
        raise HTTPException(
            status_code=404, detail="Cleaned dataset not available. Apply cleaning first."
        )

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
        # Parse CSV bytes to DataFrame then convert to Excel
        cleaned_df = pd.read_csv(io.BytesIO(csv_bytes))
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            cleaned_df.to_excel(writer, index=False, sheet_name="Cleaned Data")
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


@app.post("/chat")
def chat_endpoint(req: ChatRequestSchema, db: Session = Depends(get_db)) -> dict[str, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "reply": "AI assistant isn't configured — add GEMINI_API_KEY to backend/.env and restart the server."
        }

    context = ""
    if req.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
        if dataset and dataset.profile_json and "columns" in dataset.profile_json:
            cols = [c["name"] for c in dataset.profile_json["columns"]]
            row_count = dataset.profile_json.get("row_count", 0)
            context = f"The user's dataset has {row_count} rows and these columns: {cols}. "
        elif req.dataset_id in DATASETS:
            df = DATASETS[req.dataset_id]
            context = f"The user's dataset has {len(df)} rows and these columns: {list(df.columns)}. "

    full_prompt = f"{context}User question: {req.message}"
    client = genai.Client(api_key=api_key)
    models_to_try = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
    reply = None
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=full_prompt,
            )
            reply = response.text
            break
        except Exception as e:  # noqa: BLE001
            last_error = e
            continue

    if reply is None:
        return {"reply": f"Couldn't reach Gemini — {str(last_error)}"}
    return {"reply": reply}
