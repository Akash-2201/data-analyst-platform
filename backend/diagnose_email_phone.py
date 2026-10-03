"""Focused diagnostic: check what _build_guaranteed_column_response actually returns."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import json
import pandas as pd

csv_path = os.path.join(os.path.dirname(__file__), "test_phone_email_20x7.csv")
df = pd.read_csv(csv_path)

from app.profiling import profile_dataframe
from app.cleaning import suggest_cleaning_steps
from app.ai_suggestions import _build_guaranteed_column_response

profile = profile_dataframe(df)
suggestions = suggest_cleaning_steps(df, profile)

# Filter to just the ones that would pass the safety net
passed = []
for rs in suggestions:
    r_col = rs.get("params", {}).get("column")
    r_act = rs.get("action")
    if r_col and r_act not in ("standardize_category", "standardize_date_format"):
        passed.append(rs)

print(f"=== Suggestions passed to _build_guaranteed_column_response: {len(passed)} ===")
for p in passed:
    print(f"  action='{p['action']}' column='{p['params'].get('column')}' has_flagged={('flagged_values' in p)}")

final = _build_guaranteed_column_response(
    df, profile,
    all_suggestions=passed,
    date_cache={},
    mapping_cache={},
    general_notes=[],
    source="diagnostic",
)

print(f"\n=== column_results structure ===")
for cr in final.get("column_results", []):
    col_name = cr.get("name", cr.get("column_name", "?"))
    issues = cr.get("issues", [])
    status = cr.get("status", "?")
    card_type = cr.get("card_type", "?")
    print(f"  Column '{col_name}': status='{status}', card_type='{card_type}', issue_count={len(issues)}")
    for iss in issues:
        act = iss.get("action", "?")
        has_fv = "flagged_values" in iss
        fv_count = len(iss.get("flagged_values", []))
        print(f"    action='{act}' has_flagged_values={has_fv} flagged_count={fv_count}")

print(f"\n=== flat suggestions ===")
flat = final.get("suggestions", [])
print(f"Total flat suggestions: {len(flat)}")
for s in flat:
    act = s.get("action", "?")
    col = s.get("params", {}).get("column", "N/A")
    has_fv = "flagged_values" in s
    print(f"  action='{act}' column='{col}' has_flagged_values={has_fv}")

# Dump the Email and Phone column_results fully
print(f"\n=== FULL Email column_result ===")
for cr in final.get("column_results", []):
    if cr.get("name") == "Email":
        print(json.dumps(cr, indent=2, default=str)[:2000])

print(f"\n=== FULL Phone column_result ===")
for cr in final.get("column_results", []):
    if cr.get("name") == "Phone":
        print(json.dumps(cr, indent=2, default=str)[:2000])
