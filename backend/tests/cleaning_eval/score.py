"""
Scoring harness for data cleaning evaluation.
Evaluates cleaning output on messy_project_testing_dataset_120_rows.xlsx against expected assertions,
checks for collateral damage on valid cells, verifies idempotency, and tests pristine dataset preservation.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Any

# Ensure backend is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pandas as pd
from tests.cleaning_eval.expected import get_expected_cases
from tests.cleaning_eval.pristine_generator import generate_pristine_dataset
from app.profiling import profile_dataframe
from app.ai_suggestions import _generate_rule_based_pipeline
from app.cleaning import apply_pipeline


def run_pipeline_on_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Run the current cleaning pipeline end-to-end on a DataFrame."""
    profile = profile_dataframe(df)
    sug = _generate_rule_based_pipeline(df, profile)

    steps = []
    # 1. Dataset issues (severity high/medium)
    for ds_issue in sug.get("dataset_issues", []):
        if ds_issue.get("severity") in ["high", "medium"]:
            steps.append({
                "action": ds_issue["action"],
                "params": ds_issue.get("params", {}),
                "description": ds_issue.get("description", ""),
            })

    # 2. Categorical mappings (high confidence or recommended)
    for col in sug.get("column_results", []):
        col_name = col["name"]
        cat_an = col.get("categorical_analysis") or {}
        mapping = cat_an.get("mapping") or col.get("mapping") or {}
        confidences = cat_an.get("variant_confidences") or (col.get("extra_info") or {}).get("variant_confidences", {})
        if not mapping:
            for iss in col.get("issues", []):
                if iss.get("action") == "standardize_category" and iss.get("recommended", True):
                    p = iss.get("params") or {}
                    mapping = p.get("mapping") or {}
                    confidences = p.get("variant_confidences") or {}
                    break
        approved_map = {}
        for raw_val, target in mapping.items():
            if confidences.get(raw_val) == "high":
                approved_map[raw_val] = target
            elif raw_val not in confidences and col.get("recommended", True):
                approved_map[raw_val] = target
        if approved_map:
            steps.append({
                "action": "standardize_category",
                "params": {"column": col_name, "mapping": approved_map},
            })

    # 3. Date analysis (non-ambiguous items)
    for col in sug.get("column_results", []):
        col_name = col["name"]
        date_analysis = col.get("date_analysis")
        if date_analysis:
            target_fmt = date_analysis.get("default_target_format", "YYYY-MM-DD")
            vmap = {}
            for item in date_analysis.get("date_items", []):
                if not item.get("ambiguous"):
                    target = item.get("formats", {}).get(target_fmt)
                    if target:
                        vmap[item["raw"]] = target
            if vmap:
                steps.append({
                    "action": "standardize_date_format",
                    "params": {"column": col_name, "target_format": target_fmt, "value_map": vmap},
                })

    # 4. Column issues (high/medium severity)
    for col in sug.get("column_results", []):
        for issue in col.get("issues", []):
            if issue.get("action") not in ["standardize_category", "standardize_date_format"]:
                if issue.get("severity") in ["high", "medium"]:
                    steps.append({
                        "action": issue["action"],
                        "params": issue.get("params", {}),
                        "description": issue.get("description", ""),
                    })

    cleaned_df, log = apply_pipeline(df, steps)
    return cleaned_df, log


def compute_collateral_damage(raw_df: pd.DataFrame, cleaned_df: pd.DataFrame) -> tuple[int, list[str]]:
    """
    Check if any cell that was already valid in raw was altered in cleaned_df.
    Returns (collateral_count, list_of_collateral_details).
    """
    # Set of known raw records/cells that were injected with issues
    INJECTED_CELLS = {
        ("REC-1002", "Customer_Name"),
        ("REC-1007", "Customer_Name"),
        ("REC-1019", "Customer_Name"),
        ("REC-1034", "Customer_Name"),
        ("REC-1092", "Customer_Name"),
        ("REC-1003", "Customer_Name"),
        ("REC-1057", "Customer_Name"),
        ("REC-1024", "Age"),
        ("REC-1004", "Age"),
        ("REC-1016", "Age"),
        ("REC-1090", "Email"),
        ("REC-1022", "Email"),
        ("REC-1011", "Email"),
        ("REC-1039", "Email"),
        ("REC-1014", "Email"),
        ("REC-1089", "Email"),
        ("REC-1047", "Phone"),
        ("REC-1009", "Phone"),
        ("REC-1028", "Phone"),
        ("REC-1029", "City"),
        ("REC-1044", "City"),
        ("REC-1033", "City"),
        ("REC-1071", "Category"),
        ("REC-1013", "Purchase_Date"),
        ("REC-1023", "Purchase_Date"),
        ("REC-1038", "Purchase_Date"),
        ("REC-1049", "Purchase_Date"),
        ("REC-1060", "Purchase_Date"),
        ("REC-1065", "Quantity"),
        ("REC-1063", "Quantity"),
        ("REC-1064", "Quantity"),
        ("REC-1030", "Amount"),
        ("REC-1055", "Amount"),
        ("REC-1080", "Latitude"),
        ("REC-1012", "Latitude"),
        ("REC-1031", "Latitude"),
        ("REC-1036", "Longitude"),
        ("REC-1048", "Longitude"),
    }

    # Also city variants that needed unification
    # (Bangalore, bengaluru, ' Bangalore ')
    # And category variants: 'electronics', 'Furniture ', 'Grocery'
    # These are not considered collateral damage when normalized.

    collateral_count = 0
    collateral_details = []

    # Map raw rows by Record_ID for clean comparison
    # Group raw by Record_ID (skip exact duplicate occurrences)
    raw_unique = raw_df.drop_duplicates()

    for _, raw_row in raw_unique.iterrows():
        rid = raw_row["Record_ID"]
        # Find corresponding row in cleaned_df
        # Match by email first (to handle colliding IDs cleanly), then by Record_ID
        email = str(raw_row.get("Email", "")).strip()
        cleaned_matches = pd.DataFrame()
        if email and email.lower() not in ["", "nan", "none"]:
            cleaned_matches = cleaned_df[cleaned_df["Email"].astype(str).str.strip() == email]
        if cleaned_matches.empty:
            cleaned_matches = cleaned_df[cleaned_df["Record_ID"] == rid]

        if cleaned_matches.empty:
            # Row was dropped - if it was not an exact duplicate, that's already counted in row count/cases
            continue

        cl_row = cleaned_matches.iloc[0]

        for col in raw_df.columns:
            if (rid, col) in INJECTED_CELLS:
                continue

            raw_val = raw_row[col]
            cl_val = cl_row.get(col)

            # Skip categorical/city/category injected variants when normalized canonically
            if col == "City" and (str(raw_val) in ["Bangalore", " Bangalore ", "bengaluru", "Chennai "] or str(raw_val).strip() in ["Bangalore", "bengaluru"]):
                continue
            if col == "Category" and (str(raw_val) in ["electronics", "Furniture ", "Grocery"] or str(raw_val).strip() in ["electronics", "Grocery"]):
                continue
            # Skip injected ID collision rows (user113@example.com / user114@example.com) when Record_ID is reassigned
            if col == "Record_ID" and email in ("user113@example.com", "user114@example.com"):
                continue

            # Compare raw and cleaned
            if pd.isna(raw_val) and pd.isna(cl_val):
                continue

            # Normalized phone text comparison
            if col == "Phone":
                r_ph = str(raw_val).strip().replace(".0", "")
                c_ph = str(cl_val).strip().replace(".0", "")
                if r_ph == c_ph:
                    continue

            # Normalized integer comparison
            if col in ["Age", "Quantity"]:
                try:
                    if float(raw_val) == float(cl_val):
                        continue
                except (ValueError, TypeError):
                    pass

            # Numeric comparison
            if col in ["Amount", "Latitude", "Longitude"]:
                try:
                    if round(float(raw_val), 4) == round(float(cl_val), 4):
                        continue
                except (ValueError, TypeError):
                    pass

            # String comparison
            if str(raw_val) != str(cl_val):
                collateral_count += 1
                collateral_details.append(f"{rid}[{col}]: raw={repr(raw_val)} -> cleaned={repr(cl_val)}")

    return collateral_count, collateral_details


def evaluate(cleaned_df: pd.DataFrame, raw_df: pd.DataFrame) -> dict[str, Any]:
    cases = get_expected_cases()
    results_by_cat = defaultdict(lambda: {
        "injected": 0,
        "fixed": 0,
        "flagged_only": 0,
        "silently_kept": 0,
        "silently_wrong": 0,
        "deleted_wrongly": 0,
        "details": [],
    })

    for c in cases:
        status, detail = c.check_fn(raw_df, cleaned_df)
        cat = results_by_cat[c.category]
        cat["injected"] += 1
        cat[status] += 1
        cat["details"].append((c.case_id, status, detail))

    total_injected = sum(c["injected"] for c in results_by_cat.values())
    total_fixed = sum(c["fixed"] for c in results_by_cat.values())
    total_flagged_only = sum(c["flagged_only"] for c in results_by_cat.values())
    total_silently_kept = sum(c["silently_kept"] for c in results_by_cat.values())
    total_silently_wrong = sum(c["silently_wrong"] for c in results_by_cat.values())
    total_deleted_wrongly = sum(c["deleted_wrongly"] for c in results_by_cat.values())

    score = (total_fixed + total_flagged_only) / total_injected * 100.0 if total_injected > 0 else 0.0
    collateral_count, collateral_details = compute_collateral_damage(raw_df, cleaned_df)

    return {
        "results_by_cat": dict(results_by_cat),
        "total_injected": total_injected,
        "total_fixed": total_fixed,
        "total_flagged_only": total_flagged_only,
        "total_silently_kept": total_silently_kept,
        "total_silently_wrong": total_silently_wrong,
        "total_deleted_wrongly": total_deleted_wrongly,
        "score": score,
        "collateral_count": collateral_count,
        "collateral_details": collateral_details,
    }


def check_idempotency(cleaned_df: pd.DataFrame) -> tuple[bool, str]:
    """Test idempotency: re-running pipeline on cleaned_df produces 0 changes and 0 new flags."""
    df2, _ = run_pipeline_on_dataframe(cleaned_df.copy())
    # Compare shape
    if df2.shape != cleaned_df.shape:
        return False, f"Shape changed on rerun: {cleaned_df.shape} -> {df2.shape}"

    # Check for new columns
    new_cols = set(df2.columns) - set(cleaned_df.columns)
    if new_cols:
        return False, f"New columns added on rerun: {new_cols}"

    # Check cell equality
    diffs = 0
    for col in cleaned_df.columns:
        s1 = cleaned_df[col].astype(str).fillna("")
        s2 = df2[col].astype(str).fillna("")
        diffs += (s1 != s2).sum()

    if diffs > 0:
        return False, f"{diffs} cell differences on rerun"

    return True, "PASS (0 changes, 0 flags added)"


def check_pristine() -> tuple[bool, str]:
    """Test pristine dataset: clean rows must have 0 changes and 0 flags added."""
    pristine_raw = generate_pristine_dataset(100)
    pristine_cleaned, _ = run_pipeline_on_dataframe(pristine_raw.copy())

    if pristine_cleaned.shape[0] != pristine_raw.shape[0]:
        return False, f"Rows changed: {pristine_raw.shape[0]} -> {pristine_cleaned.shape[0]}"

    new_cols = set(pristine_cleaned.columns) - set(pristine_raw.columns)
    if new_cols:
        return False, f"Flags added to pristine dataset: {new_cols}"

    diffs = 0
    for col in pristine_raw.columns:
        s1 = pristine_raw[col].astype(str).fillna("")
        s2 = pristine_cleaned[col].astype(str).fillna("")
        diffs += (s1 != s2).sum()

    if diffs > 0:
        return False, f"{diffs} cells altered on pristine dataset"

    return True, "PASS (0 changes, 0 flags added)"


def print_score_table(res: dict[str, Any], idempotency_msg: str, pristine_msg: str):
    print("=" * 105)
    print(f"{'Error Class / Category':<32} | {'Inj':>4} | {'Fixed':>5} | {'Flagged':>7} | {'Sil.Kept':>8} | {'Sil.Wrong':>9} | {'Del.Wrong':>9} | {'Score %':>7}")
    print("-" * 105)

    for cat_name, stats in sorted(res["results_by_cat"].items()):
        inj = stats["injected"]
        fixed = stats["fixed"]
        flg = stats["flagged_only"]
        sk = stats["silently_kept"]
        sw = stats["silently_wrong"]
        dw = stats["deleted_wrongly"]
        cat_score = (fixed + flg) / inj * 100.0 if inj > 0 else 0.0
        print(f"{cat_name:<32} | {inj:>4} | {fixed:>5} | {flg:>7} | {sk:>8} | {sw:>9} | {dw:>9} | {cat_score:>6.1f}%")

    print("-" * 105)
    tot_inj = res["total_injected"]
    tot_fixed = res["total_fixed"]
    tot_flg = res["total_flagged_only"]
    tot_sk = res["total_silently_kept"]
    tot_sw = res["total_silently_wrong"]
    tot_dw = res["total_deleted_wrongly"]
    tot_score = res["score"]
    print(f"{'TOTAL OVERALL':<32} | {tot_inj:>4} | {tot_fixed:>5} | {tot_flg:>7} | {tot_sk:>8} | {tot_sw:>9} | {tot_dw:>9} | {tot_score:>6.1f}%")
    print("=" * 105)
    print(f"Overall SCORE : {tot_score:.2f}% (Target: >= 90.0%)")
    print(f"COLLATERAL    : {res['collateral_count']} cells altered (Target: 0)")
    print(f"Idempotency   : {idempotency_msg}")
    print(f"Pristine Data : {pristine_msg}")
    print("=" * 105)


def main():
    raw_path = os.path.join(SCRIPT_DIR, "messy_project_testing_dataset_120_rows.xlsx")
    raw_df = pd.read_excel(raw_path)

    # Use baseline_cleaned.csv if requested or run pipeline
    csv_mode = "--baseline" in sys.argv or "-b" in sys.argv
    if csv_mode:
        cleaned_path = os.path.join(SCRIPT_DIR, "baseline_cleaned.csv")
        cleaned_df = pd.read_csv(cleaned_path)
        print("\n>>> EVALUATING BASELINE (baseline_cleaned.csv) <<<\n")
    else:
        print("\n>>> EVALUATING CURRENT PIPELINE ON RAW DATASET <<<\n")
        cleaned_df, _ = run_pipeline_on_dataframe(raw_df.copy())

    res = evaluate(cleaned_df, raw_df)
    idemp_ok, idemp_msg = check_idempotency(cleaned_df)
    prist_ok, prist_msg = check_pristine()
    print_score_table(res, idemp_msg, prist_msg)


if __name__ == "__main__":
    main()
