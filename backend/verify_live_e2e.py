import requests
import json
import pandas as pd

BASE_URL = "http://127.0.0.1:8000"
FILE_PATH = "storage_data/0c5f9b01-9cf9-46d7-b675-55d46d04b699_raw_messy_test_data_20x7.xlsx"

def run_test():
    print("--- 1. UPLOADING 20x7 TEST DATASET ---")
    with open(FILE_PATH, "rb") as f:
        resp = requests.post(f"{BASE_URL}/upload", files={"file": ("raw_messy_test_data_20x7.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    data = resp.json()
    dataset_id = data["dataset_id"]
    print(f"Dataset uploaded successfully: ID = {dataset_id}")
    print(f"Columns: {[c['name'] for c in data['columns']]}")

    print("\n--- 2. FETCHING SUGGESTIONS & GUARANTEED COLUMN CARDS ---")
    s_resp = requests.get(f"{BASE_URL}/datasets/{dataset_id}/suggestions")
    assert s_resp.status_code == 200, f"Suggestions failed: {s_resp.text}"
    s_data = s_resp.json()
    col_results = s_data["column_results"]
    print(f"Column results count: {len(col_results)}")
    
    # Phase 1 verification: Phone column
    phone_card = next((c for c in col_results if c["name"].lower() == "phone"), None)
    assert phone_card is not None, "Phone column card missing!"
    print(f"Phone card: inferred_type = {phone_card['inferred_type']}, status = {phone_card['status']}")
    assert phone_card["inferred_type"] == "phone", f"Phone inferred type is {phone_card['inferred_type']}"
    phone_ops = [i["action"] for i in phone_card.get("issues", [])]
    print(f"Phone issues: {phone_ops}")
    assert "coerce_numeric" not in phone_ops, "coerce_numeric MUST NOT be suggested for Phone!"
    assert "flag_invalid_phone" in phone_ops, "flag_invalid_phone should be flagged for 9-digit phone!"
    phone_flagged = phone_card["issues"][0].get("flagged_values", [])
    print(f"Phone flagged values: {phone_flagged}")
    assert any("987654321" in str(v.get("raw_value")) for v in phone_flagged), "987654321 should be flagged"

    # Phase 2 verification: Email column
    email_card = next((c for c in col_results if c["name"].lower() == "email"), None)
    assert email_card is not None, "Email column card missing!"
    print(f"\nEmail card: inferred_type = {email_card['inferred_type']}, status = {email_card['status']}")
    email_issues = email_card.get("issues", [])
    email_flagged_vals = []
    for issue in email_issues:
        for fv in issue.get("flagged_values", []):
            email_flagged_vals.append(fv["raw_value"])
    print(f"Email flagged values ({len(email_flagged_vals)}): {email_flagged_vals}")
    bad_emails = ["rahul123@gmail", "meena.gmail.com", "lakshmi@@gmail.com", "priya.sharma @gmail.com"]
    for bad in bad_emails:
        assert bad in email_flagged_vals, f"Bad email '{bad}' not flagged! Flagged: {email_flagged_vals}"
    print("✓ All 4 bad emails flagged correctly!")

    # Phase 4 & 6 verification: Amount column
    amount_card = next((c for c in col_results if c["name"].lower() == "amount"), None)
    assert amount_card is not None, "Amount column card missing!"
    amount_issues = amount_card.get("issues", [])
    neg_issue = next((i for i in amount_issues if i["action"] == "flag_negative_values"), None)
    assert neg_issue is not None, "flag_negative_values issue missing from Amount!"
    print(f"\nAmount negative issue flagged values: {neg_issue.get('flagged_values')}")
    neg_flagged = neg_issue.get("flagged_values", [])
    assert len(neg_flagged) > 0, "No negative flagged values in Amount!"
    neg_item = neg_flagged[0]
    print(f"Flagged negative: raw = {neg_item['raw_value']}, suggested = {neg_item.get('suggested_value')}")
    assert float(neg_item["suggested_value"]) == 500.0, f"Suggested value should be 500.0, got {neg_item.get('suggested_value')}"

    # Phase 3 verification: City column
    city_card = next((c for c in col_results if c["name"].lower() == "city"), None)
    assert city_card is not None, "City column card missing!"
    ca = city_card.get("categorical_analysis", {})
    city_mapping = ca.get("mapping", {})
    print(f"\nCity mapping: {city_mapping}")
    assert "Bangalore" in city_mapping, "Bangalore should be in mapping!"
    canonical_city = city_mapping["Bangalore"]
    print(f"Bangalore maps to: {canonical_city}")

    print("\n--- 3. TESTING PREVIEW & APPLY WITH ALL STEPS ---")
    steps = [
        # Phase 5: Name case normalisation with trimming
        {
            "action": "normalize_case",
            "params": {"column": "Name", "case": "upper"},
            "description": "Normalize 'Name' to UPPERCASE",
            "severity": "low"
        },
        # Phase 3: City standardization
        {
            "action": "standardize_category",
            "params": {"column": "City", "mapping": {"Bangalore": canonical_city}},
            "description": f"Standardize City (Bangalore -> {canonical_city})",
            "severity": "medium"
        },
        # Phase 4: Coerce numeric on Amount (currency + comma stripping)
        {
            "action": "coerce_numeric",
            "params": {"column": "Amount"},
            "description": "Coerce Amount to numeric",
            "severity": "high"
        },
        # Phase 6: Manual value override on Amount (row with -500 to 500)
        {
            "action": "manual_value_override",
            "params": {"column": "Amount", "overrides": {str(neg_item["row_index"]): 500}},
            "description": "Manual override on Amount",
            "severity": "medium"
        }
    ]

    prev_resp = requests.post(f"{BASE_URL}/datasets/{dataset_id}/preview", json=steps)
    assert prev_resp.status_code == 200, f"Preview failed: {prev_resp.text}"
    prev_data = prev_resp.json()
    print("Preview diff keys:", list(prev_data.get("diff", {}).keys()))
    print("Preview sample rows count:", len(prev_data.get("sample_preview", [])))

    # Save pipeline and apply
    save_resp = requests.post(f"{BASE_URL}/datasets/{dataset_id}/pipeline", json=steps)
    assert save_resp.status_code == 200, f"Save pipeline failed: {save_resp.text}"

    apply_resp = requests.post(f"{BASE_URL}/datasets/{dataset_id}/apply")
    assert apply_resp.status_code == 200, f"Apply failed: {apply_resp.text}"
    apply_data = apply_resp.json()
    print("Apply success:", apply_data["status"])
    print("Steps executed:", [s["action"] for s in apply_data["steps_applied"]])

    # Verify download file content
    dl_resp = requests.get(f"{BASE_URL}/datasets/{dataset_id}/download-cleaned?format=csv")
    assert dl_resp.status_code == 200, f"Download failed: {dl_resp.text}"
    import io
    df_clean = pd.read_csv(io.StringIO(dl_resp.text))
    print(f"\nCleaned DataFrame shape: {df_clean.shape}")
    print("\nCleaned DataFrame head:")
    print(df_clean[["Name", "City", "Amount", "Phone"]].head(10))

    # Phase 1 check: Phone values
    phone_vals = df_clean["Phone"].dropna().astype(str).tolist()
    print(f"\nSample cleaned phone values: {phone_vals[:5]}")
    for p in phone_vals:
        assert not p.endswith(".0"), f"Phone was corrupted with .0 float suffix: {p}"
        assert "e" not in p.lower(), f"Phone was converted to scientific notation: {p}"
    print("✓ Phone numbers preserved as clean strings without float/scientific notation!")

    # Phase 3 check: City values
    city_vals = df_clean["City"].tolist()
    assert "Bangalore" not in city_vals, "Raw 'Bangalore' still present in cleaned City!"
    assert city_vals.count(canonical_city) >= 2, f"Both Bangalore rows should map to {canonical_city}"
    print(f"✓ City mapping deterministic: all mapped to {canonical_city}!")

    # Phase 4 & 6 check: Amount values
    amt_vals = df_clean["Amount"].dropna().tolist()
    print(f"\nCleaned Amount values: {amt_vals}")
    assert all(a >= 0 for a in amt_vals), f"Found negative values in Amount: {amt_vals}"
    assert 500.0 in amt_vals, "Overridden 500.0 not found in Amount!"
    # Check currency and comma values
    for expected in [8500.0, 7200.0, 4500.0, 15000.0, 7250.0]:
        assert expected in amt_vals, f"Expected amount {expected} missing from Amount! Found: {amt_vals}"
    print("✓ Amount currency/comma stripping and manual override worked perfectly!")

    # Phase 5 check: Name trim and case
    name_vals = df_clean["Name"].dropna().tolist()
    assert "ROHIT SINGH" in name_vals, f"'ROHIT SINGH' not found! Names: {name_vals}"
    assert not any("  " in n for n in name_vals), f"Found double spaces in Name: {name_vals}"
    print("✓ Name whitespace trimmed and collapsed alongside uppercase normalization!")

    print("\n--- 4. TESTING CHAT BOT ENDPOINT ---")
    chat_resp = requests.post(f"{BASE_URL}/chat", json={
        "message": "Which column has the highest missing values?",
        "dataset_id": dataset_id
    })
    assert chat_resp.status_code == 200, f"Chat failed: {chat_resp.text}"
    chat_data = chat_resp.json()
    print("Chat reply snippet:", chat_data["reply"][:150])
    print("✓ Chat response received successfully!")

    print("\n=======================================================")
    print("ALL 7 PHASES LIVE END-TO-END VERIFIED SUCCESSFULLY!")
    print("=======================================================")

if __name__ == "__main__":
    run_test()
