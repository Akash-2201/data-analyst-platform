"""
Live integration test: upload a dirty CSV to the running server,
call /suggestions, print the AI response.
"""
import json
import sys
import time
import urllib.request

SERVER = "http://127.0.0.1:8000"

DIRTY_CSV = (
    "name,city,department,age,salary\n"
    "Alice,Bengaluru,Marketing,25,50000\n"
    "Bob,bangalore,Marketing,30,60000\n"
    "Charlie,BANGALORE ,Marekting,35,55000\n"
    "Dave,Bengaluru,Marketing,-5,N/A\n"
    "Eve,Bengaluru,Marketing,,45000\n"
    "Alice,Bengaluru,Marketing,25,50000\n"
)


def upload(csv_bytes: bytes) -> str:
    import http.client, mimetypes
    boundary = "aBoundary1234567890"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="dirty.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + csv_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{SERVER}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())["dataset_id"]


def get_suggestions(dataset_id: str) -> list:
    req = urllib.request.Request(f"{SERVER}/datasets/{dataset_id}/suggestions", method="GET")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def main():
    print("Uploading dirty CSV...")
    dataset_id = upload(DIRTY_CSV.encode())
    print(f"dataset_id = {dataset_id}\n")

    print("Fetching AI suggestions (may take up to 60s)...")
    suggestions = get_suggestions(dataset_id)

    print(f"\n=== SUGGESTIONS ({len(suggestions)} total) ===\n")
    for s in suggestions:
        display = {k: v for k, v in s.items() if k not in ("general_notes",)}
        print(json.dumps(display, indent=2))
        print()

    source = suggestions[0].get("source") if suggestions else "n/a"
    notes = suggestions[0].get("general_notes", []) if suggestions else []
    print(f"source       : {source}")
    print(f"general_notes: {json.dumps(notes, indent=2)}")

    # Validation checks
    print("\n=== VALIDATION ===")
    ALLOWED_OPERATIONS = {
        "drop_duplicates", "drop_column", "drop_missing", "fill_missing",
        "trim_whitespace", "normalize_case", "standardize_category",
        "coerce_numeric", "flag_negative_values", "clip_negative_to_null", "remove_outliers",
    }
    all_valid = True
    for s in suggestions:
        if s["action"] not in ALLOWED_OPERATIONS:
            print(f"FAIL: bad operation {s['action']!r}")
            all_valid = False
        sc = s.get("params", {})
        if s["action"] == "standardize_category":
            mapping = sc.get("mapping", {})
            if not mapping:
                print(f"FAIL: standardize_category for {sc.get('column')!r} has empty mapping!")
                all_valid = False
            else:
                print(f"OK  : standardize_category mapping for {sc.get('column')!r} = {mapping}")
    if all_valid:
        print("All suggestions passed validation.")
    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
