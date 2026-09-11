"""
Phase 1-4 Bug Hunt: Frank row-loss + Gender 'M' variant investigation.

Phases:
  1. Reproduce & trace the row-loss bug - step-by-step pipeline trace
  2. Confirm Gender 'M' behavior (by design or real bug?)
  3. Fix operation ordering if drop_duplicates runs AFTER normalization
  4. Prove: Frank survives the full TestClient flow with all 9 rows intact

Run from: backend/
    venv\\Scripts\\python.exe -m pytest tests/test_frank_row_loss.py -v -s
"""
from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.cleaning import apply_pipeline

# ---------------------------------------------------------------------------
# Exact 9-row dataset (verbatim - do not alter values)
# ---------------------------------------------------------------------------
NINE_ROW_CSV = (
    "Name,Age,Gender,City,Department,Salary\n"
    "Alice,28,MALE,Bengaluru,Marketing,72000\n"
    "Bob,35,male,bangalore,Marekting,58000\n"
    "Charlie,42,M,BANGALORE,Marketing,95000\n"
    "Diana,-5,FEMALE,Bengaluru,marketing,61000\n"
    "Eve,31,female,Banglore,Engineering,88000\n"
    "Frank,55,F,bengaluru,engineering,  120000  \n"
    "Grace,29,MALE,BENGALURU,Marketing,45000\n"
    "Heidi,33,male,bangalore,Marekting,79000\n"
    "Ivan,26,FEMALE,Bengaluru,HR,42000\n"
)

# Steps a user would reasonably approve (no drop_duplicates in this set -
# that is exactly what we are testing: if drop_duplicates were included it
# must run BEFORE normalize_case, not after).
USER_STEPS = [
    {
        "action": "standardize_category",
        "params": {
            "column": "City",
            "mapping": {
                "bangalore":  "Bengaluru",
                "BANGALORE":  "Bengaluru",
                "Banglore":   "Bengaluru",
                "bengaluru":  "Bengaluru",
                "BENGALURU":  "Bengaluru",
            },
        },
        "description": "Standardize City variants",
        "severity": "high",
    },
    {
        "action": "standardize_category",
        "params": {
            "column": "Department",
            "mapping": {
                "Marekting":   "Marketing",
                "MARKETING":   "Marketing",
                "marketing":   "Marketing",
                "engineering": "Engineering",
                "ENGINEERING": "Engineering",
            },
        },
        "description": "Standardize Department variants",
        "severity": "high",
    },
    {
        "action": "clip_negative_to_null",
        "params": {"column": "Age"},
        "description": "Clip negative Age values to null",
        "severity": "high",
    },
    {
        "action": "normalize_case",
        "params": {"column": "Gender", "case": "title"},
        "description": "Normalize Gender capitalization",
        "severity": "medium",
    },
]

# Steps with drop_duplicates BEFORE normalization (correct order per Phase 3)
USER_STEPS_WITH_DEDUP_BEFORE = [
    {
        "action": "drop_duplicates",
        "params": {},
        "description": "Drop duplicate rows",
        "severity": "high",
    },
] + USER_STEPS

# Steps with drop_duplicates AFTER normalization (the ORDER THAT CAUSES THE BUG)
USER_STEPS_WITH_DEDUP_AFTER = USER_STEPS + [
    {
        "action": "drop_duplicates",
        "params": {},
        "description": "Drop duplicate rows",
        "severity": "high",
    },
]


def _load_df(csv_text: str) -> pd.DataFrame:
    """Parse CSV text the same way the API does (keep_default_na=False, na_values=[''])."""
    return pd.read_csv(io.StringIO(csv_text), keep_default_na=False, na_values=[""])


# ---------------------------------------------------------------------------
# Phase 1 + 3: Low-level apply_pipeline() trace (no HTTP)
# ---------------------------------------------------------------------------

class TestPhase1TraceRowLoss(unittest.TestCase):
    """
    Phase 1 - Reproduce and trace the row-loss bug at apply_pipeline() level.
    Phase 3 - Confirm correct order (dedup BEFORE normalize) preserves all rows.
    """

    def setUp(self) -> None:
        self.df_orig = _load_df(NINE_ROW_CSV)
        print(f"\n[Setup] Original dataset: {len(self.df_orig)} rows")
        print(self.df_orig.to_string())

    def test_1a_four_steps_no_dedup_all_9_rows_survive(self) -> None:
        """Without drop_duplicates, all 9 rows must survive."""
        df = self.df_orig.copy()
        cleaned_df, log = apply_pipeline(df, USER_STEPS)

        print("\n[Phase 1a] Step log:")
        for entry in log:
            lost = entry["rows_before"] - entry["rows_after"]
            marker = f" *** ROWS LOST: {lost} ***" if lost > 0 else " OK"
            print(f"  {entry['action']:30s} {entry['rows_before']} -> {entry['rows_after']}{marker}")

        print(f"\nFinal df ({len(cleaned_df)} rows):")
        print(cleaned_df.to_string())

        frank_present = "Frank" in cleaned_df["Name"].values
        print(f"\nFrank present: {frank_present}")
        print(f"Gender unique: {sorted(cleaned_df['Gender'].unique().tolist())}")

        self.assertEqual(len(cleaned_df), 9,
                         f"Expected 9 rows but got {len(cleaned_df)} -- row was incorrectly dropped")
        self.assertTrue(frank_present, "Frank's row was lost during pipeline execution")

    def test_1b_bob_heidi_collision_after_normalize(self) -> None:
        """
        After City+Department standardization + normalize_case(Gender):
        Bob: male->Male, bangalore->Bengaluru, Marekting->Marketing, Salary=58000
        Heidi: male->Male, bangalore->Bengaluru, Marekting->Marketing, Salary=79000

        Their Salary DIFFERS (58000 vs 79000), so they are NOT identical.
        drop_duplicates after normalization should NOT drop either of them.
        This test documents the exact field-by-field comparison.
        """
        df = self.df_orig.copy()
        cleaned_df, _ = apply_pipeline(df, USER_STEPS)

        bob   = cleaned_df[cleaned_df["Name"] == "Bob"]
        heidi = cleaned_df[cleaned_df["Name"] == "Heidi"]
        self.assertFalse(bob.empty, "Bob not found after cleaning")
        self.assertFalse(heidi.empty, "Heidi not found after cleaning")

        bob_row   = bob.iloc[0]
        heidi_row = heidi.iloc[0]

        print("\n[Phase 1b] Bob vs Heidi after normalization:")
        mismatches = []
        for col in cleaned_df.columns:
            if col == "Name":
                continue
            b = str(bob_row[col]).strip()
            h = str(heidi_row[col]).strip()
            match_str = "MATCH" if b == h else "differ"
            print(f"  {col}: Bob={b!r}  Heidi={h!r}  -> {match_str}")
            if b != h:
                mismatches.append(col)

        print(f"\nData columns where Bob != Heidi: {mismatches}")
        # Salary differs: 58000 vs 79000. They are NOT identical after normalization.
        self.assertGreater(len(mismatches), 0,
                           "Bob and Heidi are identical in ALL data columns after normalization -- "
                           "drop_duplicates WOULD silently merge them, causing row loss")

    def test_3a_dedup_before_normalize_all_9_rows_survive(self) -> None:
        """With drop_duplicates BEFORE normalize_case, all 9 rows should survive."""
        df = self.df_orig.copy()
        cleaned_df, log = apply_pipeline(df, USER_STEPS_WITH_DEDUP_BEFORE)

        print("\n[Phase 3a] dedup-before step log:")
        for entry in log:
            lost = entry["rows_before"] - entry["rows_after"]
            marker = f" *** ROWS LOST: {lost} ***" if lost > 0 else " OK"
            print(f"  {entry['action']:30s} {entry['rows_before']} -> {entry['rows_after']}{marker}")

        print(f"\nFinal df ({len(cleaned_df)} rows):")
        print(cleaned_df.to_string())

        frank_present = "Frank" in cleaned_df["Name"].values
        print(f"\nFrank present: {frank_present}")

        self.assertEqual(len(cleaned_df), 9,
                         f"Expected 9 rows but got {len(cleaned_df)} with dedup-before")
        self.assertTrue(frank_present, "Frank is missing even with dedup-before -- unexpected")

    def test_3b_dedup_after_normalize_documents_row_loss_risk(self) -> None:
        """
        DIAGNOSTIC: Run drop_duplicates AFTER normalize_case to document exactly what happens.
        Frank is unique (F->Female, Salary=120000) so he must never be lost.
        Bob and Heidi differ in Salary, so they survive too.
        This test locks in the guarantee and reports clearly if the dangerous order breaks things.
        """
        df = self.df_orig.copy()
        cleaned_df, log = apply_pipeline(df, USER_STEPS_WITH_DEDUP_AFTER)

        print("\n[Phase 3b] dedup-AFTER step log:")
        for entry in log:
            lost = entry["rows_before"] - entry["rows_after"]
            marker = f" *** ROWS LOST: {lost} ***" if lost > 0 else " OK"
            print(f"  {entry['action']:30s} {entry['rows_before']} -> {entry['rows_after']}{marker}")

        print(f"\nFinal df ({len(cleaned_df)} rows):")
        print(cleaned_df.to_string())

        orig_names = {"Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Heidi","Ivan"}
        cleaned_names = set(cleaned_df["Name"].tolist())
        lost_names = orig_names - cleaned_names
        print(f"\nLost names: {sorted(lost_names)}")

        frank_present = "Frank" in cleaned_df["Name"].values
        print(f"Frank present with dedup-AFTER: {frank_present}")

        if lost_names:
            print(f"\n*** ORDER BUG CONFIRMED: dedup-AFTER dropped {len(lost_names)} row(s): "
                  f"{sorted(lost_names)} ***")
            print("drop_duplicates MUST run BEFORE normalize_case/standardize_category")

        self.assertTrue(frank_present,
                        f"Frank was incorrectly removed by dedup-AFTER. "
                        f"Lost rows: {sorted(lost_names)}")


# ---------------------------------------------------------------------------
# Phase 2: Gender 'M' confidence design confirmation
# ---------------------------------------------------------------------------

class TestPhase2GenderMAbbreviation(unittest.TestCase):
    """
    Phase 2 - Trace what mapping is sent for Gender 'M' and confirm
    whether the behavior is by-design or an actual bug.
    """

    def test_2a_m_marked_low_confidence_not_auto_applied(self) -> None:
        """
        The AI marks 'M' as low-confidence (abbreviation of 'Male').
        _build_mapping_from_ai_groups() only adds HIGH-confidence variants to
        params.mapping.  'M' goes into variant_confidences as 'low' but is
        NOT added to the auto-applied mapping.

        Frontend behavior:
          if (confidences[val] === 'high' && aiMapping[val]) {
              initMappings[col][val] = aiMapping[val];  // auto-select
          } else {
              initMappings[col][val] = val;             // keep as-is (default)
          }

        'M' shows in the review table with a 'low' badge.
        The user must manually select it to include it.
        This is WORKING AS DESIGNED -- not a bug.
        """
        from app.ai_suggestions import _build_mapping_from_ai_groups

        simulated_ai_groups = [
            {
                "canonical": "Male",
                "variants": [
                    {"value": "MALE",   "confidence": "high"},
                    {"value": "male",   "confidence": "high"},
                    {"value": "M",      "confidence": "low"},
                ],
                "reasoning": "MALE/male are case variants; M is an abbreviation of Male",
            },
            {
                "canonical": "Female",
                "variants": [
                    {"value": "FEMALE", "confidence": "high"},
                    {"value": "female", "confidence": "high"},
                    {"value": "F",      "confidence": "low"},
                ],
                "reasoning": "FEMALE/female are case variants; F is an abbreviation of Female",
            },
        ]

        gender_series = pd.Series([
            "MALE", "male", "M", "FEMALE", "female", "F", "MALE", "male", "FEMALE"
        ])

        mapping, recommended, warn_desc, extra_info = _build_mapping_from_ai_groups(
            simulated_ai_groups, gender_series, total_rows=9
        )

        print("\n[Phase 2] Gender mapping from _build_mapping_from_ai_groups:")
        print(f"  mapping: {mapping}")
        print(f"  variant_confidences: {extra_info.get('variant_confidences', {})}")
        print(f"  recommended: {recommended}")

        # HIGH confidence variants ARE auto-mapped
        self.assertEqual(mapping.get("MALE"),   "Male",   "MALE should auto-map to Male")
        self.assertEqual(mapping.get("male"),   "Male",   "male should auto-map to Male")
        self.assertEqual(mapping.get("FEMALE"), "Female", "FEMALE should auto-map to Female")
        self.assertEqual(mapping.get("female"), "Female", "female should auto-map to Female")

        # LOW confidence abbreviations are NOT auto-mapped
        self.assertNotIn("M", mapping,
                         "'M' confidence=low must NOT appear in auto-applied mapping")
        self.assertNotIn("F", mapping,
                         "'F' confidence=low must NOT appear in auto-applied mapping")

        # But they ARE in variant_confidences so the UI renders them
        vc = extra_info.get("variant_confidences", {})
        self.assertEqual(vc.get("M"), "low",
                         "'M' must appear in variant_confidences as 'low' for UI rendering")
        self.assertEqual(vc.get("F"), "low",
                         "'F' must appear in variant_confidences as 'low' for UI rendering")

        print("\n[Phase 2] Verdict: 'M' is WORKING AS DESIGNED.")
        print("  The review UI shows M with a low-confidence badge.")
        print("  The user must manually select M->Male to include it in the mapping.")
        print("  If they do not select it, M is intentionally excluded. NOT a bug.")

    def test_2b_m_shows_in_groups_for_ui_rendering(self) -> None:
        """
        Even though 'M' is not in params.mapping, it MUST appear in
        params.groups[].variants so the frontend review table can render it.
        """
        from app.ai_suggestions import _build_mapping_from_ai_groups

        simulated_ai_groups = [
            {
                "canonical": "Male",
                "variants": [
                    {"value": "MALE", "confidence": "high"},
                    {"value": "M",    "confidence": "low"},
                ],
                "reasoning": "M is likely an abbreviation of Male",
            },
        ]
        gender_series = pd.Series(["MALE", "M", "MALE", "M"])
        _, _, _, extra_info = _build_mapping_from_ai_groups(
            simulated_ai_groups, gender_series, total_rows=4
        )

        groups = extra_info.get("groups", [])
        self.assertTrue(len(groups) > 0, "No groups returned")

        male_group = next((g for g in groups if g["canonical"] == "Male"), None)
        self.assertIsNotNone(male_group, "Male group not found")

        variant_values = [v["value"] for v in male_group["variants"]]
        print(f"\n[Phase 2b] Male group variants: {variant_values}")
        self.assertIn("M", variant_values,
                      "'M' must appear in groups.variants so the UI renders it with a low-confidence badge")


# ---------------------------------------------------------------------------
# Phase 4: Full TestClient end-to-end (Frank must survive /apply)
# ---------------------------------------------------------------------------

class TestPhase4FullEndToEnd(unittest.TestCase):
    """
    Phase 4 - Prove it: run the full HTTP flow via TestClient and confirm
    Frank is present in the final cleaned output with City='Bengaluru'.
    """

    def setUp(self) -> None:
        self.client = TestClient(app)

    def _upload(self, csv_bytes: bytes, filename: str = "test9rows.csv") -> str:
        res = self.client.post(
            "/upload",
            files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        )
        self.assertEqual(res.status_code, 200, f"Upload failed: {res.text}")
        return res.json()["dataset_id"]

    def test_4_frank_survives_full_pipeline_via_testclient(self) -> None:
        """
        Full flow:
          1. Upload 9-row CSV
          2. GET /suggestions (rule-based, no Gemini)
          3. POST /pipeline with approved steps
          4. POST /preview (mirrors what user sees)
          5. POST /apply
          6. Download cleaned CSV; assert len==9, Frank present, Frank.City=='Bengaluru'
        """
        csv_bytes = NINE_ROW_CSV.encode("utf-8")
        dataset_id = self._upload(csv_bytes)

        # Step 2: get suggestions (rule-based, no AI key)
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        data = res.json()
        suggestions = data.get("suggestions", data) if isinstance(data, dict) else data
        print(f"\n[Phase 4] Suggestions returned ({len(suggestions)}):")
        for s in suggestions:
            print(f"  action={s['action']} col={s['params'].get('column','---')} "
                  f"desc={s.get('description','')}")

        # Step 3: Save pipeline with our predefined USER_STEPS
        pipe_res = self.client.post(
            f"/datasets/{dataset_id}/pipeline",
            json=USER_STEPS,
        )
        self.assertEqual(pipe_res.status_code, 200, f"Pipeline save failed: {pipe_res.text}")

        # Step 4: Preview
        preview_payload = [
            {
                "action": s["action"],
                "params": s["params"],
                "description": s["description"],
                "severity": s["severity"],
            }
            for s in USER_STEPS
        ]
        preview_res = self.client.post(
            f"/datasets/{dataset_id}/preview",
            json=preview_payload,
        )
        self.assertEqual(preview_res.status_code, 200, f"Preview failed: {preview_res.text}")
        preview_data = preview_res.json()
        print(f"\n[Phase 4] Preview: {preview_data.get('original_row_count')} -> "
              f"{preview_data.get('cleaned_row_count')} rows")
        for diff in preview_data.get("column_diffs", []):
            summary_safe = (diff.get("summary") or "").encode("ascii", "replace").decode("ascii")
            print(f"  {diff.get('column')}: {summary_safe}")

        # Step 5: Apply
        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200, f"Apply failed: {apply_res.text}")
        apply_data = apply_res.json()

        print(f"\n[Phase 4] Apply result:")
        print(f"  original_row_count: {apply_data.get('original_row_count')}")
        print(f"  cleaned_row_count:  {apply_data.get('cleaned_row_count')}")
        print("  step log:")
        for entry in apply_data.get("log", []):
            lost = entry["rows_before"] - entry["rows_after"]
            marker = f" *** LOST {lost} ***" if lost > 0 else " OK"
            print(f"    {entry['action']:30s} {entry['rows_before']} -> {entry['rows_after']}{marker}")

        # Step 6: Download and inspect
        dl_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(dl_res.status_code, 200, f"Download failed: {dl_res.text}")
        cleaned_df = pd.read_csv(io.BytesIO(dl_res.content))

        print(f"\n[Phase 4] Cleaned dataframe ({len(cleaned_df)} rows):")
        print(cleaned_df.to_string())
        print(f"\nGender unique values: {sorted(cleaned_df['Gender'].dropna().unique().tolist())}")

        frank_rows = cleaned_df[cleaned_df["Name"] == "Frank"]
        if not frank_rows.empty:
            print(f"Frank's row: {frank_rows.iloc[0].to_dict()}")
        else:
            print("Frank: NOT FOUND")

        # ===== ASSERTIONS =====
        self.assertEqual(
            len(cleaned_df), 9,
            f"Row count BEFORE={apply_data.get('original_row_count')} "
            f"AFTER={len(cleaned_df)}. Expected 9. "
            f"Names present: {sorted(cleaned_df['Name'].tolist())}"
        )

        self.assertIn("Frank", cleaned_df["Name"].values,
                      "Frank's row is missing from the final cleaned output")

        frank_row = cleaned_df[cleaned_df["Name"] == "Frank"].iloc[0]
        self.assertEqual(frank_row["City"], "Bengaluru",
                         f"Frank's City was not corrected to 'Bengaluru', got: {frank_row['City']!r}")

        print(f"\n[Phase 4] PASSED: All 9 rows survived, Frank present with City='Bengaluru'")

    def test_4b_dedup_before_normalize_is_safe_with_9_rows(self) -> None:
        """
        If drop_duplicates is included, it MUST run before normalize_case.
        This test verifies the correct order still produces 9 rows.
        """
        csv_bytes = NINE_ROW_CSV.encode("utf-8")
        dataset_id = self._upload(csv_bytes, "test9rows_dedup.csv")

        pipe_res = self.client.post(
            f"/datasets/{dataset_id}/pipeline",
            json=USER_STEPS_WITH_DEDUP_BEFORE,
        )
        self.assertEqual(pipe_res.status_code, 200)

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200)
        apply_data = apply_res.json()

        dl_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(dl_res.status_code, 200)
        cleaned_df = pd.read_csv(io.BytesIO(dl_res.content))

        print(f"\n[Phase 4b] dedup-before: {apply_data.get('original_row_count')} -> "
              f"{len(cleaned_df)} rows")
        print(f"  Names: {sorted(cleaned_df['Name'].tolist())}")

        self.assertEqual(len(cleaned_df), 9,
                         f"dedup-before should yield 9 rows, got {len(cleaned_df)}")
        self.assertIn("Frank", cleaned_df["Name"].values,
                      "Frank must survive even with drop_duplicates before normalize")

    def test_4c_dedup_after_normalize_row_loss_analysis(self) -> None:
        """
        DIAGNOSTIC: Drop_duplicates AFTER normalize_case is the dangerous order.
        For this specific 9-row dataset:
          Bob (Salary=58000) and Heidi (Salary=79000) differ in Salary after normalization,
          so NO row loss should occur for this dataset.
        Frank is unique in all fields. This test locks in that guarantee.
        """
        csv_bytes = NINE_ROW_CSV.encode("utf-8")
        dataset_id = self._upload(csv_bytes, "test9rows_dedup_after.csv")

        pipe_res = self.client.post(
            f"/datasets/{dataset_id}/pipeline",
            json=USER_STEPS_WITH_DEDUP_AFTER,
        )
        self.assertEqual(pipe_res.status_code, 200)

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200)
        apply_data = apply_res.json()

        dl_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(dl_res.status_code, 200)
        cleaned_df = pd.read_csv(io.BytesIO(dl_res.content))

        orig_names = {"Alice","Bob","Charlie","Diana","Eve","Frank","Grace","Heidi","Ivan"}
        cleaned_names = set(cleaned_df["Name"].tolist())
        lost_names = orig_names - cleaned_names

        print(f"\n[Phase 4c] dedup-AFTER result: {apply_data.get('original_row_count')} -> "
              f"{len(cleaned_df)} rows")
        print(f"  Lost names: {sorted(lost_names)}")

        self.assertIn("Frank", cleaned_df["Name"].values,
                      f"Frank was dropped by dedup-AFTER. Lost names: {sorted(lost_names)}")

        if lost_names:
            print(f"\n  *** ORDER BUG: dedup-AFTER dropped {len(lost_names)} row(s): "
                  f"{sorted(lost_names)} ***")
            print("  drop_duplicates should run BEFORE normalize_case/standardize_category.")
        else:
            print("  No row loss for this dataset with dedup-AFTER.")
            print("  (Bob/Heidi differ in Salary=58000 vs 79000, so they never become identical.)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
