"""
Simulated end-to-end: Directly call generate_ai_suggestions to see what
the real AI path returns for the 20x7 CSV, including the safety net.
"""
import sys, os, json, logging
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging to see what AI suggestions does
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

import pandas as pd

csv_path = os.path.join(os.path.dirname(__file__), "test_phone_email_20x7.csv")
df = pd.read_csv(csv_path)
print(f"=== Loaded CSV: {df.shape} ===")

from app.profiling import profile_dataframe
profile = profile_dataframe(df)

# Now call the REAL generate_ai_suggestions — this is exactly what the /suggestions endpoint calls
from app.ai_suggestions import generate_ai_suggestions
print(f"\n=== Calling generate_ai_suggestions (the REAL AI path) ===")
result = generate_ai_suggestions(df, profile)

print(f"\n=== RESULT ===")
print(f"  source: {result.get('source')}")
print(f"  column_results count: {len(result.get('column_results', []))}")
print(f"  flat suggestions count: {len(result.get('suggestions', []))}")

for cr in result.get("column_results", []):
    col_name = cr.get("name", "?")
    issues = cr.get("issues", [])
    status = cr.get("status", "?")
    card_type = cr.get("card_type", "?")
    
    if col_name in ("Email", "Phone"):
        print(f"\n  *** Column '{col_name}' ***")
        print(f"    status: {status}")
        print(f"    card_type: {card_type}")
        print(f"    issue_count: {len(issues)}")
        for iss in issues:
            act = iss.get("action", "?")
            has_fv = "flagged_values" in iss
            fv_count = len(iss.get("flagged_values", []))
            desc = iss.get("description", "")[:100]
            print(f"    - action='{act}' has_flagged={has_fv} fv_count={fv_count} desc='{desc}'")
            if has_fv:
                for fv in iss.get("flagged_values", [])[:3]:
                    print(f"      row={fv.get('row_index')} raw='{fv.get('raw_value')}' reason='{fv.get('reason')}'")

# Check flat suggestions for email/phone
print(f"\n  === Flat suggestions with email/phone ===")
email_phone_found = False
for s in result.get("suggestions", []):
    act = s.get("action", "?")
    if "email" in act.lower() or "phone" in act.lower():
        col = s.get("params", {}).get("column", "N/A")
        has_fv = "flagged_values" in s
        fv_count = len(s.get("flagged_values", []))
        print(f"  action='{act}' column='{col}' has_flagged={has_fv} fv_count={fv_count}")
        email_phone_found = True

if not email_phone_found:
    print("  NONE FOUND!")
    
    # Dump to understand what DID appear
    print(f"\n  === ALL actions in flat suggestions ===")
    for s in result.get("suggestions", []):
        col = s.get("params", {}).get("column", "N/A")
        print(f"  action='{s.get('action')}' column='{col}'")
