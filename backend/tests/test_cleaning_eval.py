"""
Permanent regression test suite for data-cleaning quality & Do-No-Harm guarantees.
Covers all bug classes from the Master Prompt:
  - Messy 120-row dataset (SCORE >= 90%, COLLATERAL == 0)
  - Idempotency (0 changes, 0 flags on rerun)
  - Pristine dataset (0 changes, 0 flags on valid tricky rows)
  - ID collision reassignment + flag
  - Possible duplicates (same email/phone) flagged, never deleted
  - No row deletion for blank names / missing values
  - Number words ("Twenty", "Ten") + Int64 dtype
  - Date ambiguity (<=12 flagged, never guessed; >12 disambiguated; impossible blanked; suspect year flagged)
  - Coordinate bounds (lat [-90,90], lon [-180,180]; valid negative coords preserved)
  - City aliases & category clustering
  - Active/Inactive & negative-prefix non-merge guardrail (rules & AI)
  - Phone stays text & no PII fill
  - Gemini failure / invalid key / bad JSON graceful fallback with visible note
  - Cleaning log CSV & real download endpoints (CSV, XLSX via openpyxl, log)
"""
from __future__ import annotations

import io
import os
from unittest.mock import patch, MagicMock

import openpyxl
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.profiling import profile_dataframe
from app.cleaning import (
    apply_pipeline,
    cluster_categorical_column,
    cleaning_log_to_csv_bytes,
    is_antonym_or_prefix_pair,
    suggest_cleaning_steps,
)
from app.ai_suggestions import (
    _build_mapping_from_ai_groups,
    generate_ai_suggestions,
)
from tests.cleaning_eval.score import (
    check_idempotency,
    check_pristine,
    compute_collateral_damage,
    evaluate,
    run_pipeline_on_dataframe,
)


MESSY_XLSX = os.path.join(
    os.path.dirname(__file__),
    "cleaning_eval",
    "messy_project_testing_dataset_120_rows.xlsx",
)


def test_messy_dataset_score_and_zero_collateral():
    raw_df = pd.read_excel(MESSY_XLSX)
    cleaned_df, _ = run_pipeline_on_dataframe(raw_df)
    res = evaluate(cleaned_df, raw_df)
    score_pct = res["score"]
    assert score_pct >= 90.0, f"Expected score >= 90%, got {score_pct:.2f}%"
    collat_cnt, details = compute_collateral_damage(raw_df, cleaned_df)
    assert collat_cnt == 0, f"Expected 0 collateral damage, got {collat_cnt}: {details}"
    assert len(cleaned_df) == 117
    assert cleaned_df["Record_ID"].nunique() == 117
    assert str(cleaned_df["Age"].dtype) == "Int64"
    assert str(cleaned_df["Quantity"].dtype) == "Int64"
    assert str(cleaned_df["Phone"].dtype) == "object"


def test_idempotency():
    raw_df = pd.read_excel(MESSY_XLSX)
    cleaned_df, _ = run_pipeline_on_dataframe(raw_df)
    passed, msg = check_idempotency(cleaned_df)
    assert passed, f"Idempotency failed: {msg}"


def test_pristine_dataset_zero_changes_zero_flags():
    passed, msg = check_pristine()
    assert passed, f"Pristine dataset failed: {msg}"


def test_collision_ids_reassigned_and_flagged():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1001", None],
        "Customer_Name": ["Alice", "Bob", "Charlie", "Diana"],
        "Email": ["a@example.com", "b@example.com", "c@example.com", "d@example.com"],
    })
    cleaned, _ = run_pipeline_on_dataframe(df)
    assert len(cleaned) == 4
    assert cleaned.iloc[0]["Record_ID"] == "REC-1001"
    assert cleaned.iloc[1]["Record_ID"] == "REC-1002"
    assert cleaned.iloc[2]["Record_ID"] == "REC-1003"
    assert cleaned.iloc[3]["Record_ID"] == "REC-1004"
    assert cleaned["Record_ID"].nunique() == 4
    assert cleaned["Record_ID"].isna().sum() == 0
    assert list(cleaned["Record_ID_flag_reassigned"]) == [False, False, True, True]


def test_possible_duplicates_flagged_never_deleted():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003", "REC-1004"],
        "Customer_Name": ["Alice", "Alice Smith", "Bob", "Carol"],
        "Email": ["alice@example.com", "alice@example.com", "bob@example.com", "carol@example.com"],
        "City": ["Mumbai", "Pune", "Delhi", "Chennai"],
    })
    cleaned, _ = run_pipeline_on_dataframe(df)
    assert len(cleaned) == 4  # NEVER deleted
    assert "_flag_possible_duplicate" in cleaned.columns
    assert list(cleaned["_flag_possible_duplicate"]) == [True, True, False, False]


def test_no_row_deletion_for_blanks():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003"],
        "Customer_Name": ["Alice", None, ""],
        "Email": ["a@example.com", None, "c@example.com"],
        "City": ["Bengaluru", "Delhi", None],
    })
    cleaned, _ = run_pipeline_on_dataframe(df)
    assert len(cleaned) == 3
    assert pd.isna(cleaned.iloc[1]["Customer_Name"])
    assert pd.isna(cleaned.iloc[2]["Customer_Name"])
    assert pd.isna(cleaned.iloc[1]["Email"])
    assert pd.isna(cleaned.iloc[2]["City"])
    assert bool(cleaned.iloc[1]["Customer_Name_flag_missing"]) is True
    assert bool(cleaned.iloc[1]["Email_flag_missing"]) is True
    assert bool(cleaned.iloc[2]["City_flag_missing"]) is True


def test_number_words_parsed_and_int64():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003"],
        "Age": ["Twenty", 35, 150],
        "Quantity": ["Ten", 0, -3],
    })
    cleaned, _ = run_pipeline_on_dataframe(df)
    assert int(cleaned.iloc[0]["Age"]) == 20
    assert int(cleaned.iloc[1]["Age"]) == 35
    assert pd.isna(cleaned.iloc[2]["Age"])
    assert bool(cleaned.iloc[2]["Age_flag_invalid"]) is True
    assert str(cleaned["Age"].dtype) == "Int64"

    assert int(cleaned.iloc[0]["Quantity"]) == 10
    assert int(cleaned.iloc[1]["Quantity"]) == 0
    assert bool(cleaned.iloc[1]["Quantity_flag_zero"]) is True
    assert int(cleaned.iloc[2]["Quantity"]) == -3
    assert bool(cleaned.iloc[2]["Quantity_flag_negative"]) is True
    assert str(cleaned["Quantity"].dtype) == "Int64"

    cell_log = cleaned.attrs.get("cleaning_log", [])
    assert any(e["rule"] == "number_word_to_int" and e["old"] == "Twenty" and e["new"] == "20" for e in cell_log)


def test_date_ambiguity_and_bounds():
    # Case A: All dates <= 12 -> AMBIGUOUS, must flag and NOT guess
    df_ambig = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003"],
        "Purchase_Date": ["05/06/2026", "01/02/2026", "2026-15-45"],
    })
    cleaned_a, _ = run_pipeline_on_dataframe(df_ambig)
    assert cleaned_a.iloc[0]["Purchase_Date"] == "05/06/2026"
    assert bool(cleaned_a.iloc[0]["Purchase_Date_flag_ambiguous"]) is True
    assert pd.isna(cleaned_a.iloc[2]["Purchase_Date"])
    assert bool(cleaned_a.iloc[2]["Purchase_Date_flag_invalid"]) is True

    # Case B: One date has first part > 12 -> column treated as DD/MM; suspect year flagged
    df_dmy = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003", "REC-1004"],
        "Purchase_Date": ["15/03/2026", "05/06/2026", "1850-01-01", "not available"],
    })
    cleaned_b, _ = run_pipeline_on_dataframe(df_dmy)
    assert cleaned_b.iloc[0]["Purchase_Date"] == "2026-03-15"
    assert cleaned_b.iloc[1]["Purchase_Date"] == "2026-06-05"
    assert bool(cleaned_b.iloc[2]["Purchase_Date_flag_suspect"]) is True
    assert pd.isna(cleaned_b.iloc[3]["Purchase_Date"])
    assert bool(cleaned_b.iloc[3]["Purchase_Date_flag_invalid"]) is True


def test_coordinate_bounds_and_valid_negative_coords():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003", "REC-1004"],
        "Latitude": [-33.8688, 123.456, -200.0, "unknown"],
        "Longitude": [-74.006, 250.123, -500.0, 77.5946],
    })
    cleaned, _ = run_pipeline_on_dataframe(df)
    # Valid negative coordinates (Sydney / NYC) must stay untouched and NOT flagged negative!
    assert round(float(cleaned.iloc[0]["Latitude"]), 4) == -33.8688
    assert round(float(cleaned.iloc[0]["Longitude"]), 4) == -74.006
    assert "Latitude_flag_negative" not in cleaned.columns
    assert "Longitude_flag_negative" not in cleaned.columns
    # Out-of-bounds blanked + flagged invalid
    assert pd.isna(cleaned.iloc[1]["Latitude"])
    assert bool(cleaned.iloc[1]["Latitude_flag_invalid"]) is True
    assert pd.isna(cleaned.iloc[2]["Latitude"])
    assert bool(cleaned.iloc[2]["Latitude_flag_invalid"]) is True
    assert pd.isna(cleaned.iloc[3]["Latitude"])
    assert pd.isna(cleaned.iloc[1]["Longitude"])
    assert bool(cleaned.iloc[1]["Longitude_flag_invalid"]) is True
    assert pd.isna(cleaned.iloc[2]["Longitude"])
    assert bool(cleaned.iloc[2]["Longitude_flag_invalid"]) is True


def test_city_aliases_and_category_clustering():
    cities = pd.Series(
        ["Bengaluru"] * 10 + ["Bangalore", " Bangalore ", "bengaluru", "Mumbai", "Mumbai", "Mumbai", "Mum bai", "Delhi", "DELHI"]
    )
    res_city = cluster_categorical_column(cities)
    assert res_city["mapping"]["Bangalore"] == "Bengaluru"
    assert res_city["mapping"][" Bangalore "] == "Bengaluru"
    assert res_city["mapping"]["bengaluru"] == "Bengaluru"
    assert res_city["mapping"]["Mum bai"] == "Mumbai"
    assert res_city["mapping"]["DELHI"] == "Delhi"
    assert "Bengaluru" not in res_city["mapping"]

    cats = pd.Series(
        ["Groceries"] * 10 + ["Grocery"] + ["Electronics"] * 10 + ["Eletronics", "electronics"]
    )
    res_cat = cluster_categorical_column(cats)
    assert res_cat["mapping"]["Grocery"] == "Groceries"
    assert res_cat["mapping"]["Eletronics"] == "Electronics"
    assert res_cat["mapping"]["electronics"] == "Electronics"


def test_active_inactive_never_merge():
    assert is_antonym_or_prefix_pair("Active", "Inactive") is True
    assert is_antonym_or_prefix_pair("Valid", "Invalid") is True
    assert is_antonym_or_prefix_pair("Paid", "Unpaid") is True

    s = pd.Series(["Active"] * 20 + ["Inactive"] * 2)
    res = cluster_categorical_column(s)
    assert res["mapping"] == {}

    # Even if AI proposes merging Inactive -> Active, guardrail rejects it!
    ai_groups = [{
        "canonical": "Active",
        "variants": [{"value": "Inactive", "confidence": "high"}],
        "reasoning": "test bad AI merge",
    }]
    mapping, _, _, _ = _build_mapping_from_ai_groups(ai_groups, s, len(s))
    assert "Inactive" not in mapping


def test_phone_stays_text_and_no_pii_fill():
    df = pd.DataFrame({
        "Record_ID": ["REC-1001", "REC-1002", "REC-1003"],
        "Phone": ["+91-98765-43210", "12345", None],
        "Email": [" user@example.com ", "invalidemail", None],
    })
    prof = profile_dataframe(df)
    sugs = suggest_cleaning_steps(df, prof)
    # No fill_missing offered for Phone or Email
    for s in sugs:
        if s["action"] == "fill_missing":
            assert s["params"].get("column") not in ("Phone", "Email")

    cleaned, _ = run_pipeline_on_dataframe(df)
    assert str(cleaned["Phone"].dtype) == "object"
    assert cleaned.iloc[0]["Phone"] == "9876543210"
    assert pd.isna(cleaned.iloc[1]["Phone"])
    assert pd.isna(cleaned.iloc[2]["Phone"])
    assert cleaned.iloc[0]["Email"] == "user@example.com"
    assert pd.isna(cleaned.iloc[1]["Email"])
    assert pd.isna(cleaned.iloc[2]["Email"])


def test_gemini_down_and_bad_json_fallback():
    df = pd.read_excel(MESSY_XLSX).head(20)
    prof = profile_dataframe(df)

    # 1. Invalid API key / Gemini network failure -> rules-only with visible note
    with patch.dict(os.environ, {"GEMINI_API_KEY": "INVALID_KEY_FOR_TEST"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = RuntimeError("403 Invalid API key")
            mock_client_cls.return_value = mock_client

            res = generate_ai_suggestions(df, prof)
            assert res["source"] == "rule_based_fallback"
            assert len(res["column_results"]) == len(df.columns)
            assert any("deterministic rules" in n.lower() for n in res.get("general_notes", []))

    # 2. Bad JSON from Gemini -> rules-only with visible note, never crashes
    with patch.dict(os.environ, {"GEMINI_API_KEY": "BAD_JSON_KEY"}):
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            bad_resp = MagicMock()
            bad_resp.text = "{not valid json!!!"
            mock_client.models.generate_content.return_value = bad_resp
            mock_client_cls.return_value = mock_client

            res = generate_ai_suggestions(df, prof)
            assert res["source"] == "rule_based_fallback"
            assert len(res["column_results"]) == len(df.columns)


def test_cleaning_log_and_download_endpoints():
    client = TestClient(app)
    with open(MESSY_XLSX, "rb") as f:
        raw_bytes = f.read()

    up = client.post(
        "/upload",
        files={"file": ("messy_120.xlsx", io.BytesIO(raw_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert up.status_code == 200
    dataset_id = up.json()["dataset_id"]

    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        sug_res = client.get(f"/datasets/{dataset_id}/suggestions")
    assert sug_res.status_code == 200
    sug = sug_res.json()

    # Build steps mirroring UI high/medium selection
    steps = []
    for ds_issue in sug.get("dataset_issues", []):
        if ds_issue.get("severity") in ("high", "medium"):
            steps.append({
                "action": ds_issue["action"],
                "params": ds_issue.get("params", {}),
                "description": ds_issue.get("description", ""),
                "severity": ds_issue.get("severity", "medium"),
            })
    for col in sug.get("column_results", []):
        cat_an = col.get("categorical_analysis") or {}
        if cat_an.get("mapping"):
            steps.append({
                "action": "standardize_category",
                "params": {"column": col["name"], "mapping": cat_an["mapping"]},
                "description": f"Standardize {col['name']}",
                "severity": "medium",
            })
        date_an = col.get("date_analysis")
        if date_an:
            tfmt = date_an.get("default_style", "YYYY-MM-DD")
            vmap = {it["raw"]: it["formats"][tfmt] for it in date_an.get("date_items", []) if not it.get("ambiguous") and it.get("formats", {}).get(tfmt)}
            if vmap:
                steps.append({
                    "action": "standardize_date_format",
                    "params": {"column": col["name"], "target_format": tfmt, "value_map": vmap},
                    "description": f"Standardize date {col['name']}",
                    "severity": "medium",
                })
        for iss in col.get("issues", []):
            if iss.get("action") not in ("standardize_category", "standardize_date_format") and iss.get("severity") in ("high", "medium"):
                steps.append({
                    "action": iss["action"],
                    "params": iss.get("params", {}),
                    "description": iss.get("description", ""),
                    "severity": iss.get("severity", "medium"),
                })

    pipe = client.post(f"/datasets/{dataset_id}/pipeline", json=steps)
    assert pipe.status_code == 200

    app_res = client.post(f"/datasets/{dataset_id}/apply")
    assert app_res.status_code == 200
    assert app_res.json()["cleaned_row_count"] == 117
    assert app_res.json()["cleaning_log_count"] > 0

    # Download CSV
    csv_res = client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
    assert csv_res.status_code == 200
    csv_df = pd.read_csv(io.BytesIO(csv_res.content), dtype={"Phone": str, "Record_ID": str})
    assert len(csv_df) == 117
    assert not any(str(v).endswith(".0") for v in csv_df["Phone"].dropna())

    # Download Excel and verify via openpyxl
    xlsx_res = client.get(f"/datasets/{dataset_id}/download-cleaned?format=xlsx")
    assert xlsx_res.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_res.content))
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    phone_col_idx = headers.index("Phone") + 1
    phone_letter = openpyxl.utils.get_column_letter(phone_col_idx)
    assert ws.column_dimensions[phone_letter].width >= 14
    for r in range(2, ws.max_row + 1):
        cell = ws.cell(r, phone_col_idx)
        assert cell.number_format == "@"
        if cell.value is not None and str(cell.value) != "":
            assert isinstance(cell.value, str)
            assert not cell.value.endswith(".0")

    # Download Cleaning Log CSV
    log_res = client.get(f"/datasets/{dataset_id}/download-cleaned?format=log")
    assert log_res.status_code == 200
    log_df = pd.read_csv(io.BytesIO(log_res.content))
    assert list(log_df.columns) == ["row_id", "column", "old", "new", "rule", "confidence", "source", "timestamp"]
    assert len(log_df) >= 35
