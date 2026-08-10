# Data Analyst Copilot — Step 1: Upload + Auto-Profiling

This is the first milestone of the project: upload a CSV/Excel file and get
an automatic data-quality report (types, missing values, duplicates,
outliers) with zero configuration.

No database, no LLM calls yet — those come in later milestones. This part
is rule-based, deterministic, and free to run.

## Project layout

```
backend/    FastAPI service — file upload + profiling engine
frontend/   React (Vite) app — upload UI + report view
```

## Run it locally

You need Python 3.10+ and Node 18+.

**1. Backend**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000` (docs at `/docs`).

**2. Frontend** (in a second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, drop in a CSV or Excel file, and you'll see
the profiling report.

## How it works

- `POST /upload` reads the file with pandas, stores it in memory keyed by a
  `dataset_id`, and returns a profiling report.
- `backend/app/profiling.py` is the engine: per-column missing %, dtype,
  inferred semantic type (email, identifier, categorical, etc.), unique
  count, sample values, and — for numeric columns — min/max/mean/std plus
  IQR-based outlier detection.
- The frontend renders that report as a column-by-column ledger.

## What's next (not built yet)

1. **Cleaning suggestions** — turn profiling findings into proposed fixes
   ("340 rows have no `@` in `email` — drop or flag?") that the user
   approves before anything is applied.
2. **Persistent storage** — move datasets from the in-memory dict to
   object storage (S3/local disk) + Postgres for metadata, so pipelines
   survive a server restart and can belong to a user.
3. **Editable pipeline** — store approved cleaning steps as structured
   data so they're reorderable, undoable, and exportable as a pandas
   script.
4. **Visualization** — manual chart builder first, then natural-language
   chart requests via an LLM that outputs a constrained chart-spec JSON.

See the architecture discussion earlier in this conversation for the full
system design these milestones build toward.
