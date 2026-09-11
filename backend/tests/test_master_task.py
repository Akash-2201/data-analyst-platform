"""
Test suite for Master Task Phases 1 to 6.
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
from app.cleaning import suggest_cleaning_steps, apply_pipeline
from app.ai_suggestions import generate_ai_suggestions


class TestMasterTask(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        # Load the 20x7 dataset
        self.excel_path = "storage_data/0c5f9b01-9cf9-46d7-b675-55d46d04b699_raw_messy_test_data_20x7.xlsx"
        self.df = pd.read_excel(self.excel_path)
        self.profile = profile_dataframe(self.df)

    def test_phase1_phone_not_numerically_coerced(self) -> None:
        """Phase 1: Phone column is excluded from coerce_numeric and numeric operations."""
        suggs = suggest_cleaning_steps(self.df, self.profile)
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            ai_res = generate_ai_suggestions(self.df, self.profile)

        # Confirm Phone is not coerced
        phone_actions = [s["action"] for s in suggs if s.get("params", {}).get("column") == "Phone"]
        self.assertNotIn("coerce_numeric", phone_actions)
        self.assertNotIn("remove_outliers", phone_actions)

        # Confirm Phone in column_results is recognized as phone and not numeric card
        phone_col = next(c for c in ai_res["column_results"] if c["name"] == "Phone")
        self.assertEqual(phone_col["inferred_type"], "phone")
        self.assertNotEqual(phone_col["card_type"], "numeric")

        # Test apply_pipeline doesn't coerce Phone
        cleaned_df, _ = apply_pipeline(self.df, [{"action": "coerce_numeric", "params": {"column": "Phone"}}])
        # Phone values must not become NaN
        original_non_nulls = self.df["Phone"].dropna()
        cleaned_non_nulls = cleaned_df["Phone"].dropna()
        self.assertEqual(len(original_non_nulls), len(cleaned_non_nulls))

    def test_phase2_email_structural_checks(self) -> None:
        """Phase 2: Email column structural checks flag 4 known bad emails."""
        suggs = suggest_cleaning_steps(self.df, self.profile)
        email_suggs = [s for s in suggs if s.get("params", {}).get("column") == "Email"]
        descriptions = " ".join(s["description"] for s in email_suggs)

        self.assertIn("rahul123@gmail", descriptions)
        self.assertIn("meena.gmail.com", descriptions)
        self.assertIn("lakshmi@@gmail.com", descriptions)
        self.assertIn("priya.sharma @gmail.com", descriptions)

    def test_phase3_city_mapping_determinism(self) -> None:
        """Phase 3: Two rows with 'Bangalore' map to identical canonical targets."""
        mapping = {"bangalore": "Bengaluru", "Bangalore": "Bengaluru", "Banglore": "Bengaluru"}
        step = {
            "action": "standardize_category",
            "params": {"column": "City", "mapping": mapping},
        }
        cleaned_df, _ = apply_pipeline(self.df, [step])
        # Check row 0, row 2, row 15, row 16
        # Row 0: "Bangalore" -> "Bengaluru"
        # Row 16: "Bangalore" -> "Bengaluru"
        self.assertEqual(cleaned_df.loc[0, "City"], "Bengaluru")
        self.assertEqual(cleaned_df.loc[16, "City"], "Bengaluru")
        self.assertEqual(cleaned_df.loc[2, "City"], "Bengaluru")

    def test_phase4_amount_currency_and_comma_parsing(self) -> None:
        """Phase 4: Comma/currency formatted numbers are parsed, not turned to NaN."""
        step = {"action": "coerce_numeric", "params": {"column": "Amount"}}
        cleaned_df, _ = apply_pipeline(self.df, [step])

        # 8,500 (row 1), ₹7,200 (row 3), 4,500 (row 5), 15,000 (row 10), 7,250 (row 13)
        self.assertEqual(cleaned_df.loc[1, "Amount"], 8500.0)
        self.assertEqual(cleaned_df.loc[3, "Amount"], 7200.0)
        self.assertEqual(cleaned_df.loc[5, "Amount"], 4500.0)
        self.assertEqual(cleaned_df.loc[10, "Amount"], 15000.0)
        self.assertEqual(cleaned_df.loc[13, "Amount"], 7250.0)

    def test_phase5_name_trim_alongside_case_change(self) -> None:
        """Phase 5: Name trim applies alongside case change."""
        # Row 10 is "  rohit singh  "
        step = {"action": "normalize_case", "params": {"column": "Name", "case": "upper"}}
        cleaned_df, _ = apply_pipeline(self.df, [step])
        self.assertEqual(cleaned_df.loc[10, "Name"], "ROHIT SINGH")

    def test_phase6_manual_value_override(self) -> None:
        """Phase 6: manual_value_override sets specific cell values."""
        # Row 11 has Amount = -500. Correct it to 500
        step = {
            "action": "manual_value_override",
            "params": {"column": "Amount", "overrides": {11: 500}},
        }
        cleaned_df, _ = apply_pipeline(self.df, [step])
        self.assertEqual(cleaned_df.loc[11, "Amount"], 500)


if __name__ == "__main__":
    unittest.main()
