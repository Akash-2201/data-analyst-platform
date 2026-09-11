"""
Phase 1-4 Diagnostic: Frank row-loss + Gender 'M' variant bug hunt.
Run from: data-analyst-platform/backend/
"""
from __future__ import annotations

import io
import pandas as pd
from app.cleaning import apply_pipeline

# ── Exact 9-row dataset ───────────────────────────────────────────────────────
CSV = """\
Name,Age,Gender,City,Department,Salary
Alice,28,MALE,Bengaluru,Marketing,72000
Bob,35,male,bangalore,Marekting,58000
Charlie,42,M,BANGALORE,Marketing,95000
Diana,-5,FEMALE,Bengaluru,marketing,61000
Eve,31,female,Banglore,Engineering,88000
Frank,55,F,bengaluru,engineering,  120000  
Grace,29,MALE,BENGALURU,Marketing,45000
Heidi,33,male,bangalore,Marekting,79000
Ivan,26,FEMALE,Bengaluru,HR,42000
"""

df_original = pd.read_csv(io.StringIO(CSV))
print("=" * 70)
print("ORIGINAL DATASET — 9 rows")
print("=" * 70)
print(df_original.to_string())
print(f"\nRow count: {len(df_original)}")

# ── Steps a user would reasonably approve ─────────────────────────────────────
steps = [
    {
        "action": "standardize_category",
        "params": {
            "column": "City",
            "mapping": {
                "bangalore":  "Bengaluru",
                "BANGALORE":  "Bengaluru",
                "Banglore":   "Bengaluru",
                "bengaluru":  "Bengaluru",
                "BENGALURU":  "Bengaluru",
            },
        },
        "description": "Standardize City variants",
        "severity": "high",
    },
    {
        "action": "standardize_category",
        "params": {
            "column": "Department",
            "mapping": {
                "Marekting":   "Marketing",
                "MARKETING":   "Marketing",
                "marketing":   "Marketing",
                "engineering": "Engineering",
                "ENGINEERING": "Engineering",
            },
        },
        "description": "Standardize Department variants",
        "severity": "high",
    },
    {
        "action": "clip_negative_to_null",
        "params": {"column": "Age"},
        "description": "Clip negative Age values to null",
        "severity": "high",
    },
    {
        "action": "normalize_case",
        "params": {"column": "Gender", "case": "title"},
        "description": "Normalize Gender capitalization",
        "severity": "medium",
    },
]

# ── STEP-BY-STEP TRACE with snapshots ────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP-BY-STEP TRACE — inspecting each operation")
print("=" * 70)

import copy

df_trace = df_original.copy()
for i, step in enumerate(steps):
    rows_before = len(df_trace)
    action = step["action"]
    params = step["params"]
    col = params.get("column", "—")

    # Apply same logic as apply_pipeline
    if action == "standardize_category":
        mapping = params.get("mapping", {})
        df_trace[col] = df_trace[col].replace(mapping)
        resilient = {}
        for k, v in mapping.items():
            for kk in [str(k), str(k).strip(), str(k).lower(), str(k).upper(), str(k).title()]:
                resilient[kk] = v
        df_trace[col] = df_trace[col].replace(resilient)

    elif action == "clip_negative_to_null":
        num = pd.to_numeric(df_trace[col], errors="coerce")
        df_trace.loc[num < 0, col] = None

    elif action == "normalize_case":
        case = params.get("case", "title")
        non_null_mask = df_trace[col].notna()
        if case == "title":
            df_trace.loc[non_null_mask, col] = (
                df_trace.loc[non_null_mask, col].astype(str).str.title()
            )

    rows_after = len(df_trace)
    lost = rows_before - rows_after
    flag = f" ⚠️  LOST {lost} ROWS" if lost > 0 else " ✓"
    print(f"\n[Step {i+1}] {action} (col={col}): {rows_before} → {rows_after}{flag}")
    print(f"  {col} values now: {df_trace[col].tolist()}")
    if lost > 0:
        print(f"  ROWS MISSING — checking which ones disappeared...")

# ── Collision detection: do any rows become identical after normalize? ─────────
print("\n" + "=" * 70)
print("DUPLICATE-COLLISION CHECK after all 4 steps")
print("=" * 70)
print(df_trace.to_string())
print(f"\nFull exact duplicates: {df_trace.duplicated().sum()}")
dups = df_trace[df_trace.duplicated(keep=False)]
if not dups.empty:
    print("Duplicate rows:")
    print(dups.to_string())
else:
    print("No exact duplicates found.")

# ── Now check if normalize_case causes Bob == Heidi ───────────────────────────
print("\n" + "=" * 70)
print("BOB vs HEIDI — do they collide?")
print("=" * 70)
bob   = df_trace[df_trace["Name"] == "Bob"]
heidi = df_trace[df_trace["Name"] == "Heidi"]
print(f"Bob:   {bob.iloc[0].tolist()}")
print(f"Heidi: {heidi.iloc[0].tolist()}")

# Compare field by field (ignoring Name)
cols_to_check = ["Age", "Gender", "City", "Department", "Salary"]
for c in cols_to_check:
    bv = str(bob.iloc[0][c]).strip()
    hv = str(heidi.iloc[0][c]).strip()
    match = "✓ MATCH" if bv == hv else "✗ differ"
    print(f"  {c}: Bob={bv!r}  Heidi={hv!r}  → {match}")

# ── run real apply_pipeline ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print("REAL apply_pipeline() RESULT")
print("=" * 70)
df_fresh = df_original.copy()
cleaned_df, log = apply_pipeline(df_fresh, steps)
print(f"\n{len(df_original)} rows → {len(cleaned_df)} rows\n")
for entry in log:
    marker = " ⚠️  ROWS LOST" if entry["rows_affected"] > 0 else " ✓"
    print(f"  {entry['action']:25s} before={entry['rows_before']} "
          f"after={entry['rows_after']} affected={entry['rows_affected']}{marker}")
print("\nFinal cleaned dataframe:")
print(cleaned_df.to_string())
print(f"\nFrank present: {'Frank' in cleaned_df['Name'].values}")
print(f"Gender unique values: {sorted(cleaned_df['Gender'].unique().tolist())}")
m_present = "M" in cleaned_df["Gender"].values
f_present = "F" in cleaned_df["Gender"].values
print(f"'M' still in Gender: {m_present}")
print(f"'F' still in Gender: {f_present}")

# ── Check Salary whitespace on Frank's row ────────────────────────────────────
print("\n" + "=" * 70)
print("SALARY WHITESPACE CHECK — Frank's raw Salary value")
print("=" * 70)
frank_orig = df_original[df_original["Name"] == "Frank"]
print(f"Frank raw Salary: {frank_orig['Salary'].values!r}")
salary_stripped = str(frank_orig["Salary"].values[0]).strip()
print(f"Frank Salary stripped: {salary_stripped!r}")

# Now test: after standardize_category on City, is Frank's City resolved?
df_city_only = df_original.copy()
city_map = {"bangalore": "Bengaluru", "BANGALORE": "Bengaluru",
            "Banglore": "Bengaluru", "bengaluru": "Bengaluru", "BENGALURU": "Bengaluru"}
df_city_only["City"] = df_city_only["City"].replace(city_map)
frank_city = df_city_only[df_city_only["Name"] == "Frank"]["City"].values[0]
print(f"\nFrank's City after standardize: {frank_city!r}  (expected 'Bengaluru')")

# ── Phase 2: Confirm 'M'/'F' confidence logic ────────────────────────────────
print("\n" + "=" * 70)
print("PHASE 2 — Gender 'M' confidence design trace")
print("=" * 70)
print("""
In ai_suggestions.py::_build_mapping_from_ai_groups():

    for item in raw_variants:
        variant = item["value"]      # e.g. "M"
        conf    = item["confidence"] # "low"  ← Gemini marks abbreviations as low

        if conf == "high":           # ← LINE 340
            group_mapping[variant] = canonical   # only high-conf in the mapping!

So 'M' with conf="low":
  - IS added to params.variant_confidences = {"M": "low"}
  - IS shown to the user in the review UI as a low-confidence row
  - is NOT added to params.mapping         ← absent from the mapping sent to apply

In the frontend (App.jsx, fetchSuggestions):
  if (confidences[val] === "high" && aiMapping[val]) {
      initMappings[col][val] = aiMapping[val];  // defaults to AI's target
  } else {
      initMappings[col][val] = val;             // defaults to "keep as-is"
  }

  'M' → confidences["M"] = "low" → initialised to "keep as-is" (identity mapping)
  The user must MANUALLY select a target for M in the per-row review table.
  If they don't touch it, M is NOT included in the final payload sent to /apply.

Verdict: This is WORKING AS DESIGNED.
The review UI shows M with a low-confidence badge ("low" pill styling in CSS).
The user gets to decide. If they want M → Male, they select it in the dropdown.
""")

print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)
