"""
Phase 0 — Re-upload bug diagnostic test.

Full flow:
  1. Upload messy CSV with Gender (MALE/male/M/FEMALE/F), City, Department case/spelling variants
  2. GET /suggestions (rule-based, no Gemini needed for mechanical detection)
  3. Save + Apply every suggestion returned
  4. Download cleaned CSV via /download-cleaned
  5. Re-upload that exact downloaded file as a brand-new upload
  6. GET /suggestions on the new upload

Assert: second /suggestions must return ZERO standardize_category, trim_whitespace,
or normalize_case issues.  Missing-value or outlier flags are fine.

If the assertion fails we dump:
  - the raw distinct value counts BEFORE cleaning (from step 1 upload)
  - the raw distinct value counts AFTER cleaning (from the re-uploaded file)
  - which suggestions were still returned

This test MUST pass before any Phase 1/2 code is written.
"""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

# A CSV that has every variant we want to verify disappears after cleaning:
# - Gender: MALE / male / M / FEMALE / female / F   (case + abbreviation)
# - City:   Bengaluru / bangalore / BANGALORE / Banglore   (case + typo)
# - Department: Marketing / Marekting / MARKETING   (case + typo)
# - Salary: numeric, with one missing (N/A) — should survive as a legitimate flag
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

# Mechanical issues we expect the first-pass suggestions to catch
CATEGORICAL_ACTIONS = {"standardize_category", "trim_whitespace", "normalize_case"}


class TestReuploadBug(unittest.TestCase):
    """Verify that cleaning fully persists so re-uploading the cleaned file is clean."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _upload(self, csv_bytes: bytes, filename: str = "messy.csv") -> str:
        res = self.client.post(
            "/upload",
            files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        )
        self.assertEqual(res.status_code, 200, f"Upload failed: {res.text}")
        return res.json()["dataset_id"]

    def _get_suggestions_rule_based(self, dataset_id: str) -> list[dict]:
        """Get suggestions using rule-based engine (no Gemini needed)."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        self.assertEqual(res.status_code, 200, f"Suggestions failed: {res.text}")
        return res.json()

    def _apply_all(self, dataset_id: str, suggestions: list[dict]) -> None:
        """Save every suggestion to the pipeline and apply."""
        pipe_res = self.client.post(
            f"/datasets/{dataset_id}/pipeline",
            json=suggestions,
        )
        self.assertEqual(pipe_res.status_code, 200, f"Pipeline save failed: {pipe_res.text}")

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200, f"Apply failed: {apply_res.text}")

    def _download_cleaned(self, dataset_id: str) -> bytes:
        res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(res.status_code, 200, f"Download failed: {res.text}")
        return res.content

    # ------------------------------------------------------------------
    # Phase 0 main test
    # ------------------------------------------------------------------

    def test_reupload_produces_no_categorical_issues(self) -> None:
        # ---- Step 1: upload the messy file ----
        messy_bytes = MESSY_CSV.encode("utf-8")
        dataset_id_1 = self._upload(messy_bytes, "messy.csv")

        # ---- Step 2: get suggestions (rule-based) ----
        suggestions_1 = self._get_suggestions_rule_based(dataset_id_1)
        actions_1 = [s["action"] for s in suggestions_1]
        print(f"\n[Phase 0] First-pass suggestions ({len(suggestions_1)}):")
        for s in suggestions_1:
            print(f"  action={s['action']} col={s['params'].get('column','—')} "
                  f"mapping={s['params'].get('mapping')}")

        # Sanity: we expect the first pass to FIND categorical issues
        categorical_1 = [s for s in suggestions_1 if s["action"] in CATEGORICAL_ACTIONS]
        self.assertTrue(
            len(categorical_1) > 0,
            f"Expected first-pass to find categorical issues — got only: {actions_1}",
        )

        # ---- Step 3: apply ALL suggestions ----
        self._apply_all(dataset_id_1, suggestions_1)

        # ---- Step 4: download cleaned CSV ----
        cleaned_bytes = self._download_cleaned(dataset_id_1)
        cleaned_df = pd.read_csv(io.BytesIO(cleaned_bytes))

        print(f"\n[Phase 0] Cleaned CSV distinct values per categorical column:")
        for col in ["Gender", "City", "Department"]:
            if col in cleaned_df.columns:
                vc = cleaned_df[col].value_counts().to_dict()
                print(f"  {col}: {vc}")

        # ---- Step 5: re-upload the cleaned file as a NEW upload ----
        dataset_id_2 = self._upload(cleaned_bytes, "cleaned_reupload.csv")

        # ---- Step 6: get suggestions on the re-uploaded cleaned file ----
        suggestions_2 = self._get_suggestions_rule_based(dataset_id_2)
        categorical_2 = [s for s in suggestions_2 if s["action"] in CATEGORICAL_ACTIONS]

        print(f"\n[Phase 0] Second-pass suggestions ({len(suggestions_2)}) — MUST BE ZERO categorical:")
        for s in suggestions_2:
            print(f"  action={s['action']} col={s['params'].get('column','—')} "
                  f"desc={s.get('description','')}")

        # ---- Step 7: ASSERTION — no categorical issues remain ----
        if categorical_2:
            # Build a diff to show what's still wrong
            re_uploaded_df = pd.read_csv(io.BytesIO(cleaned_bytes))
            print("\n[Phase 0] DIFF — values still problematic after cleaning:")
            for s in categorical_2:
                col = s["params"].get("column", "?")
                if col in re_uploaded_df.columns:
                    vc = re_uploaded_df[col].value_counts().to_dict()
                    print(f"  {col} ({s['action']}): {vc}")
                    print(f"  mapping in suggestion: {s['params'].get('mapping')}")

        self.assertEqual(
            categorical_2,
            [],
            f"Re-uploaded cleaned file still has {len(categorical_2)} categorical issue(s). "
            f"Actions found: {[s['action'] for s in categorical_2]}. "
            f"Columns: {[s['params'].get('column') for s in categorical_2]}. "
            "Cleaning did not fully persist.",
        )

        print("\n[Phase 0] [PASSED] re-uploaded cleaned file has zero categorical issues.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
