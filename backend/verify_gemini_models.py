import json
import requests

BASE = "http://127.0.0.1:8000"

print("=" * 70)
print("TEST 1: LIVE CHAT (General query without dataset)")
print("=" * 70)
chat_res = requests.post(
    f"{BASE}/chat",
    json={"message": "In one short sentence, introduce yourself as the Data Analyst Copilot."},
    timeout=60,
)
print("Status Code:", chat_res.status_code)
chat_data = chat_res.json()
print("Actual Chat Reply Text:")
print(chat_data.get("reply"))
print("Proposed Action:", chat_data.get("proposed_action"))

print("\n" + "=" * 70)
print("TEST 2: UPLOAD REAL DATASET (test_messy_v2.csv)")
print("=" * 70)
with open("test_messy_v2.csv", "rb") as f:
    upload_res = requests.post(f"{BASE}/upload", files={"file": ("test_messy_v2.csv", f, "text/csv")}, timeout=30)
print("Upload Status Code:", upload_res.status_code)
upload_data = upload_res.json()
dataset_id = upload_data["dataset_id"]
print("Dataset ID:", dataset_id)
print("Row count:", upload_data.get("row_count"))
print("Columns in dataset:", [c["name"] for c in upload_data.get("columns", [])])

print("\n" + "=" * 70)
print("TEST 3: GENERATE AI SUGGESTIONS (via Gemini)")
print("=" * 70)
sugg_res = requests.get(f"{BASE}/datasets/{dataset_id}/suggestions", timeout=120)
print("Suggestions Status Code:", sugg_res.status_code)
sugg_data = sugg_res.json()
print("\nGeneral Notes:")
for note in sugg_data.get("general_notes", []):
    print(f"  - {note}")

suggestions = sugg_data.get("suggestions", [])
print(f"\nTotal Suggestions Generated: {len(suggestions)}")
for i, s in enumerate(suggestions, 1):
    op = s.get("operation")
    col = s.get("params", {}).get("column") or s.get("column")
    desc = s.get("description")
    rec = s.get("recommended")
    print(f"  {i}. [{op}] {col}: {desc} (recommended={rec})")

print("\n" + "=" * 70)
print("TEST 4: LIVE CHAT WITH DATASET CONTEXT (Proposing action)")
print("=" * 70)
chat_ctx_res = requests.post(
    f"{BASE}/chat",
    json={
        "message": "What should I do about the missing values or inconsistencies in the Department column?",
        "dataset_id": dataset_id,
    },
    timeout=60,
)
print("Chat with Context Status Code:", chat_ctx_res.status_code)
chat_ctx_data = chat_ctx_res.json()
print("Actual Chat Context Reply Text:")
print(chat_ctx_data.get("reply"))
print("Proposed Action:")
print(json.dumps(chat_ctx_data.get("proposed_action"), indent=2))
