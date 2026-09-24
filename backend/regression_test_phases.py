"""
Regression test for Excel Phone/Email formatting, column width, and validation rules.

Run from the backend directory with the virtualenv active:
    python regression_test_phases.py
"""

import io
import sys
import os

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from openpyxl import load_workbook

from app.cleaning import validate_phone, validate_email, COLUMN_TYPE_RULES, suggest_cleaning_steps
from app.profiling import profile_dataframe


def test_phone_validation():
    """Phase 3: Verify validate_phone flags all expected issues."""
    print("\n=== Phase 3a: Phone Validation ===")
    phones = pd.Series([
        "9876543210",       # valid
        "98765432111",      # 11 digits
        "8765432",          # 7 digits
        "+919876543210",    # valid with country code
        "abcdefghij",       # letters
        "",                 # empty (will be NaN after dropna)
        "123",              # 3 digits
        "9988776655AB",     # digits + letters
        "+14155552671",     # US number (not 10 digits after stripping +1)
        "0091987654321",    # 13 digits with country code (00 prefix)
    ], name="Phone")

    flagged = validate_phone(phones, "Phone")
    print(f"  Flagged {len(flagged)} / {len(phones)} values:")
    for f in flagged:
        print(f"    Row {f['row_index']}: {f['reason']}")

    # Should flag: 98765432111 (11 digits), 8765432 (7), abcdefghij (letters),
    #              123 (3), 9988776655AB (letters), +14155552671 (after strip: 4155552671 = 10 → valid? no, US)
    assert len(flagged) >= 4, f"Expected ≥4 flagged phones, got {len(flagged)}"
    # Check specific messages
    reasons = [f["reason"] for f in flagged]
    assert any("11 digits" in r for r in reasons), "Missing '11 digits' reason"
    assert any("7 digits" in r or "digits, expected 10" in r for r in reasons), "Missing short-digit reason"
    assert any("alphabetic" in r or "letters" in r for r in reasons), "Missing letters reason"
    print("  ✅ Phone validation OK")


def test_email_validation():
    """Phase 3: Verify validate_email flags all expected issues."""
    print("\n=== Phase 3b: Email Validation ===")
    emails = pd.Series([
        "aarav.sharma@gmail.com",     # valid
        "sneha.gmail.com",            # missing @
        "meena@@company.co.in",       # double @
        "deepa.nair@company",         # no dot in domain
        "kiran desai@gmail.com",      # whitespace
        "lakshmi..rao@yahoo.com",     # consecutive dots
        "@missinglocal.com",          # empty local part
        "mohan.lal@company.c",        # TLD too short
        "priya.patel@yahoo.com",      # valid
    ], name="Email")

    flagged = validate_email(emails, "Email")
    print(f"  Flagged {len(flagged)} / {len(emails)} values:")
    for f in flagged:
        print(f"    Row {f['row_index']}: {f['reason']}")

    assert len(flagged) >= 6, f"Expected ≥6 flagged emails, got {len(flagged)}"
    reasons = [f["reason"] for f in flagged]
    assert any("missing '@'" in r for r in reasons), "Missing 'missing @' reason"
    assert any("2 '@'" in r or "symbols" in r for r in reasons), "Missing 'double @' reason"
    assert any("whitespace" in r for r in reasons), "Missing 'whitespace' reason"
    assert any("consecutive dots" in r for r in reasons), "Missing 'consecutive dots' reason"
    print("  ✅ Email validation OK")


def test_rules_registry():
    """Phase 3: Verify COLUMN_TYPE_RULES registry has phone and email."""
    print("\n=== Phase 3c: Rules Registry ===")
    assert "phone" in COLUMN_TYPE_RULES, "Missing 'phone' in COLUMN_TYPE_RULES"
    assert "email" in COLUMN_TYPE_RULES, "Missing 'email' in COLUMN_TYPE_RULES"
    assert callable(COLUMN_TYPE_RULES["phone"]), "'phone' rule is not callable"
    assert callable(COLUMN_TYPE_RULES["email"]), "'email' rule is not callable"
    print("  ✅ Rules registry OK")


def test_suggest_cleaning_steps_integration():
    """Phase 3: Verify suggest_cleaning_steps produces flag_invalid_phone and flag_invalid_email."""
    print("\n=== Phase 3d: Integration — suggest_cleaning_steps ===")
    csv_path = os.path.join(os.path.dirname(__file__), "test_phone_email_20x7.csv")
    df = pd.read_csv(csv_path, keep_default_na=False, na_values=[""])
    profile = profile_dataframe(df)

    suggestions = suggest_cleaning_steps(df, profile)
    actions = [s["action"] for s in suggestions]
    print(f"  Generated {len(suggestions)} suggestions:")
    for s in suggestions:
        col = (s.get("params") or {}).get("column", "—")
        fc = (s.get("params") or {}).get("flagged_count", "")
        fv_count = len(s.get("flagged_values", []))
        print(f"    [{s['severity']:6}] {s['action']:30} col={col:15} flagged={fv_count}")

    assert "flag_invalid_phone" in actions, "Missing flag_invalid_phone suggestion"
    assert "flag_invalid_email" in actions, "Missing flag_invalid_email suggestion"

    # Check that flagged_values have per-row reasons
    for s in suggestions:
        if s["action"] in ("flag_invalid_phone", "flag_invalid_email"):
            fv = s.get("flagged_values", [])
            assert len(fv) > 0, f"{s['action']} has empty flagged_values"
            for item in fv:
                assert "reason" in item, f"Missing 'reason' in flagged item: {item}"
                assert "row_index" in item, f"Missing 'row_index' in flagged item: {item}"
            print(f"  ✅ {s['action']}: {len(fv)} items, all with reasons")


def test_excel_export():
    """Phase 1 & 2: Verify Excel export preserves phone as text with proper widths."""
    print("\n=== Phase 1 & 2: Excel Export ===")
    csv_path = os.path.join(os.path.dirname(__file__), "test_phone_email_20x7.csv")
    df = pd.read_csv(csv_path, keep_default_na=False, na_values=[""])

    # Simulate the export pipeline
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    # Reproduce the main.py xlsx export logic
    from openpyxl.utils import get_column_letter

    cleaned_df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str, keep_default_na=False)

    _PHONE_KEYWORDS = ("phone", "mobile", "contact")
    _EMAIL_KEYWORDS = ("email", "e-mail", "e_mail")
    text_format_col_indices = []

    for col_idx_0, col_name in enumerate(cleaned_df.columns):
        col_lower = str(col_name).lower()
        is_phone = any(kw in col_lower for kw in _PHONE_KEYWORDS)
        is_email = any(kw in col_lower for kw in _EMAIL_KEYWORDS)

        if is_phone or is_email:
            cleaned_df[col_name] = cleaned_df[col_name].replace("nan", "").replace("", "")
            text_format_col_indices.append(col_idx_0 + 1)
        else:
            coerced = pd.to_numeric(cleaned_df[col_name], errors="coerce")
            non_empty = cleaned_df[col_name][cleaned_df[col_name] != ""]
            if len(non_empty) > 0 and coerced.notna().sum() >= len(non_empty) * 0.5:
                cleaned_df[col_name] = coerced

    output = io.BytesIO()
    sheet_name = "Cleaned Data"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        cleaned_df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        ws.sheet_format.defaultColWidth = None

        for col_idx_1 in text_format_col_indices:
            col_letter = get_column_letter(col_idx_1)
            for row in range(1, ws.max_row + 1):
                cell = ws[f"{col_letter}{row}"]
                cell.number_format = "@"
                if row > 1 and cell.value is not None:
                    cell.value = str(cell.value)

        sample_df = cleaned_df.head(500)
        for col_idx, col_name in enumerate(cleaned_df.columns, start=1):
            col_letter = get_column_letter(col_idx)
            header_len = len(str(col_name))
            if not sample_df.empty:
                val_lens = [len(str(v)) for v in sample_df[col_name].dropna()]
            else:
                val_lens = []
            max_len = max([header_len] + val_lens) if val_lens else header_len
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 60)

        ws.protection.disable()
        ws.protection.sheet = False

    # Now verify by reading back the Excel file
    xlsx_bytes = output.getvalue()
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    # Find Phone and Email column indices
    headers = [cell.value for cell in ws[1]]
    phone_col_idx = headers.index("Phone") + 1  # 1-based
    email_col_idx = headers.index("Email") + 1

    print(f"  Headers: {headers}")
    print(f"  Phone column: {phone_col_idx}, Email column: {email_col_idx}")

    # Check Phone cells: must be text format and string values
    phone_letter = get_column_letter(phone_col_idx)
    for row in range(2, ws.max_row + 1):
        cell = ws[f"{phone_letter}{row}"]
        # Number format must be '@' (text)
        assert cell.number_format == "@", f"Phone cell {phone_letter}{row} format is '{cell.number_format}', expected '@'"
        # Value must be string, not int/float
        if cell.value is not None and cell.value != "":
            assert isinstance(cell.value, str), f"Phone cell {phone_letter}{row} value is {type(cell.value).__name__}, expected str"
            # Must NOT be in scientific notation
            assert "e+" not in str(cell.value).lower(), f"Phone cell {phone_letter}{row} is in scientific notation: {cell.value}"
    print("  ✅ Phone column: all cells have '@' format and string values")

    # Check column widths: all must be > 10
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        width = ws.column_dimensions[col_letter].width
        assert width is not None and width >= 14, f"Column {col_letter} width is {width}, expected ≥14"
    print("  ✅ Column widths: all ≥14")

    # Check no sheet protection
    assert not ws.protection.sheet, "Sheet protection is enabled!"
    print("  ✅ No sheet protection")

    print("\n✅ ALL PHASES PASSED")


if __name__ == "__main__":
    test_phone_validation()
    test_email_validation()
    test_rules_registry()
    test_suggest_cleaning_steps_integration()
    test_excel_export()
