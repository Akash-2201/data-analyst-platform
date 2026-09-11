"""
Permanent regression test suite for the 'One Column In, One Card Out' guarantee.

RULE:
For any dataset with N columns, the /suggestions endpoint response MUST contain
exactly N column_results objects — one per column, no more, no less, in the exact
original column order from profile["columns"]. Every column must appear exactly once.
"""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.profiling import profile_dataframe
from app.ai_suggestions import generate_ai_suggestions


MESSY_20X7_PATH = r"C:\Users\j9698\OneDrive\Desktop\messy_test_data_20x7.xlsx"

DIRTY_CSV = (
    "id,name,city,department,age,salary\n"
    "1,Alice,Bengaluru,Marketing,25,50000\n"
    "2,Bob,bangalore,Marketing,30,60000\n"
    "3,Charlie,BANGALORE ,Marekting,35,55000\n"
    "4,Dave,Bengaluru,Marketing,-5,N/A\n"
    "5,Eve,Bengaluru,Marketing,,45000\n"
)

CLEAN_CSV = (
    "user_id,first_name,last_name,is_active\n"
    "101,John,Doe,True\n"
    "102,Jane,Smith,False\n"
    "103,Alex,Taylor,True\n"
)


class TestColumnResultsGuarantee(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def _assert_column_guarantee(self, response_data: dict, profile: dict) -> None:
        """Core assertion helper verifying the hard rule."""
        self.assertIn("column_results", response_data, "Response must contain 'column_results'")
        col_results = response_data["column_results"]
        expected_cols = profile.get("columns", [])
        expected_names = [c["name"] for c in expected_cols]

        # 1. Exactly N items
        self.assertEqual(
            len(col_results),
            len(expected_cols),
            f"Expected exactly {len(expected_cols)} column results, got {len(col_results)}",
        )

        # 2. Exact match in order
        result_names = [c["name"] for c in col_results]
        self.assertEqual(
            result_names,
            expected_names,
            f"Column order mismatch: {result_names} != {expected_names}",
        )

        # 3. Every column appears exactly once (no duplicates, no omissions)
        self.assertEqual(
            len(set(result_names)),
            len(expected_names),
            f"Duplicate column detected in results: {result_names}",
        )

        # 4. Valid structure on each column result object
        for col_res in col_results:
            self.assertIn("name", col_res)
            self.assertIn("column", col_res)
            self.assertEqual(col_res["name"], col_res["column"])
            self.assertIn("status", col_res)
            self.assertIn(col_res["status"], {"clean", "has_issues"})
            self.assertIn("card_type", col_res)
            self.assertIn(col_res["card_type"], {"clean", "date", "categorical", "numeric", "structural"})
            self.assertIn("issues", col_res)
            self.assertIsInstance(col_res["issues"], list)

            if col_res["status"] == "clean":
                self.assertEqual(len(col_res["issues"]), 0)
                self.assertEqual(col_res["card_type"], "clean")
            else:
                self.assertGreater(len(col_res["issues"]), 0)

    def test_guarantee_on_real_7_column_file_direct(self):
        """Direct test on generate_ai_suggestions using the real messy_test_data_20x7.xlsx file."""
        if not os.path.exists(MESSY_20X7_PATH):
            self.skipTest(f"{MESSY_20X7_PATH} not found")

        df = pd.read_excel(MESSY_20X7_PATH)
        profile = profile_dataframe(df)

        self.assertEqual(len(profile["columns"]), 7, "Real test file must have 7 columns")
        expected_names = ["ID", "Name", "Email", "Phone", "Date", "City", "Amount"]
        self.assertEqual([c["name"] for c in profile["columns"]], expected_names)

        # Test fallback path
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = generate_ai_suggestions(df, profile)

        self._assert_column_guarantee(result, profile)

    def test_guarantee_on_real_7_column_file_via_api_endpoint(self):
        """HTTP endpoint test on /datasets/{id}/suggestions using real messy_test_data_20x7.xlsx."""
        if not os.path.exists(MESSY_20X7_PATH):
            self.skipTest(f"{MESSY_20X7_PATH} not found")

        with open(MESSY_20X7_PATH, "rb") as f:
            file_bytes = f.read()

        up_res = self.client.post(
            "/upload",
            files={"file": ("messy_test_data_20x7.xlsx", io.BytesIO(file_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(up_res.status_code, 200)
        dataset_id = up_res.json()["dataset_id"]
        profile = up_res.json()

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            sug_res = self.client.get(f"/datasets/{dataset_id}/suggestions")

        self.assertEqual(sug_res.status_code, 200)
        data = sug_res.json()
        self._assert_column_guarantee(data, profile)

    def test_guarantee_on_dirty_csv(self):
        """Test on DIRTY_CSV (6 columns)."""
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        profile = profile_dataframe(df)

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = generate_ai_suggestions(df, profile)

        self._assert_column_guarantee(result, profile)

    def test_guarantee_on_clean_csv(self):
        """Test on CLEAN_CSV (4 clean columns) — all columns must be emitted as 'clean'."""
        df = pd.read_csv(io.StringIO(CLEAN_CSV))
        profile = profile_dataframe(df)

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = generate_ai_suggestions(df, profile)

        self._assert_column_guarantee(result, profile)
        for c in result["column_results"]:
            self.assertEqual(c["status"], "clean")
            self.assertEqual(c["card_type"], "clean")
            self.assertEqual(len(c["issues"]), 0)


if __name__ == "__main__":
    unittest.main()
