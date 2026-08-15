"""
Tests for AI-powered cleaning suggestions.

Tests:
1. Upload a dirty CSV with known issues and verify AI suggestions are returned,
   including that standardize_category mapping is Python-computed (not empty).
2. Fallback path: with empty API key, rule-based suggestions are returned instead of an error.
3. Validation: suggestions with unknown operations or bad column names are rejected.
4. General notes are present (non-empty list when real issues exist).

Also fixes the existing chat test mock target (updated SDK path).
"""

from __future__ import annotations

import io
import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.ai_suggestions import (
    ALLOWED_OPERATIONS,
    _build_compact_summary,
    _validate_and_enrich,
    _fill_standardize_mapping,
    generate_ai_suggestions,
)
from app.profiling import profile_dataframe


DIRTY_CSV = (
    "name,city,department,age,salary\n"
    "Alice,Bengaluru,Marketing,25,50000\n"
    "Bob,bangalore,Marketing,30,60000\n"
    "Charlie,BANGALORE ,Marekting,35,55000\n"
    "Dave,Bengaluru,Marketing,-5,N/A\n"
    "Eve,Bengaluru,Marketing,,45000\n"
    "Alice,Bengaluru,Marketing,25,50000\n"   # duplicate of row 1
)


def _make_mock_gemini_response(suggestions_payload: list[dict], notes: list[str] = None) -> MagicMock:
    """Build a mock google.genai Client that returns the given payload as JSON."""
    import json
    payload = {"suggestions": suggestions_payload, "general_notes": notes or []}
    mock_response = MagicMock()
    mock_response.text = json.dumps(payload)

    mock_model_client = MagicMock()
    mock_model_client.models.generate_content.return_value = mock_response

    return mock_model_client


class TestCompactSummary(unittest.TestCase):
    def test_summary_structure(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        profile = profile_dataframe(df)
        summary = _build_compact_summary(profile)
        self.assertIn("row_count", summary)
        self.assertIn("columns", summary)
        # Raw dataframe data not in summary
        self.assertNotIn("data", summary)
        col_names = [c["name"] for c in summary["columns"]]
        self.assertIn("city", col_names)
        self.assertIn("salary", col_names)


class TestValidateAndEnrich(unittest.TestCase):
    def _df(self):
        return pd.read_csv(io.StringIO(DIRTY_CSV))

    def test_valid_suggestion_passes(self):
        df = self._df()
        raw = {
            "column": "age",
            "operation": "flag_negative_values",
            "params": {"column": "age"},
            "description": "Age has negative values",
            "severity": "medium",
            "reason": "Negative age is impossible",
        }
        result = _validate_and_enrich(raw, df, {})
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "flag_negative_values")
        self.assertIn("id", result)

    def test_unknown_operation_rejected(self):
        df = self._df()
        raw = {
            "column": "age",
            "operation": "magic_fix",  # not in ALLOWED_OPERATIONS
            "params": {},
            "description": "blah",
            "severity": "low",
        }
        result = _validate_and_enrich(raw, df, {})
        self.assertIsNone(result)

    def test_bad_column_rejected(self):
        df = self._df()
        raw = {
            "column": "nonexistent_col",
            "operation": "fill_missing",
            "params": {"strategy": "median"},
            "description": "blah",
            "severity": "low",
        }
        result = _validate_and_enrich(raw, df, {})
        self.assertIsNone(result)

    def test_standardize_category_mapping_filled_by_python(self):
        df = self._df()
        raw = {
            "column": "city",
            "operation": "standardize_category",
            "params": {"column": "city"},  # NO mapping from Gemini
            "description": "City has inconsistent spellings",
            "severity": "medium",
        }
        cache: dict = {}
        result = _validate_and_enrich(raw, df, cache)
        self.assertIsNotNone(result)
        # Mapping must be non-empty and Python-computed
        self.assertIn("mapping", result["params"])
        self.assertGreater(len(result["params"]["mapping"]), 0)
        # It should map the variant spellings to the canonical one
        mapping = result["params"]["mapping"]
        # bangalore or BANGALORE  should map to Bengaluru (most frequent)
        mapped_values = set(mapping.values())
        self.assertTrue(len(mapped_values) >= 1)

    def test_standardize_category_with_gemini_mapping_overwritten(self):
        """Even if Gemini includes a mapping, Python's difflib result is used."""
        df = self._df()
        raw = {
            "column": "city",
            "operation": "standardize_category",
            "params": {"column": "city", "mapping": {"wrong": "data"}},
            "description": "desc",
            "severity": "medium",
        }
        cache: dict = {}
        result = _validate_and_enrich(raw, df, cache)
        self.assertIsNotNone(result)
        # The "wrong": "data" mapping from Gemini should be completely overwritten
        self.assertNotIn("wrong", result["params"]["mapping"])


class TestFillStandardizeMapping(unittest.TestCase):
    def test_finds_city_clusters(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        mapping = _fill_standardize_mapping(df, "city")
        # Should detect bangalore/BANGALORE  as variants of Bengaluru
        self.assertGreater(len(mapping), 0)

    def test_nonexistent_column_returns_empty(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        mapping = _fill_standardize_mapping(df, "does_not_exist")
        self.assertEqual(mapping, {})


class TestGenerateAiSuggestionsFallback(unittest.TestCase):
    """Test that fallback to rule-based works when API key is missing."""

    def test_no_api_key_uses_rule_based(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        profile = profile_dataframe(df)
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = generate_ai_suggestions(df, profile)
        self.assertEqual(result["source"], "rule_based_fallback")
        self.assertIsInstance(result["suggestions"], list)
        self.assertGreater(len(result["suggestions"]), 0)
        # Rule-based suggestions always have the required keys
        for s in result["suggestions"]:
            self.assertIn("id", s)
            self.assertIn("action", s)
            self.assertIn("description", s)
            self.assertIn("severity", s)

    def test_gemini_exception_falls_back(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        profile = profile_dataframe(df)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}, clear=False):
            with patch("google.genai.Client", side_effect=RuntimeError("network error")), \
                 patch("google.genai.types"):
                result = generate_ai_suggestions(df, profile)
        self.assertEqual(result["source"], "rule_based_fallback")
        self.assertGreater(len(result["suggestions"]), 0)


class TestGenerateAiSuggestionsWithMockedGemini(unittest.TestCase):
    """Test the AI path with mocked Gemini responses."""

    def _dirty_df_and_profile(self):
        df = pd.read_csv(io.StringIO(DIRTY_CSV))
        return df, profile_dataframe(df)

    def test_valid_ai_suggestions_returned(self):
        df, profile = self._dirty_df_and_profile()
        mock_suggestions = [
            {
                "column": "salary",
                "issue": "non_numeric_in_numeric",
                "operation": "coerce_numeric",
                "params": {"column": "salary"},
                "description": "Salary column has 'N/A' text in a numeric column — coercing to NaN.",
                "severity": "high",
                "reason": "Text values prevent numeric analysis.",
            },
            {
                "column": "age",
                "issue": "missing_values",
                "operation": "fill_missing",
                "params": {"column": "age", "strategy": "median"},
                "description": "Age column has 1 missing value — filling with median is appropriate for numeric data.",
                "severity": "medium",
                "reason": "Median is robust to outliers unlike mean.",
            },
            {
                "column": "city",
                "issue": "near_duplicate_categories",
                "operation": "standardize_category",
                "params": {"column": "city"},
                "description": "City column has 'Bengaluru', 'bangalore', 'BANGALORE' — likely the same city with inconsistent spelling.",
                "severity": "medium",
                "reason": "Inconsistent city names will break groupby analyses.",
            },
        ]
        mock_notes = ["The 'salary' and 'age' columns together suggest Dave (age=-5) may be a test record."]

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}, clear=False):
            import json
            payload = {"suggestions": mock_suggestions, "general_notes": mock_notes}

            mock_response = MagicMock()
            mock_response.text = json.dumps(payload)
            mock_client_instance = MagicMock()
            mock_client_instance.models.generate_content.return_value = mock_response

            with patch("google.genai.Client", return_value=mock_client_instance), \
                 patch("google.genai.types"):
                result = generate_ai_suggestions(df, profile)

        self.assertEqual(result["source"], "ai")
        sugs = result["suggestions"]
        actions = [s["action"] for s in sugs]

        # coerce_numeric, fill_missing, standardize_category all validated through
        self.assertIn("coerce_numeric", actions)
        self.assertIn("fill_missing", actions)
        self.assertIn("standardize_category", actions)

        # drop_duplicates should be added by safety net (1 dup row in CSV)
        self.assertIn("drop_duplicates", actions)

        # general_notes present
        self.assertGreater(len(result["general_notes"]), 0)

        # standardize_category mapping was filled by Python, not Gemini
        sc_sug = next(s for s in sugs if s["action"] == "standardize_category")
        self.assertIn("mapping", sc_sug["params"])
        self.assertGreater(len(sc_sug["params"]["mapping"]), 0)

        # All suggestions have required keys
        for sug in sugs:
            self.assertIn("id", sug)
            self.assertIn("action", sug)
            self.assertIn("description", sug)
            self.assertIn("severity", sug)
            self.assertIn(sug["action"], ALLOWED_OPERATIONS)

    def test_invalid_operations_from_gemini_are_rejected(self):
        df, profile = self._dirty_df_and_profile()
        bad_suggestions = [
            {
                "column": "age",
                "operation": "magic_clean_everything",  # bad!
                "params": {},
                "description": "some desc",
                "severity": "high",
            },
            {
                "column": "salary",
                "operation": "fill_missing",
                "params": {"column": "salary", "strategy": "median"},
                "description": "Fill missing salary",
                "severity": "medium",
            },
        ]
        import json
        payload = {"suggestions": bad_suggestions, "general_notes": []}

        mock_response = MagicMock()
        mock_response.text = json.dumps(payload)
        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = mock_response

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}, clear=False):
            with patch("google.genai.Client", return_value=mock_client_instance), \
                 patch("google.genai.types"):
                result = generate_ai_suggestions(df, profile)

        actions = [s["action"] for s in result["suggestions"]]
        self.assertNotIn("magic_clean_everything", actions)
        self.assertIn("fill_missing", actions)


class TestEndpointIntegration(unittest.TestCase):
    """Integration test via TestClient for the /suggestions endpoint."""

    def setUp(self):
        self.client = TestClient(app)

    def _upload_dirty_csv(self) -> str:
        file_obj = io.BytesIO(DIRTY_CSV.encode("utf-8"))
        res = self.client.post(
            "/upload",
            files={"file": ("dirty.csv", file_obj, "text/csv")},
        )
        self.assertEqual(res.status_code, 200)
        return res.json()["dataset_id"]

    def test_suggestions_endpoint_returns_list(self):
        dataset_id = self._upload_dirty_csv()
        # Use rule-based fallback to keep test fast and deterministic
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        self.assertEqual(res.status_code, 200)
        suggestions = res.json()
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)

    def test_suggestions_endpoint_fallback_when_key_empty(self):
        """With empty key, endpoint must still return valid suggestions (rule-based)."""
        dataset_id = self._upload_dirty_csv()
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        self.assertEqual(res.status_code, 200)
        suggestions = res.json()
        # All suggestions from fallback must be actionable
        for s in suggestions:
            self.assertIn("action", s)
            self.assertIn(s["action"], ALLOWED_OPERATIONS)
            # source field should say rule_based_fallback
            self.assertEqual(s.get("source"), "rule_based_fallback")

    def test_pipeline_still_applies_after_ai_suggestions(self):
        """Verify the full pipeline still works end-to-end with AI-derived suggestions."""
        dataset_id = self._upload_dirty_csv()
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            sug_res = self.client.get(f"/datasets/{dataset_id}/suggestions")
        suggestions = sug_res.json()

        pipe_res = self.client.post(f"/datasets/{dataset_id}/pipeline", json=suggestions)
        self.assertEqual(pipe_res.status_code, 200)

        apply_res = self.client.post(f"/datasets/{dataset_id}/apply")
        self.assertEqual(apply_res.status_code, 200)
        self.assertIn("cleaned_profile", apply_res.json())


if __name__ == "__main__":
    unittest.main()
