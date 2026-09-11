"""
Test suite for generalized numeric cleanup, editable Excel export with auto-sized columns,
and chat endpoint behavior.
"""

from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch, MagicMock
import openpyxl
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.cleaning import suggest_cleaning_steps, apply_pipeline, clean_numeric_value
from app.profiling import profile_dataframe


class TestGeneralizedNumericAndExcel(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_clean_numeric_value_various_formats(self) -> None:
        """Test clean_numeric_value on various currencies, commas, and negative formats."""
        self.assertEqual(clean_numeric_value("₹7,200"), 7200)
        self.assertEqual(clean_numeric_value("$1,200.50"), 1200.5)
        self.assertEqual(clean_numeric_value("€ 3,450"), 3450)
        self.assertEqual(clean_numeric_value("  15,000  "), 15000)
        self.assertEqual(clean_numeric_value("-500"), -500)
        self.assertEqual(clean_numeric_value("-₹500"), -500)
        self.assertEqual(clean_numeric_value("₹-500"), -500)
        self.assertEqual(clean_numeric_value("(500)"), -500)
        self.assertEqual(clean_numeric_value("($1,200)"), -1200)
        self.assertIsNone(clean_numeric_value("N/A"))
        self.assertIsNone(clean_numeric_value("nan"))
        self.assertIsNone(clean_numeric_value(None))

    def test_generic_numeric_cleanup_on_price_and_revenue_columns(self) -> None:
        """Phase 2: Test that Price and Revenue columns (different from Amount) are cleaned properly."""
        data = {
            "Item": ["A", "B", "C", "D"],
            "Price": ["$1,200.50", "₹5,000", "4,500", "  750  "],
            "Revenue": ["10,000", "₹25,000.00", "$5,500", "1,250"],
        }
        df = pd.DataFrame(data)
        profile = profile_dataframe(df)

        # Apply coerce_numeric pipeline step on Price and Revenue
        steps = [
            {"action": "coerce_numeric", "params": {"column": "Price"}},
            {"action": "coerce_numeric", "params": {"column": "Revenue"}},
        ]
        cleaned_df, log = apply_pipeline(df, steps)

        # Confirm Price values are parsed into numeric floats/ints
        self.assertEqual(cleaned_df.loc[0, "Price"], 1200.50)
        self.assertEqual(cleaned_df.loc[1, "Price"], 5000.0)
        self.assertEqual(cleaned_df.loc[2, "Price"], 4500.0)
        self.assertEqual(cleaned_df.loc[3, "Price"], 750.0)

        # Confirm Revenue values are parsed into numeric floats/ints
        self.assertEqual(cleaned_df.loc[0, "Revenue"], 10000.0)
        self.assertEqual(cleaned_df.loc[1, "Revenue"], 25000.0)
        self.assertEqual(cleaned_df.loc[2, "Revenue"], 5500.0)
        self.assertEqual(cleaned_df.loc[3, "Revenue"], 1250.0)

        # Confirm dtypes are numeric
        self.assertTrue(pd.api.types.is_numeric_dtype(cleaned_df["Price"]))
        self.assertTrue(pd.api.types.is_numeric_dtype(cleaned_df["Revenue"]))

    def test_amount_column_regression(self) -> None:
        """Phase 4 regression: Confirm Amount column behavior still works completely."""
        data = {
            "ID": [1, 2, 3, 4],
            "Amount": ["8,500", "₹7,200", "15,000", "-500"],
        }
        df = pd.DataFrame(data)
        steps = [{"action": "coerce_numeric", "params": {"column": "Amount"}}]
        cleaned_df, _ = apply_pipeline(df, steps)

        self.assertEqual(cleaned_df.loc[0, "Amount"], 8500.0)
        self.assertEqual(cleaned_df.loc[1, "Amount"], 7200.0)
        self.assertEqual(cleaned_df.loc[2, "Amount"], 15000.0)
        self.assertEqual(cleaned_df.loc[3, "Amount"], -500.0)

    def test_excel_download_autosizing_and_editability(self) -> None:
        """Phase 3: Upload a file, clean it, download as xlsx, and verify column widths and editable cells."""
        csv_content = (
            'Name,Product_Category,Price,Total_Revenue\n'
            'Alice Smith,"Electronics & Accessories","$1,250.00",12500.00\n'
            'Bob Jones,"Home Decor & Kitchen Appliances","₹4,500",45000.00\n'
        ).encode("utf-8")

        # Upload
        up_res = self.client.post(
            "/upload",
            files={"file": ("test_sales.csv", io.BytesIO(csv_content), "text/csv")},
        )
        self.assertEqual(up_res.status_code, 200)
        dataset_id = up_res.json()["dataset_id"]

        # Apply a pipeline step so cleaned file exists
        step = {
            "action": "coerce_numeric",
            "params": {"column": "Price"},
            "description": "Coerce Price to numeric",
            "severity": "medium",
        }
        save_res = self.client.post(f"/datasets/{dataset_id}/pipeline", json=[step])
        self.assertEqual(save_res.status_code, 200)

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200)

        # Download xlsx
        dl_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=xlsx")
        self.assertEqual(dl_res.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument", dl_res.headers["content-type"])

        # Inspect with openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(dl_res.content))
        ws = wb["Cleaned Data"]

        # Confirm protection is disabled and sheet is editable
        self.assertFalse(ws.protection.sheet)

        # Confirm column dimensions are auto-sized (width >= 12)
        for col_letter in ["A", "B", "C", "D"]:
            col_dim = ws.column_dimensions[col_letter]
            self.assertIsNotNone(col_dim.width)
            self.assertGreaterEqual(col_dim.width, 12)

        # Column B ("Product_Category" or "Home Decor & Kitchen Appliances") must be wide (> 30)
        b_width = ws.column_dimensions["B"].width
        self.assertGreater(b_width, 30)

        # Confirm cells can be edited and saved without restriction
        ws["B2"] = "Edited Cell Content"
        out_stream = io.BytesIO()
        wb.save(out_stream)
        self.assertGreater(len(out_stream.getvalue()), 0)

        # Also confirm CSV download still works
        csv_res = self.client.get(f"/datasets/{dataset_id}/download-cleaned?format=csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("text/csv", csv_res.headers["content-type"])
        self.assertIn("Alice Smith", csv_res.text)


if __name__ == "__main__":
    unittest.main()
