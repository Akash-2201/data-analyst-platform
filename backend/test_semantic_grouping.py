"""
End-to-end test: verify AI-driven semantic grouping correctly separates
Active/Inactive (opposite meanings) while merging typos (active → Active, ACTVE → Active).

Also tests the preview endpoint to confirm before/after value counts are sane.

Usage:
    cd backend
    python test_semantic_grouping.py
"""

from __future__ import annotations

import json
import os
import sys

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env BEFORE importing app modules (they check GEMINI_API_KEY at call time)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import pandas as pd

from app.ai_suggestions import generate_ai_suggestions
from app.cleaning import apply_pipeline
from app.profiling import profile_dataframe


def build_test_dataframe() -> pd.DataFrame:
    """Recreate the exact Status column that triggered the Active/Inactive merge bug."""
    statuses = (
        ["Active"] * 30
        + ["Inactive"] * 24
        + ["active"] * 1   # case typo → should merge into Active
        + ["ACTVE"] * 1    # spelling typo → should merge into Active
    )
    # Add a simple numeric column so the profile is realistic
    df = pd.DataFrame({
        "Name": [f"Person_{i}" for i in range(len(statuses))],
        "Status": statuses,
        "Score": list(range(len(statuses))),
    })
    return df


def run_test():
    print("=" * 70)
    print("END-TO-END TEST: AI Semantic Grouping + Preview Safety Net")
    print("=" * 70)

    # ---- Step 1: Build test data ----
    df = build_test_dataframe()
    profile = profile_dataframe(df)
    print(f"\nDataFrame shape: {df.shape}")
    print(f"Status value counts BEFORE cleaning:")
    vc_before = df["Status"].value_counts().to_dict()
    print(json.dumps(vc_before, indent=2))

    # ---- Step 2: Generate AI suggestions ----
    print("\n--- Generating AI suggestions ---")
    result = generate_ai_suggestions(df, profile)
    source = result["source"]
    print(f"Source: {source}")

    # Find standardize_category suggestions for Status
    status_suggestions = [
        s for s in result["suggestions"]
        if s.get("action") == "standardize_category"
        and (s.get("params") or {}).get("column") == "Status"
    ]

    if not status_suggestions:
        print("\n⚠  No standardize_category suggestion for Status column.")
        print("   This could mean AI found no typos (unlikely with our test data) or an error occurred.")
        print(f"   All suggestions: {json.dumps(result['suggestions'], indent=2)}")
        return False

    for sug in status_suggestions:
        mapping = sug["params"].get("mapping", {})
        print(f"\nStandardize mapping for Status: {json.dumps(mapping, indent=2)}")
        print(f"Recommended: {sug.get('recommended', 'N/A')}")
        print(f"Description: {sug.get('description', 'N/A')}")
        if sug.get("ai_reason"):
            print(f"AI reason: {sug['ai_reason']}")

    # ---- Step 3: CRITICAL CHECK — Active and Inactive must NEVER be merged ----
    print("\n--- CRITICAL VALIDATION ---")
    combined_mapping = {}
    for sug in status_suggestions:
        combined_mapping.update(sug["params"].get("mapping", {}))

    # Check: no variant maps Active→Inactive or Inactive→Active
    bad_merges = []
    for variant, canonical in combined_mapping.items():
        vl = variant.strip().lower()
        cl = canonical.strip().lower()
        if ("active" in vl and "inactive" in cl) or ("inactive" in vl and "active" in cl):
            bad_merges.append(f"  {variant} → {canonical}")
        # Also check: "Inactive" should never be mapped to "Active"
        if vl == "inactive" and cl == "active":
            bad_merges.append(f"  {variant} → {canonical}")
        if vl == "active" and cl == "inactive":
            bad_merges.append(f"  {variant} → {canonical}")

    if bad_merges:
        print("❌ FAIL: Active/Inactive were incorrectly merged!")
        for bm in bad_merges:
            print(bm)
        return False
    else:
        print("✅ PASS: Active and Inactive are correctly separated (not merged).")

    # ---- Step 4: Preview — run the pipeline in memory and check before/after ----
    print("\n--- PREVIEW: Before/After Value Counts ---")

    # Build steps from all suggestions (simulate what the frontend sends)
    steps = [
        {
            "action": s["action"],
            "params": s.get("params", {}),
            "description": s.get("description", ""),
            "severity": s.get("severity", "medium"),
        }
        for s in result["suggestions"]
        if s.get("action") == "standardize_category"
        and (s.get("params") or {}).get("column") == "Status"
    ]

    cleaned_df, log = apply_pipeline(df, steps)

    vc_after = cleaned_df["Status"].value_counts().to_dict()
    print(f"\nStatus value counts AFTER cleaning:")
    print(json.dumps(vc_after, indent=2))

    print(f"\nPreview JSON (what the /preview endpoint would return):")
    preview_output = {
        "column": "Status",
        "before": {str(k): int(v) for k, v in vc_before.items()},
        "after": {str(k): int(v) for k, v in vc_after.items()},
    }
    print(json.dumps(preview_output, indent=2))

    # ---- Step 5: Validate the numbers ----
    print("\n--- NUMERICAL VALIDATION ---")
    active_before = vc_before.get("Active", 0)
    active_after = vc_after.get("Active", 0)
    inactive_before = vc_before.get("Inactive", 0)
    inactive_after = vc_after.get("Inactive", 0)

    # Active should go up by ~2 (absorbing "active" and "ACTVE" typos)
    expected_active = active_before + vc_before.get("active", 0) + vc_before.get("ACTVE", 0)
    # Inactive should stay the same
    expected_inactive = inactive_before

    print(f"Active:   {active_before} → {active_after}  (expected: {expected_active})")
    print(f"Inactive: {inactive_before} → {inactive_after}  (expected: {expected_inactive})")

    checks_passed = True
    if active_after != expected_active:
        print(f"❌ Active count mismatch: got {active_after}, expected {expected_active}")
        checks_passed = False
    else:
        print("✅ Active count correct (typos absorbed)")

    if inactive_after != expected_inactive:
        print(f"❌ Inactive count mismatch: got {inactive_after}, expected {expected_inactive}")
        checks_passed = False
    else:
        print("✅ Inactive count unchanged (correctly not merged)")

    # Typo values should be gone
    remaining_typos = [v for v in ("active", "ACTVE") if v in vc_after]
    if remaining_typos:
        print(f"❌ Typo values still present: {remaining_typos}")
        checks_passed = False
    else:
        print("✅ Typo values ('active', 'ACTVE') cleaned up")

    print("\n" + "=" * 70)
    if checks_passed:
        print("ALL CHECKS PASSED ✅")
    else:
        print("SOME CHECKS FAILED ❌")
    print("=" * 70)

    return checks_passed


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
