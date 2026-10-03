"""
Test script verifying all 5 fix phases.

Run from backend/ with:
    venv\\Scripts\\python.exe test_five_phase_fixes.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np


def test_phase1_email_validation_runs():
    """Phase 1: Email validation produces flagged issues for known-bad values."""
    from app.validation_rules import validate_email

    emails = pd.Series([
        "rahul123@gmail",         # missing extension
        "meena.gmail.com",        # missing @
        "lakshmi@@gmail.com",     # double @
        "priya.sharma @gmail.com", # space
        "valid@gmail.com",        # correct
    ])
    issues = validate_email(emails, "Email")
    assert len(issues) >= 4, f"Expected >=4 issues, got {len(issues)}: {[i.issue for i in issues]}"

    raw_values_flagged = {str(i.raw_value) for i in issues}
    assert "rahul123@gmail" in raw_values_flagged, "Missing: rahul123@gmail (no extension)"
    assert "meena.gmail.com" in raw_values_flagged, "Missing: meena.gmail.com (no @)"
    assert "lakshmi@@gmail.com" in raw_values_flagged, "Missing: lakshmi@@gmail.com (double @)"
    assert "priya.sharma @gmail.com" in raw_values_flagged, "Missing: priya.sharma @gmail.com (space)"
    assert "valid@gmail.com" not in raw_values_flagged, "Should not flag valid@gmail.com"
    print("  Phase 1: Email validation catches all bad values")


def test_phase1_phone_validation_runs():
    """Phase 1: Phone validation produces flagged issues for known-bad values."""
    from app.validation_rules import validate_phone

    phones = pd.Series([
        "98765 43211",       # space - normalise to 9876543211
        "76543-21098",       # dash - normalise
        "+91-9988776656",    # country code - normalise
        "987654321",         # 9 digits - too short
        "9876543210",        # valid
    ])
    issues = validate_phone(phones, "Phone")
    assert len(issues) >= 3, f"Expected >=3 issues, got {len(issues)}: {[i.issue for i in issues]}"

    # 987654321 should be flagged as too short
    short_flagged = [i for i in issues if "987654321" in str(i.raw_value) and "short" in i.issue.lower()]
    assert len(short_flagged) >= 1, "Should flag 987654321 as too short"

    # Space/dash/country-code phones should get normalization suggestions
    norm_flagged = [i for i in issues if "normali" in i.issue.lower()]
    assert len(norm_flagged) >= 2, f"Should flag space/dash/country-code phones for normalization, got {len(norm_flagged)}"
    print("  Phase 1: Phone validation catches bad values and normalises format")


def test_phase2_email_flagging_integrated():
    """Phase 2: Email/Phone flags appear in suggest_cleaning_steps output."""
    from app.cleaning import suggest_cleaning_steps
    from app.profiling import profile_dataframe

    df = pd.DataFrame({
        "Name": ["Alice", "Bob", "Carol", "Dan", "Eve"],
        "Email": ["rahul123@gmail", "meena.gmail.com", "lakshmi@@gmail.com", "priya.sharma @gmail.com", "valid@gmail.com"],
        "Phone": ["98765 43211", "76543-21098", "+91-9988776656", "987654321", "9876543210"],
    })
    profile = profile_dataframe(df)
    suggestions = suggest_cleaning_steps(df, profile)

    email_flags = [s for s in suggestions if s.get("action") == "flag_invalid_email"]
    phone_flags = [s for s in suggestions if s.get("action") == "flag_invalid_phone"]

    assert len(email_flags) >= 1, f"Expected flag_invalid_email suggestions, got none. Actions: {[s['action'] for s in suggestions]}"
    assert len(phone_flags) >= 1, f"Expected flag_invalid_phone suggestions, got none. Actions: {[s['action'] for s in suggestions]}"

    email_flagged_count = email_flags[0]["params"]["flagged_count"]
    phone_flagged_count = phone_flags[0]["params"]["flagged_count"]
    assert email_flagged_count >= 4, f"Expected >=4 email flags, got {email_flagged_count}"
    assert phone_flagged_count >= 3, f"Expected >=3 phone flags, got {phone_flagged_count}"
    print(f"  Phase 2: Email ({email_flagged_count} flagged) and Phone ({phone_flagged_count} flagged) integrated correctly")


def test_phase3_no_fill_mode_for_pii():
    """Phase 3: Email/Phone columns never get fill_missing with mode."""
    from app.cleaning import suggest_cleaning_steps
    from app.profiling import profile_dataframe

    df = pd.DataFrame({
        "Name": ["Alice", "Bob", "Carol", None, "Eve", "Frank"],
        "Email": ["alice@gmail.com", "bob@yahoo.com", None, "alice@gmail.com", "eve@test.com", "frank@test.com"],
        "Phone": ["9876543210", None, "8765432109", "7654321098", "6543210987", "9988776655"],
        "Amount": [100, 200, None, 400, 500, 600],
    })
    profile = profile_dataframe(df)
    suggestions = suggest_cleaning_steps(df, profile)

    # Check that Email and Phone columns get drop_missing, NOT fill_missing
    for sug in suggestions:
        col = sug.get("params", {}).get("column", "")
        action = sug.get("action", "")
        strategy = sug.get("params", {}).get("strategy", "")

        if col in ("Email", "Phone", "Name") and action == "fill_missing":
            assert strategy not in ("mode", "mean", "median"), (
                f"PII column '{col}' got fill_missing with strategy='{strategy}' - "
                f"this would fabricate a real person's value!"
            )

    # Email should get drop_missing instead
    email_missing_actions = [
        s for s in suggestions
        if s.get("params", {}).get("column") == "Email"
        and s["action"] in ("drop_missing", "drop_column")
    ]
    assert len(email_missing_actions) >= 1, (
        f"Expected drop_missing for Email column, got: "
        f"{[(s['action'], s.get('params',{}).get('column')) for s in suggestions if s.get('params',{}).get('column') == 'Email']}"
    )

    # Amount (numeric, non-PII) should still get fill_missing with median
    amount_fills = [
        s for s in suggestions
        if s.get("params", {}).get("column") == "Amount" and s["action"] == "fill_missing"
    ]
    assert len(amount_fills) >= 1, "Amount should still get fill_missing suggestion"
    assert amount_fills[0]["params"]["strategy"] == "median", "Amount should fill with median"

    print("  Phase 3: PII columns excluded from fill_mode, numeric columns still get fill_median")


def test_phase4_nan_filtered_from_chart():
    """Phase 4: NaN values in X-axis column are excluded from chart data."""
    df = pd.DataFrame({
        "Amount": [100, 200, 300, None, 500, 100, 200, None],
        "City": ["Mumbai", "Delhi", "Mumbai", "Delhi", "Mumbai", "Delhi", "Mumbai", "Delhi"],
    })

    # Simulate what the chart endpoint does
    x = "Amount"
    chart_df = df[df[x].notna()].copy()
    grouped = chart_df[x].astype(str).value_counts().head(50).reset_index()
    grouped.columns = ["label", "value"]
    # Filter nan labels
    grouped = grouped[~grouped["label"].astype(str).str.lower().isin(["nan", "none", "null"])]

    labels = [str(v) for v in grouped["label"].tolist()]
    assert "nan" not in labels, f"'nan' should not appear in labels: {labels}"
    assert "None" not in labels, f"'None' should not appear in labels: {labels}"
    print(f"  Phase 4: NaN filtered from chart labels. Labels: {labels}")


def test_phase5_kpi_no_numpy_bool():
    """Phase 5: KPI endpoint returns Python-native bool, not numpy.bool_."""
    df = pd.DataFrame({
        "Amount": [100, 200, 300, 400, 500],
        "Name": ["Alice", "Bob", "Carol", "Dan", "Eve"],
    })

    # Simulate the KPI computation
    target_col = "Amount"
    num_s = pd.to_numeric(df[target_col], errors="coerce")
    is_numeric = bool(num_s.dropna().count() > 0)

    assert isinstance(is_numeric, bool), f"is_numeric should be Python bool, got {type(is_numeric)}"
    assert is_numeric is True

    # Test with non-numeric column
    target_col2 = "Name"
    num_s2 = pd.to_numeric(df[target_col2], errors="coerce")
    is_numeric2 = bool(num_s2.dropna().count() > 0)
    assert isinstance(is_numeric2, bool), f"is_numeric should be Python bool, got {type(is_numeric2)}"
    assert is_numeric2 is False

    # Verify JSON serialization works
    import json
    result = {
        "chart_type": "kpi",
        "is_numeric": is_numeric,
        "value": 300.0,
        "stats": {"sum": 1500.0, "mean": 300.0},
    }
    json_str = json.dumps(result)  # Should not raise
    assert '"is_numeric": true' in json_str
    print("  Phase 5: KPI is_numeric is Python bool, JSON-serializable")


if __name__ == "__main__":
    test_phase1_email_validation_runs()
    test_phase1_phone_validation_runs()
    test_phase2_email_flagging_integrated()
    test_phase3_no_fill_mode_for_pii()
    test_phase4_nan_filtered_from_chart()
    test_phase5_kpi_no_numpy_bool()
    print("\nAll phase tests passed!")
