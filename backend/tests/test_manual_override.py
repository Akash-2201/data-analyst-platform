"""
Phase 3 — Manual per-column review override test.

Verifies that:
1. Upload messy CSV with Gender (MALE, male, M, FEMALE, F), City, Department.
2. Get suggestions.
3. User manually overrides grouping (e.g. reassigns "M" to stay separate / original "M",
   maps "male" & "MALE" to "Male", maps "FEMALE" and "F" to "Female").
4. Call /preview and verify before/after diffs reflect the manual overrides.
5. Save pipeline and call /apply.
6. Download cleaned CSV and assert the exact manual overrides took effect.
"""

from __future__ import annotations

import io
import unittest
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

MESSY_CSV = """\
Name,Gender,City,Department,Salary
Alice,MALE,Bengaluru,Marketing,50000
Bob,male,bangalore,Marketing,60000
Carol,M,BANGALORE,Marekting,55000
Dave,FEMALE,Bengaluru,Marketing,70000
Eve,female,Banglore,MARKETING,65000
Frank,F,Bengaluru,Marketing,N/A
Grace,MALE,bangalore,Marekting,52000
Heidi,FEMALE,BANGALORE,Marketing,68000
"""


class TestManualOverride(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_manual_override_applied_correctly(self) -> None:
        # Step 1: Upload dataset
        res = self.client.post(
            "/upload",
            files={"file": ("messy.csv", io.BytesIO(MESSY_CSV.encode("utf-8")), "text/csv")},
        )
        self.assertEqual(res.status_code, 200)
        dataset_id = res.json()["dataset_id"]

        # Step 2: Get suggestions (using rule-based for speed & determinism)
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        self.assertEqual(res.status_code, 200)
        suggestions = res.json()
        self.assertGreater(len(suggestions), 0)

        # Step 3: Define manual override mapping:
        # - "MALE" -> "Male"
        # - "male" -> "Male"
        # - "M" stays "M" (explicitly NOT merged into "Male")
        # - "FEMALE" -> "Female"
        # - "female" -> "Female"
        # - "F" -> "Female"
        manual_gender_mapping = {
            "MALE": "Male",
            "male": "Male",
            # "M" is intentionally omitted so it stays as "M"
            "FEMALE": "Female",
            "female": "Female",
            "F": "Female",
        }

        manual_steps = [
            {
                "action": "standardize_category",
                "params": {"column": "Gender", "mapping": manual_gender_mapping},
                "description": "Manual override for Gender",
                "severity": "medium",
            },
            {
                "action": "standardize_category",
                "params": {
                    "column": "City",
                    "mapping": {"bangalore": "Bengaluru", "BANGALORE": "Bengaluru", "Banglore": "Bengaluru"},
                },
                "description": "Standardize City to Bengaluru",
                "severity": "medium",
            },
            {
                "action": "standardize_category",
                "params": {
                    "column": "Department",
                    "mapping": {"MARKETING": "Marketing", "Marekting": "Marketing"},
                },
                "description": "Standardize Department to Marketing",
                "severity": "medium",
            },
        ]

        # Step 4: Call /preview with manual steps
        prev_res = self.client.post(f"/datasets/{dataset_id}/preview", json=manual_steps)
        self.assertEqual(prev_res.status_code, 200)
        preview_json = prev_res.json()
        col_diffs = {d["column"]: d for d in preview_json.get("column_diffs", [])}
        self.assertIn("Gender", col_diffs)
        gender_after = col_diffs["Gender"]["after"]

        # Assert preview shows "M" stayed separate (1 occurrence) and "Male" has 3, "Female" has 4
        self.assertEqual(gender_after.get("M"), 1)
        self.assertEqual(gender_after.get("Male"), 3)
        self.assertEqual(gender_after.get("Female"), 4)

        # Step 5: Save pipeline and apply
        pipe_res = self.client.post(f"/datasets/{dataset_id}/pipeline", json=manual_steps)
        self.assertEqual(pipe_res.status_code, 200)

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200)

        # Step 6: Download cleaned CSV
        dl_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(dl_res.status_code, 200)

        cleaned_df = pd.read_csv(io.BytesIO(dl_res.content))
        gender_counts = cleaned_df["Gender"].value_counts().to_dict()

        print("\n[Manual Override Test] Cleaned Gender value counts:")
        print(gender_counts)

        # Step 7: Verify final cleaned values
        self.assertEqual(gender_counts.get("Male"), 3)
        self.assertEqual(gender_counts.get("Female"), 4)
        self.assertEqual(gender_counts.get("M"), 1)
        self.assertNotIn("MALE", gender_counts)
        self.assertNotIn("FEMALE", gender_counts)
        self.assertNotIn("F", gender_counts)

        print("[Manual Override Test] [PASSED] Manual overrides took effect correctly.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
