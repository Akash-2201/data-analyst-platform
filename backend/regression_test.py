"""Phase 4 regression script.

Tests:
  1. Large dataset (50k rows) upload + quality-bar-relevant stats check
  2. All 7 chart types via /chart-data
  3. Chat with chart_context (verify AI uses real data values)
  4. Core pipeline regression (suggestions, preview, apply, download)
"""
import requests
import json
import io
import csv
import random
import string

BASE = "http://127.0.0.1:8000"
PASS = []
FAIL = []

def check(label, condition, detail=""):
    if condition:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(label)
        print(f"  FAIL  {label}  {detail}")

# ── 1. Generate 50k-row CSV ──────────────────────────────────────────────────
print("\n=== Generating 50k-row CSV ===")
departments = ["Engineering", "Marketing", "HR", "Executive", "Sales", "Legal"]
cities = ["Bengaluru", "Mumbai", "Delhi", "Chennai", "Hyderabad"]
genders = ["Male", "Female", "Other"]

rows = []
for i in range(50_000):
    rows.append({
        "Name": f"Person_{i:05d}",
        "Age": random.randint(18, 65),
        "Gender": random.choice(genders),
        "City": random.choice(cities),
        "Department": random.choice(departments),
        "Salary": random.randint(30_000, 200_000),
        "Experience": random.randint(0, 40),
    })

buf = io.StringIO()
writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
writer.writeheader()
writer.writerows(rows)
csv_bytes = buf.getvalue().encode()
print(f"  Generated {len(rows):,} rows, {len(csv_bytes):,} bytes")

# ── 2. Upload ────────────────────────────────────────────────────────────────
print("\n=== Upload ===")
r = requests.post(f"{BASE}/upload", files={"file": ("large_test.csv", csv_bytes, "text/csv")})
r.raise_for_status()
data = r.json()
did = data["dataset_id"]
cols = {c["name"]: c for c in data.get("columns", [])}
print(f"  dataset_id={did}")

# Quality bar stats (must be in [0,100])
for col_name, col in cols.items():
    mp = col.get("missing_pct", 0)
    up = col.get("unique_pct", 0)
    check(f"missing_pct 0-100 [{col_name}]", 0 <= (mp or 0) <= 100, f"got {mp}")
    check(f"unique_pct 0-100 [{col_name}]", 0 <= (up or 0) <= 100, f"got {up}")

# Check unique_pct for Name column (should be ~100%)
name_pct = cols.get("Name", {}).get("unique_pct", 0)
check("Name unique_pct near 100", name_pct >= 90, f"got {name_pct}")

# ── 3. Chart types ───────────────────────────────────────────────────────────
print("\n=== Chart types (7 total) ===")
chart_tests = [
    ("bar",         {"chart_type": "bar",        "x": "Department", "agg": "count"},          "labels"),
    ("line",        {"chart_type": "line",       "x": "Department", "y": "Salary", "agg": "mean"}, "labels"),
    ("scatter",     {"chart_type": "scatter",    "x": "Department", "y": "Salary", "agg": "mean"}, "labels"),
    ("pie",         {"chart_type": "pie",        "x": "Gender",     "agg": "count"},          "labels"),
    ("histogram",   {"chart_type": "histogram",  "x": "Salary"},                              "labels"),
    ("box_plot",    {"chart_type": "box_plot",   "x": "Salary"},                              "box_stats"),
    ("stacked_bar", {"chart_type": "stacked_bar","x": "Department", "y": "Gender"},           "series"),
]
chart_data_results = {}
for (name, params, key) in chart_tests:
    try:
        r = requests.get(f"{BASE}/datasets/{did}/chart-data", params={**params, "use_cleaned": "true"})
        r.raise_for_status()
        d = r.json()
        ok = key in d and len(d[key]) > 0
        check(f"chart/{name} has {key}", ok, str(d.get(key, "missing"))[:120])
        chart_data_results[name] = d
    except Exception as e:
        check(f"chart/{name}", False, str(e))

# Print histogram bins
if "histogram" in chart_data_results:
    h = chart_data_results["histogram"]
    print(f"  Histogram: {len(h['labels'])} bins, labels[0]={h['labels'][0]}, values[0]={h['values'][0]}")

# Print box_plot stats
if "box_plot" in chart_data_results:
    bp = chart_data_results["box_plot"]
    print(f"  Box plot: {bp['box_stats'][0]}")

# Print stacked_bar series
if "stacked_bar" in chart_data_results:
    sb = chart_data_results["stacked_bar"]
    print(f"  Stacked bar: {len(sb['series'])} series, labels={sb['labels'][:3]}")

# ── 4. Chat with chart_context ───────────────────────────────────────────────
print("\n=== Chat with chart_context ===")
if "bar" in chart_data_results:
    bar = chart_data_results["bar"]
    chart_ctx = {
        "chartType": "bar",
        "x": "Department",
        "y": None,
        "agg": "count",
        "labels": bar["labels"],
        "values": bar["values"],
    }
    # Find the real highest department from our data
    top_dept = bar["labels"][bar["values"].index(max(bar["values"]))]
    print(f"  Actual top department in data: {top_dept} ({max(bar['values'])} rows)")

    try:
        r = requests.post(f"{BASE}/chat", json={
            "message": "Which department has the highest count in this chart?",
            "dataset_id": did,
            "chart_context": chart_ctx,
        })
        r.raise_for_status()
        reply = r.json().get("reply", "")
        print(f"  Chat reply: {reply[:300]}")
        check("Chat reply mentions top dept", top_dept.lower() in reply.lower(), f"reply={reply[:120]}")
    except Exception as e:
        check("Chat with chart_context", False, str(e))

# ── 5. Core pipeline regression ──────────────────────────────────────────────
print("\n=== Core pipeline regression (small dataset) ===")
# Use the existing small messy CSV
with open("test_messy_names.csv", "rb") as f:
    r2 = requests.post(f"{BASE}/upload", files={"file": ("test_messy_names.csv", f, "text/csv")})
r2.raise_for_status()
small_did = r2.json()["dataset_id"]

# Suggestions
r3 = requests.get(f"{BASE}/datasets/{small_did}/suggestions")
r3.raise_for_status()
suggs = r3.json()
check("Suggestions non-empty", len(suggs) > 0, f"got {len(suggs)}")

# Preview
normalize_steps = [s for s in suggs if s["action"] == "normalize_case"]
if normalize_steps:
    step = normalize_steps[0]
    r4 = requests.post(f"{BASE}/datasets/{small_did}/preview", json=[{"action": step["action"], "params": step["params"]}])
    r4.raise_for_status()
    prev = r4.json()
    check("Preview response valid", "row_count_before" in prev)

# Apply + download
r5 = requests.post(f"{BASE}/datasets/{small_did}/pipeline", json=[{"action": "drop_duplicates", "params": {}}])
r5.raise_for_status()
r6 = requests.post(f"{BASE}/datasets/{small_did}/apply")
r6.raise_for_status()
result = r6.json()
check("Apply returns rows_before", "rows_before" in result)

r7 = requests.get(f"{BASE}/datasets/{small_did}/download-cleaned?format=csv")
check("CSV download 200", r7.status_code == 200)
r8 = requests.get(f"{BASE}/datasets/{small_did}/download-cleaned?format=xlsx")
check("XLSX download 200", r8.status_code == 200)

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  PASSED: {len(PASS)}  |  FAILED: {len(FAIL)}")
if FAIL:
    print("\nFAILED tests:")
    for f_ in FAIL:
        print(f"  - {f_}")
else:
    print("  All checks passed!")
