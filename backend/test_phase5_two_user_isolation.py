"""
Phase 5 — Two-User Isolation Test + Full Authenticated Regression
=================================================================

What this script does:

1. Register two separate test accounts via Supabase (User A, User B).
2. Log in as User A → upload a file → confirm it's tagged with User A's ID in DB.
3. Log out → log in as User B → confirm User B does NOT see User A's dataset
   in their list. Confirm directly hitting User A's dataset ID via the API
   while authenticated as User B returns 403.
4. Log back in as User A → confirm their data is still there and functional.
5. Run full regression (upload→profile, clean/review, checkboxes, preview/apply,
   download CSV+xlsx, charts, chat) — all under an authenticated session.

At the end: explicit PASS/FAIL verdicts for:
  - Two-user isolation (security)
  - All regression items under auth
"""

import io
import csv
import json
import os
import random
import string
import sys
import time
import uuid

import requests
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE = "http://127.0.0.1:8000"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()

assert SUPABASE_URL, "SUPABASE_URL must be set in .env"
assert SUPABASE_ANON_KEY, "SUPABASE_ANON_KEY must be set in .env"

# Test account credentials — unique per run to avoid clashes
RUN_ID = uuid.uuid4().hex[:8]
USER_A_EMAIL = f"testuser_a_{RUN_ID}@phase5test.local"
USER_A_PASSWORD = f"Pa$$w0rd_A_{RUN_ID}"
USER_B_EMAIL = f"testuser_b_{RUN_ID}@phase5test.local"
USER_B_PASSWORD = f"Pa$$w0rd_B_{RUN_ID}"

PASS = []
FAIL = []

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def check(label, condition, detail=""):
    if condition:
        PASS.append(label)
        print(f"  ✅ PASS  {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ FAIL  {label}  {detail}")


def auth_headers(token):
    """Build Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


def supabase_signup(email, password):
    """Register a user via Supabase REST API (GoTrue)."""
    url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    body = {"email": email, "password": password}
    r = requests.post(url, headers=headers, json=body, timeout=15)
    if r.status_code not in (200, 201):
        print(f"    Signup response ({r.status_code}): {r.text[:300]}")
    r.raise_for_status()
    data = r.json()
    # If email confirmation is disabled, we get a session immediately
    access_token = data.get("access_token") or data.get("session", {}).get("access_token")
    user_id = data.get("id") or data.get("user", {}).get("id")
    return {"access_token": access_token, "user_id": user_id, "data": data}


def supabase_login(email, password):
    """Log in via Supabase REST API (GoTrue)."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    body = {"email": email, "password": password}
    r = requests.post(url, headers=headers, json=body, timeout=15)
    if r.status_code not in (200, 201):
        print(f"    Login response ({r.status_code}): {r.text[:300]}")
    r.raise_for_status()
    data = r.json()
    return {
        "access_token": data["access_token"],
        "user_id": data["user"]["id"],
        "email": data["user"]["email"],
    }


def generate_test_csv(name="test_data", rows=20, cols=None):
    """Generate a small CSV in memory and return (filename, bytes)."""
    if cols is None:
        cols = ["Name", "Age", "City", "Revenue"]
    departments = ["Sales", "Marketing", "Engineering", "HR"]
    cities = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for i in range(rows):
        row = [
            f"Person_{i}",
            random.randint(20, 60),
            random.choice(cities),
            random.randint(10000, 100000),
        ]
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode()
    return (f"{name}.csv", csv_bytes)


# ─────────────────────────────────────────────────────────────
# PHASE 5a: Register + Two-User Isolation
# ─────────────────────────────────────────────────────────────

def test_two_user_isolation():
    print("\n" + "=" * 64)
    print("  PHASE 5a: TWO-USER ISOLATION TEST")
    print("=" * 64)

    # ── 1. Register User A ──────────────────────────────────
    print(f"\n--- 1. Register User A: {USER_A_EMAIL} ---")
    try:
        signup_a = supabase_signup(USER_A_EMAIL, USER_A_PASSWORD)
        token_a = signup_a["access_token"]
        user_a_id = signup_a["user_id"]
        if not token_a:
            # If email confirmation is required, try logging in
            print("    Signup didn't return token; trying login...")
            login_a = supabase_login(USER_A_EMAIL, USER_A_PASSWORD)
            token_a = login_a["access_token"]
            user_a_id = login_a["user_id"]
        check("User A registered/logged in", bool(token_a))
        print(f"    User A ID: {user_a_id}")
    except Exception as e:
        check("User A registration", False, str(e))
        return None

    # ── 2. Register User B ──────────────────────────────────
    print(f"\n--- 2. Register User B: {USER_B_EMAIL} ---")
    try:
        signup_b = supabase_signup(USER_B_EMAIL, USER_B_PASSWORD)
        token_b = signup_b["access_token"]
        user_b_id = signup_b["user_id"]
        if not token_b:
            print("    Signup didn't return token; trying login...")
            login_b = supabase_login(USER_B_EMAIL, USER_B_PASSWORD)
            token_b = login_b["access_token"]
            user_b_id = login_b["user_id"]
        check("User B registered/logged in", bool(token_b))
        print(f"    User B ID: {user_b_id}")
    except Exception as e:
        check("User B registration", False, str(e))
        return None

    # Verify different users
    check("User A ≠ User B (different IDs)", user_a_id != user_b_id,
          f"A={user_a_id}, B={user_b_id}")

    # ── 3. User A uploads a file ────────────────────────────
    print("\n--- 3. User A uploads a dataset ---")
    fname, fbytes = generate_test_csv("user_a_data", rows=15)
    r = requests.post(
        f"{BASE}/upload",
        headers=auth_headers(token_a),
        files={"file": (fname, fbytes, "text/csv")},
    )
    check("User A upload succeeds (200)", r.status_code == 200, f"got {r.status_code}")
    upload_data = r.json()
    dataset_a_id = upload_data.get("dataset_id", "")
    check("User A upload returns dataset_id", bool(dataset_a_id))
    print(f"    User A dataset_id: {dataset_a_id}")

    # ── 4. Verify dataset is tagged with User A's ID in DB ──
    print("\n--- 4. Verify dataset tagged with User A's ID (via API) ---")
    r_list_a = requests.get(
        f"{BASE}/datasets",
        headers=auth_headers(token_a),
    )
    check("User A list datasets (200)", r_list_a.status_code == 200)
    datasets_a = r_list_a.json()
    found_a = any(d["id"] == dataset_a_id for d in datasets_a)
    check("User A sees their own dataset in list", found_a,
          f"datasets: {[d['id'] for d in datasets_a]}")

    # ── 5. User B should NOT see User A's dataset ───────────
    print("\n--- 5. User B lists datasets — should NOT see User A's data ---")
    r_list_b = requests.get(
        f"{BASE}/datasets",
        headers=auth_headers(token_b),
    )
    check("User B list datasets (200)", r_list_b.status_code == 200)
    datasets_b = r_list_b.json()
    b_sees_a = any(d["id"] == dataset_a_id for d in datasets_b)
    check("User B does NOT see User A's dataset", not b_sees_a,
          f"User B datasets: {[d['id'] for d in datasets_b]}")

    # ── 6. User B hits User A's dataset ID directly → 403 ──
    print("\n--- 6. User B direct-access User A's dataset endpoints → 403 ---")

    # 6a. Profile
    r_profile = requests.get(
        f"{BASE}/datasets/{dataset_a_id}/profile",
        headers=auth_headers(token_b),
    )
    check("User B → User A's /profile returns 403", r_profile.status_code == 403,
          f"got {r_profile.status_code}: {r_profile.text[:200]}")

    # 6b. Suggestions
    r_sugg = requests.get(
        f"{BASE}/datasets/{dataset_a_id}/suggestions",
        headers=auth_headers(token_b),
    )
    check("User B → User A's /suggestions returns 403", r_sugg.status_code == 403,
          f"got {r_sugg.status_code}")

    # 6c. Pipeline save
    r_pipe = requests.post(
        f"{BASE}/datasets/{dataset_a_id}/pipeline",
        headers={**auth_headers(token_b), "Content-Type": "application/json"},
        json=[{"action": "drop_duplicates", "params": {}, "description": "test", "severity": "low"}],
    )
    check("User B → User A's POST /pipeline returns 403", r_pipe.status_code == 403,
          f"got {r_pipe.status_code}")

    # 6d. Apply
    r_apply = requests.post(
        f"{BASE}/datasets/{dataset_a_id}/apply",
        headers=auth_headers(token_b),
    )
    check("User B → User A's POST /apply returns 403", r_apply.status_code == 403,
          f"got {r_apply.status_code}")

    # 6e. Preview
    r_prev = requests.post(
        f"{BASE}/datasets/{dataset_a_id}/preview",
        headers={**auth_headers(token_b), "Content-Type": "application/json"},
        json=[{"action": "drop_duplicates", "params": {}, "description": "test", "severity": "low"}],
    )
    check("User B → User A's POST /preview returns 403", r_prev.status_code == 403,
          f"got {r_prev.status_code}")

    # 6f. Download-cleaned (won't have cleaned data, but 403 should come first)
    r_dl = requests.get(
        f"{BASE}/datasets/{dataset_a_id}/download-cleaned?format=csv",
        headers=auth_headers(token_b),
    )
    # This might be 403 or 404 (no cleaned data) — but 403 is the correct security response
    check("User B → User A's /download-cleaned returns 403 or 404",
          r_dl.status_code in (403, 404),
          f"got {r_dl.status_code}")

    # 6g. Chart-data
    r_chart = requests.get(
        f"{BASE}/datasets/{dataset_a_id}/chart-data?chart_type=bar&x=City&agg=count",
        headers=auth_headers(token_b),
    )
    # Chart might not enforce ownership if it reads from in-memory cache — check what we get
    check("User B → User A's /chart-data returns 403",
          r_chart.status_code == 403,
          f"got {r_chart.status_code}: {r_chart.text[:200]}")

    # ── 7. User B uploads their OWN file ────────────────────
    print("\n--- 7. User B uploads their own dataset ---")
    fname_b, fbytes_b = generate_test_csv("user_b_data", rows=10)
    r_b_upload = requests.post(
        f"{BASE}/upload",
        headers=auth_headers(token_b),
        files={"file": (fname_b, fbytes_b, "text/csv")},
    )
    check("User B upload succeeds (200)", r_b_upload.status_code == 200)
    dataset_b_id = r_b_upload.json().get("dataset_id", "")
    print(f"    User B dataset_id: {dataset_b_id}")

    # Verify User B only sees their own
    r_list_b2 = requests.get(f"{BASE}/datasets", headers=auth_headers(token_b))
    datasets_b2 = r_list_b2.json()
    b_sees_own = any(d["id"] == dataset_b_id for d in datasets_b2)
    b_still_cant_see_a = not any(d["id"] == dataset_a_id for d in datasets_b2)
    check("User B sees their own dataset", b_sees_own)
    check("User B still cannot see User A's dataset", b_still_cant_see_a)

    # ── 8. Switch back to User A — data still there ─────────
    print("\n--- 8. Switch back to User A — confirm data persists ---")
    # Re-login User A (fresh token)
    login_a2 = supabase_login(USER_A_EMAIL, USER_A_PASSWORD)
    token_a2 = login_a2["access_token"]
    check("User A re-login succeeds", bool(token_a2))

    r_list_a2 = requests.get(f"{BASE}/datasets", headers=auth_headers(token_a2))
    datasets_a2 = r_list_a2.json()
    a_still_has = any(d["id"] == dataset_a_id for d in datasets_a2)
    a_cannot_see_b = not any(d["id"] == dataset_b_id for d in datasets_a2)
    check("User A still sees their own dataset after re-login", a_still_has)
    check("User A cannot see User B's dataset", a_cannot_see_b)

    # User A profile endpoint still works
    r_prof = requests.get(
        f"{BASE}/datasets/{dataset_a_id}/profile",
        headers=auth_headers(token_a2),
    )
    check("User A's /profile still returns 200", r_prof.status_code == 200)
    prof_data = r_prof.json()
    check("User A's profile has columns", len(prof_data.get("columns", [])) > 0)

    return token_a2, dataset_a_id, user_a_id


# ─────────────────────────────────────────────────────────────
# PHASE 5b: Full Regression Under Authenticated Session
# ─────────────────────────────────────────────────────────────

def test_full_regression(token, existing_dataset_id=None):
    print("\n" + "=" * 64)
    print("  PHASE 5b: FULL REGRESSION UNDER AUTHENTICATED SESSION")
    print("=" * 64)

    hdrs = auth_headers(token)

    # ── 1. Upload fresh dataset ─────────────────────────────
    print("\n--- 1. Upload a fresh test dataset ---")
    departments = ["Engineering", "Marketing", "HR", "Executive", "Sales"]
    cities = ["Bengaluru", "Mumbai", "Delhi", "Chennai", "Hyderabad"]
    genders = ["Male", "Female", "Other"]

    rows = []
    for i in range(200):
        rows.append({
            "Name": f"Person_{i:04d}",
            "Age": random.randint(18, 65),
            "Gender": random.choice(genders),
            "City": random.choice(cities),
            "Department": random.choice(departments),
            "Salary": random.randint(30000, 200000),
            "Experience": random.randint(0, 40),
        })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = buf.getvalue().encode()

    r = requests.post(
        f"{BASE}/upload",
        headers=hdrs,
        files={"file": ("regression_test.csv", csv_bytes, "text/csv")},
    )
    check("Regression upload (200)", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    data = r.json()
    did = data["dataset_id"]
    cols = {c["name"]: c for c in data.get("columns", [])}
    print(f"    dataset_id={did}, columns={list(cols.keys())}")

    # ── 2. Profile endpoint ─────────────────────────────────
    print("\n--- 2. Profile endpoint ---")
    r_prof = requests.get(f"{BASE}/datasets/{did}/profile", headers=hdrs)
    check("Profile (200)", r_prof.status_code == 200)
    profile = r_prof.json()
    check("Profile has columns", len(profile.get("columns", [])) > 0)
    check("Profile has row_count", profile.get("row_count", 0) == 200,
          f"got {profile.get('row_count')}")

    # Quality bar stats valid
    for col_name, col in cols.items():
        mp = col.get("missing_pct", 0) or 0
        up = col.get("unique_pct", 0) or 0
        check(f"missing_pct 0-100 [{col_name}]", 0 <= mp <= 100, f"got {mp}")
        check(f"unique_pct 0-100 [{col_name}]", 0 <= up <= 100, f"got {up}")

    # ── 3. Suggestions (clean/review) ───────────────────────
    print("\n--- 3. Suggestions (AI clean/review) ---")
    r_sugg = requests.get(f"{BASE}/datasets/{did}/suggestions", headers=hdrs)
    check("Suggestions (200)", r_sugg.status_code == 200, f"got {r_sugg.status_code}: {r_sugg.text[:200]}")

    # ── 4. Pipeline save (checkboxes) ───────────────────────
    print("\n--- 4. Save pipeline (drop_duplicates step) ---")
    steps = [
        {
            "action": "drop_duplicates",
            "params": {},
            "description": "Remove duplicate rows",
            "severity": "medium",
        }
    ]
    r_save = requests.post(
        f"{BASE}/datasets/{did}/pipeline",
        headers={**hdrs, "Content-Type": "application/json"},
        json=steps,
    )
    check("Pipeline save (200)", r_save.status_code == 200, f"got {r_save.status_code}: {r_save.text[:200]}")

    # ── 5. Preview ──────────────────────────────────────────
    print("\n--- 5. Preview pipeline ---")
    r_prev = requests.post(
        f"{BASE}/datasets/{did}/preview",
        headers={**hdrs, "Content-Type": "application/json"},
        json=steps,
    )
    check("Preview (200)", r_prev.status_code == 200, f"got {r_prev.status_code}: {r_prev.text[:200]}")
    prev_data = r_prev.json()
    check("Preview has original_row_count", "original_row_count" in prev_data)

    # ── 6. Apply ────────────────────────────────────────────
    print("\n--- 6. Apply pipeline ---")
    r_apply = requests.post(f"{BASE}/datasets/{did}/apply", headers=hdrs)
    check("Apply (200)", r_apply.status_code == 200, f"got {r_apply.status_code}: {r_apply.text[:200]}")
    apply_data = r_apply.json()
    check("Apply returns cleaned_row_count", "cleaned_row_count" in apply_data)

    # ── 7. Download CSV ─────────────────────────────────────
    print("\n--- 7. Download cleaned CSV ---")
    r_csv = requests.get(f"{BASE}/datasets/{did}/download-cleaned?format=csv", headers=hdrs)
    check("CSV download (200)", r_csv.status_code == 200, f"got {r_csv.status_code}")
    check("CSV content-type", "text/csv" in r_csv.headers.get("content-type", "") or
          "text/plain" in r_csv.headers.get("content-type", ""),
          f"got {r_csv.headers.get('content-type')}")
    csv_content = r_csv.text
    check("CSV has data rows", len(csv_content.strip().splitlines()) > 1,
          f"lines={len(csv_content.strip().splitlines())}")

    # ── 8. Download XLSX ────────────────────────────────────
    print("\n--- 8. Download cleaned XLSX ---")
    r_xlsx = requests.get(f"{BASE}/datasets/{did}/download-cleaned?format=xlsx", headers=hdrs)
    check("XLSX download (200)", r_xlsx.status_code == 200, f"got {r_xlsx.status_code}")
    check("XLSX content-type",
          "spreadsheetml" in r_xlsx.headers.get("content-type", "") or
          "openxml" in r_xlsx.headers.get("content-type", "") or
          "octet-stream" in r_xlsx.headers.get("content-type", ""),
          f"got {r_xlsx.headers.get('content-type')}")
    check("XLSX has data (>100 bytes)", len(r_xlsx.content) > 100,
          f"size={len(r_xlsx.content)}")

    # ── 9. Charts ───────────────────────────────────────────
    print("\n--- 9. Chart types ---")
    chart_tests = [
        ("bar",         {"chart_type": "bar",        "x": "Department", "agg": "count"},            "labels"),
        ("line",        {"chart_type": "line",       "x": "Department", "y": "Salary", "agg": "mean"}, "labels"),
        ("scatter",     {"chart_type": "scatter",    "x": "Department", "y": "Salary", "agg": "mean"}, "labels"),
        ("pie",         {"chart_type": "pie",        "x": "Gender",     "agg": "count"},            "labels"),
        ("histogram",   {"chart_type": "histogram",  "x": "Salary"},                                "labels"),
        ("box_plot",    {"chart_type": "box_plot",   "x": "Salary"},                                "box_stats"),
        ("stacked_bar", {"chart_type": "stacked_bar","x": "Department", "y": "Gender"},             "series"),
    ]
    chart_data_results = {}
    for (name, params, key) in chart_tests:
        try:
            r_c = requests.get(
                f"{BASE}/datasets/{did}/chart-data",
                params={**params, "use_cleaned": "true"},
                headers=hdrs,
            )
            r_c.raise_for_status()
            d = r_c.json()
            ok = key in d and len(d[key]) > 0
            check(f"chart/{name} has {key}", ok, str(d.get(key, "missing"))[:120])
            chart_data_results[name] = d
        except Exception as e:
            check(f"chart/{name}", False, str(e))

    # ── 10. Chat endpoint ───────────────────────────────────
    print("\n--- 10. Chat endpoint ---")
    try:
        r_chat = requests.post(
            f"{BASE}/chat",
            headers={**hdrs, "Content-Type": "application/json"},
            json={
                "message": "How many rows are in this dataset?",
                "dataset_id": did,
            },
            timeout=30,
        )
        check("Chat (200)", r_chat.status_code == 200, f"got {r_chat.status_code}")
        chat_data = r_chat.json()
        check("Chat has reply", bool(chat_data.get("reply")),
              f"keys={list(chat_data.keys())}")
        print(f"    Chat reply (excerpt): {chat_data.get('reply', '')[:150]}")
    except Exception as e:
        check("Chat endpoint", False, str(e))

    # ── 11. Unauthenticated requests must fail ──────────────
    print("\n--- 11. Unauthenticated requests → 401/403 ---")
    r_noauth_list = requests.get(f"{BASE}/datasets")
    check("Unauthed /datasets → 401/403",
          r_noauth_list.status_code in (401, 403),
          f"got {r_noauth_list.status_code}")

    r_noauth_upload = requests.post(
        f"{BASE}/upload",
        files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
    )
    check("Unauthed /upload → 401/403",
          r_noauth_upload.status_code in (401, 403),
          f"got {r_noauth_upload.status_code}")

    return did


# ─────────────────────────────────────────────────────────────
# PHASE 5c: npm run build check
# ─────────────────────────────────────────────────────────────

def test_build():
    """Check that `npm run build` still succeeds."""
    print("\n" + "=" * 64)
    print("  PHASE 5c: FRONTEND BUILD CHECK")
    print("=" * 64)

    import subprocess
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
    frontend_dir = os.path.abspath(frontend_dir)
    if not os.path.isdir(frontend_dir):
        check("Frontend dir exists", False, f"not found: {frontend_dir}")
        return

    print(f"    Running npm run build in {frontend_dir}...")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )
        check("npm run build exits 0", result.returncode == 0,
              f"rc={result.returncode}\nstderr: {result.stderr[:500]}")
        if result.returncode == 0:
            # Check dist exists
            dist_dir = os.path.join(frontend_dir, "dist")
            check("dist/ directory created", os.path.isdir(dist_dir))
    except Exception as e:
        check("npm run build", False, str(e))


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  PHASE 5 — FULL TWO-USER ISOLATION + REGRESSION TEST")
    print(f"  Run ID: {RUN_ID}")
    print(f"  User A: {USER_A_EMAIL}")
    print(f"  User B: {USER_B_EMAIL}")
    print("=" * 64)

    # Check backend is up
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        assert r.status_code == 200
        print("  Backend is healthy ✓")
    except Exception as e:
        print(f"\n  ❌ FATAL: Backend not reachable at {BASE} — {e}")
        sys.exit(1)

    # 5a: Two-user isolation
    result = test_two_user_isolation()
    if result is None:
        print("\n  ⚠️  Two-user isolation test could not complete (auth setup failed)")
    else:
        token_a, dataset_a_id, user_a_id = result

        # 5b: Full regression under User A's auth session
        test_full_regression(token_a, dataset_a_id)

    # 5c: Build check
    test_build()

    # ─── Final Summary ──────────────────────────────────────
    print("\n")
    print("=" * 64)
    print("  FINAL RESULTS")
    print("=" * 64)
    print(f"  PASSED: {len(PASS)}")
    print(f"  FAILED: {len(FAIL)}")

    # Categorize isolation-specific checks
    isolation_labels = [
        "User A ≠ User B (different IDs)",
        "User B does NOT see User A's dataset",
        "User B → User A's /profile returns 403",
        "User B → User A's /suggestions returns 403",
        "User B → User A's POST /pipeline returns 403",
        "User B → User A's POST /apply returns 403",
        "User B → User A's POST /preview returns 403",
        "User B → User A's /download-cleaned returns 403 or 404",
        "User B → User A's /chart-data returns 403",
        "User B still cannot see User A's dataset",
        "User A still sees their own dataset after re-login",
        "User A cannot see User B's dataset",
        "Unauthed /datasets → 401/403",
        "Unauthed /upload → 401/403",
    ]

    iso_passed = [l for l in isolation_labels if l in PASS]
    iso_failed = [l for l in isolation_labels if l in FAIL]

    print(f"\n  🔐 SECURITY / ISOLATION CHECKS:")
    print(f"     Passed: {len(iso_passed)} / {len(iso_passed) + len(iso_failed)}")
    if iso_failed:
        print("     FAILED:")
        for f_ in iso_failed:
            print(f"       ❌ {f_}")
    else:
        print("     ✅ ALL ISOLATION CHECKS PASSED")

    regression_items = [l for l in PASS + FAIL if l not in isolation_labels]
    reg_passed = [l for l in regression_items if l in PASS]
    reg_failed = [l for l in regression_items if l in FAIL]
    print(f"\n  📋 REGRESSION CHECKS (under auth):")
    print(f"     Passed: {len(reg_passed)} / {len(reg_passed) + len(reg_failed)}")
    if reg_failed:
        print("     FAILED:")
        for f_ in reg_failed:
            print(f"       ❌ {f_}")
    else:
        print("     ✅ ALL REGRESSION CHECKS PASSED")

    if FAIL:
        print("\n  ──── ALL FAILURES ────")
        for f_ in FAIL:
            print(f"    ❌ {f_}")
        print(f"\n  ❌ OVERALL: {len(FAIL)} FAILURE(S)")
        sys.exit(1)
    else:
        print("\n  ✅ ✅ ✅  ALL TESTS PASSED — PHASE 5 COMPLETE  ✅ ✅ ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
