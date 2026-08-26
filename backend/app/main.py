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

from app.ai_suggestions import generate_ai_suggestions, ALLOWED_OPERATIONS
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


@app.get("/datasets/{dataset_id}/chart-data")
def get_chart_data(
    dataset_id: str,
    chart_type: str = Query("bar", regex="^(bar|line|scatter|pie)$"),
    x: str = Query(..., description="Column name for X axis / grouping"),
    y: str | None = Query(None, description="Column name for Y axis (optional for count-based charts)"),
    agg: str = Query("count", regex="^(count|sum|mean)$"),
    use_cleaned: bool = Query(True, description="Prefer cleaned dataset if available"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return chart-ready aggregated data for the given dataset.

    Never modifies state — read-only endpoint.
    """
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")

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

    # --- Validate columns ---
    if x not in df.columns:
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
    try:
        if agg == "count" or y is None:
            # Count occurrences of each x value
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

    full_prompt = f"{context}User question: {req.message}"

    client = genai.Client(api_key=api_key)
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash"]

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
