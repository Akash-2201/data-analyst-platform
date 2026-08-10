"""
API entrypoint.

MVP scope: upload a CSV/XLSX file, store it in memory, and return an
auto-generated profiling report. No auth, no database yet -- those come
in the next milestones (see README).
"""

from __future__ import annotations

import io
import uuid
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.profiling import profile_dataframe

app = FastAPI(title="Data Analyst Copilot API", version="0.1.0")

# Wide-open CORS for local dev. Tighten this before deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory dataset store, keyed by dataset_id. Fine for a single-user local
# MVP; swap for real storage (S3 + Postgres) once we get past step 1.
DATASETS: dict[str, pd.DataFrame] = {}


def _read_upload(filename: str, raw: bytes) -> pd.DataFrame:
    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            return pd.read_csv(io.BytesIO(raw))
        if lower.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}") from exc

    raise HTTPException(status_code=400, detail="Only .csv, .xlsx, and .xls files are supported.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    df = _read_upload(file.filename or "upload.csv", raw)
    if df.empty:
        raise HTTPException(status_code=400, detail="No rows found in the uploaded file.")

    dataset_id = str(uuid.uuid4())
    DATASETS[dataset_id] = df

    report = profile_dataframe(df)
    return {"dataset_id": dataset_id, "filename": file.filename, **report}


@app.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str) -> dict[str, Any]:
    df = DATASETS.get(dataset_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found. Upload it again.")
    return {"dataset_id": dataset_id, **profile_dataframe(df)}
