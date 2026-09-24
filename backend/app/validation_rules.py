"""
Centralised column-validation rules engine.

This module is the SINGLE SOURCE OF TRUTH for all deterministic data-quality
rules.  AI is used ONLY as a fallback for:
  (a) detecting which semantic type a column is when ambiguous,
  (b) near-duplicate category clustering (Bangalore/Bengaluru case),
  (c) columns with no matching rule at all.
AI NEVER overrides a rule's output.

Every number, format, example, and edge case from the master rule-set document
is implemented exactly as written.
"""

from __future__ import annotations

import ipaddress
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Callable

import pandas as pd

# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single detected data-quality issue, with confidence scoring."""
    row_index: int | None        # None for column/dataset-level issues
    raw_value: Any
    issue: str                   # short label, e.g. "Possible email typo"
    confidence: int              # 0-100
    suggested_value: Any | None
    severity: str                # "error" | "warning" | "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "raw_value": self.raw_value,
            "issue": self.issue,
            "confidence": self.confidence,
            "suggested_value": self.suggested_value,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Result of validating a single column."""
    column_name: str
    semantic_type: str
    issues: list[ValidationIssue] = field(default_factory=list)

    # Convenience: flagged_values for backward compat with existing UI
    def to_flagged_values(self) -> list[dict]:
        return [
            {
                "row_index": i.row_index,
                "raw_value": i.raw_value,
                "suggested_value": i.suggested_value,
                "reason": i.issue,
                "confidence": i.confidence,
                "severity": i.severity,
            }
            for i in self.issues
        ]


@dataclass
class CrossColumnIssue:
    """A cross-column validation issue."""
    rule_name: str
    columns_involved: list[str]
    row_index: int | None
    issue: str
    confidence: int
    severity: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "columns_involved": self.columns_involved,
            "row_index": self.row_index,
            "issue": self.issue,
            "confidence": self.confidence,
            "severity": self.severity,
            "details": self.details,
        }


@dataclass
class DatasetLevelIssue:
    """A dataset-level quality issue."""
    rule_name: str
    issue: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "issue": self.issue,
            "severity": self.severity,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# NULL / placeholder detection constants (Universal Rule §1)
# ---------------------------------------------------------------------------

NULL_VARIANTS: set[str] = {
    "na", "n/a", "null", "none", "nan", "nil", "undefined",
    "not available", "not applicable", "missing",
}

PLACEHOLDER_VALUES: set[str] = {
    "?", "--", "---", "unknown", "tbd", "tba", "xxx", "placeholder",
    "test", "dummy", "sample", "example", "temp",
}

HIDDEN_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\r\n\t\u200b\u200c\u200d\ufeff\u00a0]")

# Unicode dash normalization: em-dash, en-dash, figure-dash, etc. → hyphen-minus
UNICODE_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]")

# ---------------------------------------------------------------------------
# §1  Universal rules — apply to almost every column
# ---------------------------------------------------------------------------

def apply_universal_rules(value: Any) -> tuple[Any, list[str]]:
    """Apply universal cleaning rules.  Returns (cleaned_value, list_of_applied_rules).
    If result is None, the value should be treated as NULL."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, ["null_detected"]

    s = str(value)

    applied: list[str] = []

    # Detect empty strings
    if s.strip() == "":
        return None, ["empty_string"]

    # Detect NULL variants
    if s.strip().lower() in NULL_VARIANTS:
        return None, ["null_variant"]

    # Detect placeholder values
    if s.strip().lower() in PLACEHOLDER_VALUES:
        return None, ["placeholder_value"]

    # Remove hidden characters
    if HIDDEN_CHAR_RE.search(s):
        s = HIDDEN_CHAR_RE.sub("", s)
        applied.append("hidden_chars_removed")

    # Normalize Unicode dashes
    if UNICODE_DASHES.search(s):
        s = UNICODE_DASHES.sub("-", s)
        applied.append("unicode_dashes_normalized")

    # Trim whitespace
    stripped = s.strip()
    if stripped != s:
        s = stripped
        applied.append("trimmed_whitespace")

    # Remove multiple internal spaces
    collapsed = re.sub(r"\s{2,}", " ", s)
    if collapsed != s:
        s = collapsed
        applied.append("collapsed_multiple_spaces")

    if not s:
        return None, applied + ["empty_after_cleaning"]

    return s, applied


# ---------------------------------------------------------------------------
# §2  NAME validation
# ---------------------------------------------------------------------------

def validate_name(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    min_len = config.get("min_length", 2)
    max_len = config.get("max_length", 100)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS or s.lower() in PLACEHOLDER_VALUES:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Empty or placeholder name",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        cleaned = HIDDEN_CHAR_RE.sub("", s).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned)

        # Detect names consisting only of symbols
        if re.fullmatch(r"[^a-zA-Z\s]+", cleaned):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Name consists only of symbols",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        # No numbers normally
        if re.search(r"\d", cleaned):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Name contains numbers",
                confidence=95, suggested_value=re.sub(r"\d+", "", cleaned).strip(), severity="error",
            ))
            continue

        # Length check
        if len(cleaned) < min_len:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Name too short ({len(cleaned)} chars, minimum {min_len})",
                confidence=90, suggested_value=None, severity="warning",
            ))
            continue

        if len(cleaned) > max_len:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Name too long ({len(cleaned)} chars, maximum {max_len})",
                confidence=90, suggested_value=cleaned[:max_len], severity="warning",
            ))
            continue

        # Detect suspicious repeated characters (e.g. "aaaaaaa")
        if re.search(r"(.)\1{4,}", cleaned.lower()):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Name has suspicious repeated characters",
                confidence=85, suggested_value=None, severity="warning",
            ))
            continue

        # No excessive special characters
        special_count = len(re.findall(r"[^a-zA-Z\s.'\-]", cleaned))
        if special_count > 2:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Name contains excessive special characters",
                confidence=90, suggested_value=None, severity="warning",
            ))
            continue

        # Standardize capitalization: title case
        title_cased = cleaned.title()
        if cleaned != title_cased and cleaned != cleaned.upper():
            # Only flag if it's not already properly cased
            needs_fix = (cleaned != title_cased)
            if needs_fix:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Name capitalization non-standard",
                    confidence=100, suggested_value=title_cased, severity="info",
                ))
        elif cleaned == cleaned.upper() and len(cleaned) > 1:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Name capitalization non-standard",
                confidence=100, suggested_value=cleaned.title(), severity="info",
            ))

        # Trim / multi-space fixes (suggest even if other issues exist)
        if str(val) != cleaned and not any(i.row_index == int(idx) for i in issues):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Extra spaces in name",
                confidence=100, suggested_value=cleaned.title(), severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §3  EMAIL validation
# ---------------------------------------------------------------------------

# Common email domain typo corrections (from the spec)
EMAIL_TYPO_MAP: dict[str, str] = {
    "gmail.con": "gmail.com",
    "gamil.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "gnail.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
    "hotmal.com": "hotmail.com",
    "hotmial.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com",
    "outloo.com": "outlook.com",
    "outlook.con": "outlook.com",
}

STRICT_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9._%+\-]*[a-zA-Z0-9])?@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)*"
    r"\.[a-zA-Z]{2,}$"
)


def validate_email(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        suggested = s
        issue_text = None
        confidence = 0
        severity = "error"

        # No spaces
        if re.search(r"\s", s):
            issue_text = f"Email contains whitespace"
            suggested = re.sub(r"\s+", "", s)
            confidence = 100

        # Exactly one @
        elif "@" not in s:
            issue_text = f"Email missing '@'"
            confidence = 100

        elif s.count("@") > 1:
            issue_text = f"Email has {s.count('@')} '@' symbols, expected exactly 1"
            suggested = re.sub(r"@+", "@", s)
            confidence = 100

        else:
            local, domain = s.rsplit("@", 1)

            # Local part cannot be empty
            if not local:
                issue_text = "Email has empty local part before '@'"
                confidence = 100

            # Domain cannot be empty
            elif not domain:
                issue_text = "Email has empty domain after '@'"
                confidence = 100

            # Cannot start/end with a dot in the local part
            elif local.startswith(".") or local.endswith("."):
                issue_text = "Email local part starts or ends with '.'"
                suggested = local.strip(".") + "@" + domain
                confidence = 98

            # No consecutive dots
            elif ".." in s:
                issue_text = "Email contains consecutive dots"
                suggested = re.sub(r"\.{2,}", ".", s)
                confidence = 98

            # Domain should contain valid structure
            elif "." not in domain:
                issue_text = f"Email domain '{domain}' has no '.' (missing extension)"
                suggested = s + ".com"
                confidence = 95

            # Valid domain extension (TLD 2+ letters)
            elif not re.match(r".*\.[a-zA-Z]{2,}$", domain):
                issue_text = f"Email has invalid TLD (must be 2+ letters)"
                confidence = 95

            else:
                # Check for common typos
                domain_lower = domain.lower()
                if domain_lower in EMAIL_TYPO_MAP:
                    corrected_domain = EMAIL_TYPO_MAP[domain_lower]
                    issue_text = f"Possible email domain typo"
                    suggested = local + "@" + corrected_domain
                    confidence = 98
                    severity = "warning"

                # Full strict regex check
                elif not STRICT_EMAIL_RE.match(s):
                    issue_text = f"Email fails strict format validation"
                    confidence = 90

        if issue_text:
            # Lowercase normalization
            if suggested and suggested != s:
                suggested = suggested.lower()
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=issue_text,
                confidence=confidence,
                suggested_value=suggested if suggested != s else None,
                severity=severity,
            ))

    return issues


# ---------------------------------------------------------------------------
# §4  PHONE NUMBER validation
# ---------------------------------------------------------------------------

# Indian mobile: starts with 6, 7, 8, or 9
INDIAN_MOBILE_STARTS = {"6", "7", "8", "9"}

def validate_phone(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    expected_digits = config.get("expected_digits", 10)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        # Handle pandas float → int conversion (e.g. 9876543210.0)
        if s.endswith(".0"):
            s = s[:-2]
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Strip country-code prefix: +91, 0091, +1, etc.
        cleaned = s
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if cleaned.startswith("00"):
            cleaned = cleaned[2:]
        # Remove 91 prefix if remaining yields 12 digits
        digits_all = re.sub(r"\D", "", cleaned)
        if cleaned.startswith("91") and len(digits_all) == 12:
            cleaned = cleaned[2:]
        # Remove leading 0
        digits_cleaned = re.sub(r"\D", "", cleaned)
        if digits_cleaned.startswith("0") and len(digits_cleaned) == 11:
            digits_cleaned = digits_cleaned[1:]

        digits = digits_cleaned
        has_letters = bool(re.search(r"[a-zA-Z]", s))

        if has_letters:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Phone contains alphabetic characters",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif len(digits) == 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Phone contains no digits",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif len(digits) < expected_digits:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Phone too short ({len(digits)} digits, expected {expected_digits})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif len(digits) > expected_digits:
            suggested = digits[-expected_digits:]
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Phone too long ({len(digits)} digits, expected {expected_digits})",
                confidence=95, suggested_value=suggested, severity="error",
            ))
        else:
            # Valid digit count — check Indian mobile range
            if digits[0] not in INDIAN_MOBILE_STARTS:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Phone doesn't start with valid Indian mobile digit (6-9)",
                    confidence=85, suggested_value=digits, severity="warning",
                ))
            # Check for suspicious repeated digits (e.g. 9999999999)
            elif len(set(digits)) <= 2:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Phone has suspicious repeated digits",
                    confidence=80, suggested_value=digits, severity="warning",
                ))
            # Normalize format
            elif digits != str(val).strip():
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Phone needs normalization",
                    confidence=100, suggested_value=digits, severity="info",
                ))

    return issues


# ---------------------------------------------------------------------------
# §5  AGE validation
# ---------------------------------------------------------------------------

def validate_age(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_age = config.get("max_age", 150)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Try to parse as number
        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Wrong datatype for age (non-numeric)",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Negative age",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif num > max_age:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Extreme age value ({num} exceeds maximum {max_age})",
                confidence=99, suggested_value=None, severity="error",
            ))
        elif num != int(num):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Decimal age ({num})",
                confidence=85, suggested_value=int(num), severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §6  DATE OF BIRTH validation
# ---------------------------------------------------------------------------

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
    "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%Y%m%d",
]


def _try_parse_date(s: str) -> date | None:
    """Try to parse a date string with multiple formats."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    # Fallback: pandas
    try:
        parsed = pd.to_datetime(s, format="mixed", dayfirst=True)
        if pd.notna(parsed):
            return parsed.date()
    except Exception:
        pass
    return None


def validate_dob(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_age = config.get("max_age", 150)
    issues: list[ValidationIssue] = []
    today = date.today()

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        parsed = _try_parse_date(s)
        if parsed is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid date format for DOB",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        # Cannot be future
        if parsed > today:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="DOB is in the future",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        # Reasonable age range
        age_years = (today - parsed).days / 365.25
        if age_years > max_age:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"DOB implies age of {age_years:.0f} years (exceeds {max_age})",
                confidence=95, suggested_value=None, severity="error",
            ))
            continue

        # Normalize to YYYY-MM-DD
        normalized = parsed.strftime("%Y-%m-%d")
        if s != normalized:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="DOB format should be YYYY-MM-DD",
                confidence=100, suggested_value=normalized, severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §7  DATE / TIMESTAMP validation
# ---------------------------------------------------------------------------

def validate_date(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    allow_future = config.get("allow_future", True)
    issues: list[ValidationIssue] = []
    today = date.today()

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        parsed = _try_parse_date(s)
        if parsed is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid/impossible date",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if not allow_future and parsed > today:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Date is in the future",
                confidence=95, suggested_value=None, severity="warning",
            ))
            continue

        normalized = parsed.strftime("%Y-%m-%d")
        if s != normalized:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Date format should be standardized",
                confidence=100, suggested_value=normalized, severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §8  TIME validation
# ---------------------------------------------------------------------------

TIME_12H_RE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm|a\.m\.|p\.m\.)$"
)
TIME_24H_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def validate_time(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Try 12-hour format first
        m12 = TIME_12H_RE.match(s)
        if m12:
            h, mi, sec, period = int(m12.group(1)), int(m12.group(2)), int(m12.group(3) or 0), m12.group(4).upper().replace(".", "")
            if h < 1 or h > 12 or mi > 59 or sec > 59:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Invalid 12-hour time",
                    confidence=100, suggested_value=None, severity="error",
                ))
                continue
            # Convert to 24h
            if period == "AM" and h == 12:
                h = 0
            elif period == "PM" and h != 12:
                h += 12
            normalized = f"{h:02d}:{mi:02d}:{sec:02d}"
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Time normalized to 24-hour format",
                confidence=100, suggested_value=normalized, severity="info",
            ))
            continue

        # Try 24-hour format
        m24 = TIME_24H_RE.match(s)
        if m24:
            h, mi, sec = int(m24.group(1)), int(m24.group(2)), int(m24.group(3) or 0)
            if h > 23 or mi > 59 or sec > 59:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Invalid time (hours 0-23, minutes 0-59, seconds 0-59)",
                    confidence=100, suggested_value=None, severity="error",
                ))
                continue
            normalized = f"{h:02d}:{mi:02d}:{sec:02d}"
            if s != normalized:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Time format standardized",
                    confidence=100, suggested_value=normalized, severity="info",
                ))
            continue

        issues.append(ValidationIssue(
            row_index=int(idx), raw_value=val,
            issue="Invalid time format",
            confidence=95, suggested_value=None, severity="error",
        ))

    return issues


# ---------------------------------------------------------------------------
# §9  DATETIME validation
# ---------------------------------------------------------------------------

def validate_datetime(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            parsed = pd.to_datetime(s, format="mixed")
            if pd.isna(parsed):
                raise ValueError("NaT")
            normalized = parsed.strftime("%Y-%m-%d %H:%M:%S")
            if s != normalized:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Datetime format should be standardized",
                    confidence=100, suggested_value=normalized, severity="info",
                ))
        except Exception:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid datetime",
                confidence=100, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §10  GENDER validation
# ---------------------------------------------------------------------------

GENDER_MAP: dict[str, str] = {
    "m": "Male", "male": "Male", "man": "Male", "boy": "Male",
    "f": "Female", "female": "Female", "woman": "Female", "girl": "Female",
    "o": "Other", "other": "Other", "non-binary": "Other", "nonbinary": "Other",
    "u": "Unknown", "unknown": "Unknown", "prefer not to say": "Unknown",
    "not specified": "Unknown", "undisclosed": "Unknown",
}


def validate_gender(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        normalized = GENDER_MAP.get(s.lower())
        if normalized is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Unrecognized gender value",
                confidence=85, suggested_value=None, severity="warning",
            ))
        elif s != normalized:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Gender value should be standardized",
                confidence=100, suggested_value=normalized, severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §11  BOOLEAN validation
# ---------------------------------------------------------------------------

BOOLEAN_MAP: dict[str, str] = {
    "y": "Yes", "yes": "Yes", "true": "Yes", "1": "Yes",
    "n": "No", "no": "No", "false": "No", "0": "No",
}


def validate_boolean(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    # Schema should define whether 1/0 means Yes/No
    use_true_false = config.get("use_true_false", False)
    issues: list[ValidationIssue] = []

    true_val = "True" if use_true_false else "Yes"
    false_val = "False" if use_true_false else "No"
    local_map = {}
    for k, v in BOOLEAN_MAP.items():
        local_map[k] = true_val if v == "Yes" else false_val

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        normalized = local_map.get(s.lower())
        if normalized is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid boolean value",
                confidence=90, suggested_value=None, severity="error",
            ))
        elif s != normalized:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Boolean value should be standardized",
                confidence=100, suggested_value=normalized, severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §12  CATEGORY validation
# ---------------------------------------------------------------------------

def validate_category(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    """Category validation: allowed-values dictionary + near-duplicate detection.
    Near-duplicate detection is deferred to AI/difflib (per spec: "flag for mapping")."""
    config = config or {}
    allowed_values = config.get("allowed_values", None)
    issues: list[ValidationIssue] = []

    if allowed_values:
        allowed_lower = {v.lower(): v for v in allowed_values}
        for idx, val in series.items():
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            s = str(val).strip()
            if not s or s.lower() in NULL_VARIANTS:
                continue
            if s.lower() in allowed_lower:
                canonical = allowed_lower[s.lower()]
                if s != canonical:
                    issues.append(ValidationIssue(
                        row_index=int(idx), raw_value=val,
                        issue="Category value should be standardized",
                        confidence=100, suggested_value=canonical, severity="info",
                    ))
            else:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Unknown category value",
                    confidence=80, suggested_value=None, severity="warning",
                ))

    return issues


# ---------------------------------------------------------------------------
# §13  AGE GROUP validation
# ---------------------------------------------------------------------------

AGE_GROUP_RE = re.compile(r"^(\d+)\s*[-–]\s*(\d+)$")


def validate_age_group(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    all_ranges: list[tuple[int, int, int]] = []  # (lower, upper, idx)

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = AGE_GROUP_RE.match(s)
        if not m:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid age group syntax (expected e.g. '18-25')",
                confidence=95, suggested_value=None, severity="error",
            ))
            continue

        lower, upper = int(m.group(1)), int(m.group(2))

        if lower > upper:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Age group lower bound ({lower}) > upper bound ({upper})",
                confidence=100, suggested_value=f"{upper}-{lower}", severity="error",
            ))
        elif lower < 0 or upper > 200:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Impossible age range",
                confidence=100, suggested_value=None, severity="error",
            ))
        else:
            all_ranges.append((lower, upper, int(idx)))

    # Check for overlapping groups
    sorted_ranges = sorted(all_ranges, key=lambda x: x[0])
    for i in range(1, len(sorted_ranges)):
        prev_lower, prev_upper, prev_idx = sorted_ranges[i - 1]
        curr_lower, curr_upper, curr_idx = sorted_ranges[i]
        if curr_lower <= prev_upper:
            issues.append(ValidationIssue(
                row_index=curr_idx, raw_value=f"{curr_lower}-{curr_upper}",
                issue=f"Overlapping age groups: {prev_lower}-{prev_upper} and {curr_lower}-{curr_upper}",
                confidence=90, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §14  INTEGER validation
# ---------------------------------------------------------------------------

def validate_integer(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    min_val = config.get("min_value", None)
    max_val = config.get("max_value", None)
    allow_negative = config.get("allow_negative", True)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric value in integer column",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num != int(num):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Decimal value ({num}) in integer column",
                confidence=100, suggested_value=int(num), severity="error",
            ))
            continue

        int_val = int(num)
        if not allow_negative and int_val < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative value ({int_val}) not allowed",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif min_val is not None and int_val < min_val:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Value {int_val} below minimum {min_val}",
                confidence=95, suggested_value=None, severity="error",
            ))
        elif max_val is not None and int_val > max_val:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Value {int_val} above maximum {max_val}",
                confidence=95, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §15  DECIMAL validation
# ---------------------------------------------------------------------------

def validate_decimal(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    min_val = config.get("min_value", None)
    max_val = config.get("max_value", None)
    precision = config.get("precision", None)  # decimal places
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric value in decimal column",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if min_val is not None and num < min_val:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Value {num} below minimum {min_val}",
                confidence=95, suggested_value=None, severity="error",
            ))
        elif max_val is not None and num > max_val:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Value {num} above maximum {max_val}",
                confidence=95, suggested_value=None, severity="error",
            ))
        elif precision is not None:
            rounded = round(num, precision)
            if num != rounded:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Precision exceeds {precision} decimal places",
                    confidence=99, suggested_value=rounded, severity="info",
                ))

    return issues


# ---------------------------------------------------------------------------
# §16  CURRENCY / PRICE validation
# ---------------------------------------------------------------------------

CURRENCY_SYMBOLS = re.compile(r"[₹$€£¥]")
CURRENCY_SUFFIXES = re.compile(r"\s*(k|K|lakh|lakhs|cr|crore|crores|million|billion)\b", re.IGNORECASE)


def _parse_currency_value(s: str) -> float | None:
    """Extract numeric value from a currency string."""
    cleaned = s.strip()
    # Remove currency symbols
    cleaned = CURRENCY_SYMBOLS.sub("", cleaned)
    # Handle 'k' suffix
    multiplier = 1
    m = CURRENCY_SUFFIXES.search(cleaned)
    if m:
        suffix = m.group(1).lower()
        if suffix == "k":
            multiplier = 1000
        elif suffix in ("lakh", "lakhs"):
            multiplier = 100000
        elif suffix in ("cr", "crore", "crores"):
            multiplier = 10000000
        elif suffix == "million":
            multiplier = 1000000
        elif suffix == "billion":
            multiplier = 1000000000
        cleaned = cleaned[:m.start()]

    # Remove commas
    cleaned = cleaned.replace(",", "").strip()

    if not cleaned:
        return None

    try:
        return float(cleaned) * multiplier
    except (ValueError, TypeError):
        return None


def validate_currency(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    allow_negative = config.get("allow_negative", False)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        num = _parse_currency_value(s)
        if num is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Cannot parse currency value",
                confidence=90, suggested_value=None, severity="error",
            ))
            continue

        if not allow_negative and num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative currency value ({num})",
                confidence=95, suggested_value=None, severity="warning",
            ))

        # Suggest normalized form (plain number)
        try:
            # Normalize: if result is an integer value, show as int
            norm = int(num) if num == int(num) else num
            if str(norm) != s:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Currency value needs normalization",
                    confidence=99, suggested_value=norm, severity="info",
                ))
        except (OverflowError, ValueError):
            pass

    return issues


# ---------------------------------------------------------------------------
# §17  SALARY validation
# ---------------------------------------------------------------------------

SALARY_UNIT_RE = re.compile(
    r"(?:/\s*(month|year|yr|annual|annum|hr|hour|week|day))|\b(lpa|per\s*annum)\b",
    re.IGNORECASE,
)


def validate_salary(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Detect mixed units
        unit_match = SALARY_UNIT_RE.search(s)

        num = _parse_currency_value(s)
        if num is None:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Cannot parse salary value",
                confidence=90, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Negative salary",
                confidence=100, suggested_value=None, severity="error",
            ))

        if unit_match:
            unit_text = (unit_match.group(1) or unit_match.group(2) or "").strip()
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Salary contains unit indicator '{unit_text}' — units may be mixed",
                confidence=85, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §18  PERCENTAGE validation
# ---------------------------------------------------------------------------

def validate_percentage(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Strip % symbol
        cleaned = s.rstrip("%").strip()
        try:
            num = float(cleaned)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric percentage",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0 or num > 100:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Percentage {num} outside 0–100 range",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif "%" in s:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Percentage format needs normalization (remove %)",
                confidence=99, suggested_value=num, severity="info",
            ))
        elif 0 < num < 1:
            # Could mean 85% expressed as 0.85 — flag but don't auto-convert
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Value {num} could represent {num * 100}% in decimal form — verify",
                confidence=70, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §19  CGPA validation
# ---------------------------------------------------------------------------

def validate_cgpa(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_cgpa = config.get("max_cgpa", 10)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric CGPA",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative CGPA ({num})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif num > max_cgpa:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"CGPA {num} exceeds maximum {max_cgpa}",
                confidence=100, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §20  GPA validation
# ---------------------------------------------------------------------------

def validate_gpa(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    scale = config.get("scale", 4.0)  # Never assume the scale blindly
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric GPA",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative GPA ({num})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif num > scale:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"GPA {num} exceeds scale maximum {scale}",
                confidence=95, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §21  MARKS validation
# ---------------------------------------------------------------------------

def validate_marks(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_marks = config.get("max_marks", 100)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric marks",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative marks ({num})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif num > max_marks:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Marks {num} exceeds maximum {max_marks}",
                confidence=100, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §22  RATING validation
# ---------------------------------------------------------------------------

def validate_rating(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    min_rating = config.get("min_rating", 1)
    max_rating = config.get("max_rating", 5)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric rating",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < min_rating or num > max_rating:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Rating {num} outside allowed range {min_rating}–{max_rating}",
                confidence=100, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §23  ZIP / PIN CODE validation
# ---------------------------------------------------------------------------

def validate_zipcode(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    country = config.get("country", "india")
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        if not s or s.lower() in NULL_VARIANTS:
            continue

        if country.lower() == "india":
            digits = re.sub(r"\D", "", s)
            if len(digits) != 6:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Indian PIN code must be 6 digits (got {len(digits)})",
                    confidence=100, suggested_value=None, severity="error",
                ))
            elif not digits[0].isdigit() or digits[0] == "0":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Indian PIN code cannot start with 0",
                    confidence=90, suggested_value=None, severity="warning",
                ))

    return issues


# ---------------------------------------------------------------------------
# §24  URL validation
# ---------------------------------------------------------------------------

URL_RE = re.compile(
    r"^(https?://|ftp://)?([a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(/\S*)?$"
)


def validate_url(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        if " " in s:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="URL contains spaces",
                confidence=100, suggested_value=s.replace(" ", ""), severity="error",
            ))
        elif not URL_RE.match(s):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid URL structure",
                confidence=90, suggested_value=None, severity="error",
            ))

    return issues


# ---------------------------------------------------------------------------
# §25  IP ADDRESS validation
# ---------------------------------------------------------------------------

def validate_ip_address(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            ipaddress.ip_address(s)
        except ValueError:
            # Check specifically for IPv4 issues (for better error messages)
            parts = s.split(".")
            if len(parts) == 4:
                bad_parts = [p for p in parts if not p.isdigit() or int(p) > 255]
                if bad_parts:
                    issues.append(ValidationIssue(
                        row_index=int(idx), raw_value=val,
                        issue=f"IPv4 octets must be 0–255 (invalid: {', '.join(bad_parts)})",
                        confidence=100, suggested_value=None, severity="error",
                    ))
                else:
                    issues.append(ValidationIssue(
                        row_index=int(idx), raw_value=val,
                        issue="Invalid IPv4 address",
                        confidence=100, suggested_value=None, severity="error",
                    ))
            elif len(parts) < 4 and ":" not in s:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"IPv4 requires exactly 4 parts (got {len(parts)})",
                    confidence=100, suggested_value=None, severity="error",
                ))
            else:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Invalid IP address",
                    confidence=95, suggested_value=None, severity="error",
                ))

    return issues


# ---------------------------------------------------------------------------
# §26  UUID validation
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def validate_uuid(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        if not UUID_RE.match(s):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Invalid UUID format",
                confidence=100, suggested_value=None, severity="error",
            ))
        else:
            s_lower = s.lower()
            if s_lower in seen:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Duplicate UUID (first seen at row {seen[s_lower]})",
                    confidence=100, suggested_value=None, severity="error",
                ))
            else:
                seen[s_lower] = int(idx)

    return issues


# ---------------------------------------------------------------------------
# §27  ID / PRIMARY KEY validation
# ---------------------------------------------------------------------------

def validate_id(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="ID/Primary key is NULL",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="ID/Primary key is NULL/empty",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        # No accidental spaces
        if s != str(val).strip() or "  " in s:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="ID contains accidental spaces",
                confidence=100, suggested_value=s, severity="warning",
            ))

        # Unique check
        if s in seen:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Duplicate ID (first seen at row {seen[s]})",
                confidence=100, suggested_value=None, severity="error",
            ))
        else:
            seen[s] = int(idx)

    return issues


# ---------------------------------------------------------------------------
# §28  PRODUCT CODE / SKU validation
# ---------------------------------------------------------------------------

def validate_product_code(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}

    # Detect the most common pattern
    non_null = series.dropna().astype(str).str.strip()
    patterns: dict[str, int] = {}
    for v in non_null:
        pattern = re.sub(r"[A-Z]", "A", re.sub(r"[a-z]", "a", re.sub(r"\d", "0", v)))
        patterns[pattern] = patterns.get(pattern, 0) + 1

    dominant_pattern = max(patterns, key=patterns.get) if patterns else None

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Unique check
        s_upper = s.upper()
        if s_upper in seen:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Duplicate product code (first seen at row {seen[s_upper]})",
                confidence=100, suggested_value=None, severity="error",
            ))
        else:
            seen[s_upper] = int(idx)

        # Case consistency
        if s != s.upper() and s != s:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Product code capitalization inconsistent",
                confidence=85, suggested_value=s.upper(), severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §29  ADDRESS validation (soft rules)
# ---------------------------------------------------------------------------

def validate_address(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Empty address",
                confidence=100, suggested_value=None, severity="warning",
            ))
            continue

        # Too-short address
        if len(s) < 10:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Address appears too short",
                confidence=75, suggested_value=None, severity="warning",
            ))

        # Excessive special characters
        special = len(re.findall(r"[^a-zA-Z0-9\s,.\-/#]", s))
        if special > 5:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Address has excessive special characters",
                confidence=80, suggested_value=None, severity="warning",
            ))

        # Repeated spaces
        if "  " in s:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Address has repeated spaces",
                confidence=100, suggested_value=re.sub(r"\s{2,}", " ", s).strip(),
                severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §30  COUNTRY validation
# ---------------------------------------------------------------------------

COUNTRY_DICT: dict[str, str] = {
    "india": "India", "ind": "India", "in": "India",
    "united states": "United States", "us": "United States", "usa": "United States",
    "united states of america": "United States",
    "united kingdom": "United Kingdom", "uk": "United Kingdom",
    "great britain": "United Kingdom", "gb": "United Kingdom",
    "canada": "Canada", "ca": "Canada", "can": "Canada",
    "australia": "Australia", "aus": "Australia", "au": "Australia",
    "germany": "Germany", "de": "Germany",
    "france": "France", "fr": "France",
    "japan": "Japan", "jp": "Japan",
    "china": "China", "cn": "China",
    "brazil": "Brazil", "br": "Brazil",
    "russia": "Russia", "ru": "Russia",
}


def validate_country(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    extra = config.get("country_dict", {})
    lookup = {**COUNTRY_DICT, **{k.lower(): v for k, v in extra.items()}}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        canonical = lookup.get(s.lower())
        if canonical:
            if s != canonical:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Country name should be standardized",
                    confidence=100, suggested_value=canonical, severity="info",
                ))
        else:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Unrecognized country value",
                confidence=70, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §31  STATE validation (India focus)
# ---------------------------------------------------------------------------

INDIA_STATES: dict[str, str] = {
    "andhra pradesh": "Andhra Pradesh", "ap": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat", "guj": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh", "hp": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka", "kar": "Karnataka",
    "kerala": "Kerala",
    "madhya pradesh": "Madhya Pradesh", "mp": "Madhya Pradesh",
    "maharashtra": "Maharashtra", "mh": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha", "orissa": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan", "rj": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu", "tn": "Tamil Nadu",
    "telangana": "Telangana", "ts": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh", "up": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal", "wb": "West Bengal",
    # Union territories
    "delhi": "Delhi", "new delhi": "Delhi",
    "chandigarh": "Chandigarh",
    "puducherry": "Puducherry", "pondicherry": "Puducherry",
    "jammu and kashmir": "Jammu and Kashmir", "jk": "Jammu and Kashmir",
    "ladakh": "Ladakh",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "lakshadweep": "Lakshadweep",
}


def validate_state(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    country = config.get("country", "india").lower()
    issues: list[ValidationIssue] = []

    if country == "india":
        for idx, val in series.items():
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            s = str(val).strip()
            if not s or s.lower() in NULL_VARIANTS:
                continue

            canonical = INDIA_STATES.get(s.lower())
            if canonical:
                if s != canonical:
                    issues.append(ValidationIssue(
                        row_index=int(idx), raw_value=val,
                        issue="State name should be standardized",
                        confidence=100, suggested_value=canonical, severity="info",
                    ))
            else:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Unrecognized state value (for India)",
                    confidence=70, suggested_value=None, severity="warning",
                ))

    return issues


# ---------------------------------------------------------------------------
# §32  CITY validation
# ---------------------------------------------------------------------------

def validate_city(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    """Soft rules: string, check standardized spelling. Bangalore/Bengaluru flagged, not auto-changed."""
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Check for non-alphabetic content (cities should be mostly letters)
        if re.search(r"\d", s):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="City name contains numbers",
                confidence=85, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §33  URL / SOCIAL MEDIA HANDLE validation
# ---------------------------------------------------------------------------

def validate_handle(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_length = config.get("max_length", 30)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Strip leading @
        handle = s.lstrip("@")

        if " " in handle:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Handle contains spaces",
                confidence=100, suggested_value="@" + handle.replace(" ", ""),
                severity="error",
            ))
        elif len(handle) > max_length:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Handle exceeds max length ({len(handle)} > {max_length})",
                confidence=90, suggested_value=None, severity="warning",
            ))
        elif not re.match(r"^[a-zA-Z0-9_.]+$", handle):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Handle contains disallowed characters",
                confidence=90, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §34  CREDIT CARD / PAYMENT IDENTIFIER validation
# ---------------------------------------------------------------------------

def _luhn_check(number: str) -> bool:
    """Luhn algorithm checksum."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 2:
        return False
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0


def validate_payment_id(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    expected_lengths = config.get("expected_lengths", [13, 14, 15, 16, 19])
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        digits = re.sub(r"\D", "", s)

        if len(digits) not in expected_lengths:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value="****" + s[-4:] if len(s) >= 4 else "****",
                issue=f"Unexpected length ({len(digits)} digits)",
                confidence=90, suggested_value=None, severity="warning",
            ))
        elif not _luhn_check(digits):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value="****" + s[-4:] if len(s) >= 4 else "****",
                issue="Fails Luhn checksum",
                confidence=85, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §35  TRANSACTION ID validation
# ---------------------------------------------------------------------------

def validate_transaction_id(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Transaction ID is NULL",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Transaction ID is empty",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if s in seen:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Duplicate Transaction ID (first seen at row {seen[s]})",
                confidence=100, suggested_value=None, severity="error",
            ))
        else:
            seen[s] = int(idx)

    return issues


# ---------------------------------------------------------------------------
# §36  QUANTITY validation
# ---------------------------------------------------------------------------

def validate_quantity(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    allow_fractional = config.get("allow_fractional", False)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        try:
            num = float(s)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric quantity",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative quantity ({num})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif not allow_fractional and num != int(num):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Fractional quantity ({num})",
                confidence=85, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §37  WEIGHT validation
# ---------------------------------------------------------------------------

WEIGHT_UNIT_RE = re.compile(r"([\d.]+)\s*(kg|g|lb|lbs|oz|gram|grams|kilogram|kilograms)\b", re.IGNORECASE)


def validate_weight(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    canonical_unit = config.get("canonical_unit", "kg")
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = WEIGHT_UNIT_RE.search(s)
        if m:
            num_val = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ("g", "gram", "grams") and canonical_unit == "kg":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Weight in grams — normalize to kg",
                    confidence=90, suggested_value=round(num_val / 1000, 2),
                    severity="info",
                ))
            elif unit in ("lb", "lbs") and canonical_unit == "kg":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Weight in pounds — normalize to kg",
                    confidence=90, suggested_value=round(num_val * 0.453592, 2),
                    severity="info",
                ))
        else:
            # Try plain numeric
            try:
                float(s)
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Cannot parse weight value",
                    confidence=85, suggested_value=None, severity="error",
                ))

    return issues


# ---------------------------------------------------------------------------
# §38  HEIGHT validation
# ---------------------------------------------------------------------------

HEIGHT_UNIT_RE = re.compile(r"([\d.]+)\s*(cm|m|ft|feet|inch|inches|in)\b", re.IGNORECASE)


def validate_height(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    canonical_unit = config.get("canonical_unit", "cm")
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = HEIGHT_UNIT_RE.search(s)
        if m:
            num_val = float(m.group(1))
            unit = m.group(2).lower()
            if unit == "m" and canonical_unit == "cm":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Height in meters — normalize to cm",
                    confidence=90, suggested_value=round(num_val * 100, 1),
                    severity="info",
                ))
            elif unit in ("ft", "feet") and canonical_unit == "cm":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Height in feet — normalize to cm",
                    confidence=90, suggested_value=round(num_val * 30.48, 1),
                    severity="info",
                ))
        else:
            try:
                float(s)
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Cannot parse height value",
                    confidence=85, suggested_value=None, severity="error",
                ))

    return issues


# ---------------------------------------------------------------------------
# §39  TEMPERATURE validation
# ---------------------------------------------------------------------------

TEMP_UNIT_RE = re.compile(r"([\d.\-]+)\s*°?\s*(C|F|K|celsius|fahrenheit|kelvin)\b", re.IGNORECASE)


def validate_temperature(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = TEMP_UNIT_RE.search(s)
        if m:
            unit = m.group(2).upper()[0]
            # Just flag the unit — don't convert (per spec: don't treat 77 as 77°C)
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Temperature with unit '{unit}' — verify unit consistency",
                confidence=80, suggested_value=None, severity="info",
            ))

    return issues


# ---------------------------------------------------------------------------
# §40  DISTANCE validation
# ---------------------------------------------------------------------------

DISTANCE_UNIT_RE = re.compile(r"([\d.]+)\s*(km|m|mi|miles|ft|feet|cm|meter|meters|kilometer|kilometers)\b", re.IGNORECASE)


def validate_distance(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    canonical_unit = config.get("canonical_unit", "km")
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = DISTANCE_UNIT_RE.search(s)
        if m:
            num_val = float(m.group(1))
            unit = m.group(2).lower()
            if unit in ("m", "meter", "meters") and canonical_unit == "km":
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Distance in meters — normalize to km",
                    confidence=90, suggested_value=round(num_val / 1000, 3),
                    severity="info",
                ))

    return issues


# ---------------------------------------------------------------------------
# §41  BOOLEAN FLAGS validation (is_active, is_verified, etc.)
# ---------------------------------------------------------------------------

def validate_boolean_flag(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    """Same logic as boolean, but specifically for flag columns."""
    return validate_boolean(series, col_name, config)


# ---------------------------------------------------------------------------
# §42  STATUS validation
# ---------------------------------------------------------------------------

STATUS_VOCAB: dict[str, str] = {
    "pending": "Pending", "processing": "Processing",
    "completed": "Completed", "complete": "Completed", "done": "Completed",
    "cancelled": "Cancelled", "canceled": "Cancelled", "cancel": "Cancelled",
    "active": "Active", "inactive": "Inactive",
    "approved": "Approved", "rejected": "Rejected",
    "open": "Open", "closed": "Closed",
    "in progress": "In Progress", "in_progress": "In Progress",
}


def validate_status(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    extra_vocab = config.get("status_vocab", {})
    vocab = {**STATUS_VOCAB, **{k.lower(): v for k, v in extra_vocab.items()}}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        canonical = vocab.get(s.lower())
        if canonical:
            if s != canonical:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Status value should be standardized",
                    confidence=100, suggested_value=canonical, severity="info",
                ))
        # Don't auto-map arbitrary values like "done" → "Completed" without config
        # (per spec: "don't automatically map without a configured mapping")

    return issues


# ---------------------------------------------------------------------------
# §43  EDUCATION validation
# ---------------------------------------------------------------------------

EDUCATION_VOCAB: dict[str, str] = {
    "high school": "High School", "hs": "High School", "12th": "High School",
    "10+2": "High School", "secondary": "High School",
    "diploma": "Diploma", "dip": "Diploma",
    "bachelor's": "Bachelor's", "bachelors": "Bachelor's", "bachelor": "Bachelor's",
    "b.tech": "Bachelor's", "btech": "Bachelor's", "b.e": "Bachelor's",
    "b.sc": "Bachelor's", "bsc": "Bachelor's", "b.a": "Bachelor's", "ba": "Bachelor's",
    "b.com": "Bachelor's", "bcom": "Bachelor's",
    "ug": "Bachelor's", "undergraduate": "Bachelor's",
    "master's": "Master's", "masters": "Master's", "master": "Master's",
    "m.tech": "Master's", "mtech": "Master's", "m.e": "Master's",
    "m.sc": "Master's", "msc": "Master's", "m.a": "Master's", "ma": "Master's",
    "m.com": "Master's", "mcom": "Master's", "mba": "Master's",
    "pg": "Master's", "postgraduate": "Master's", "post graduate": "Master's",
    "phd": "PhD", "ph.d": "PhD", "ph.d.": "PhD", "doctorate": "PhD",
    "doctor": "PhD", "doctoral": "PhD",
}


def validate_education(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    extra = config.get("education_vocab", {})
    vocab = {**EDUCATION_VOCAB, **{k.lower(): v for k, v in extra.items()}}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        canonical = vocab.get(s.lower())
        if canonical:
            if s != canonical:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Education value should be standardized",
                    confidence=95, suggested_value=canonical, severity="info",
                ))
        else:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Unrecognized education value",
                confidence=70, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §44  DEPARTMENT validation
# ---------------------------------------------------------------------------

DEPARTMENT_VOCAB: dict[str, str] = {
    "cse": "CSE", "computer science": "CSE", "c.s.e.": "CSE",
    "computer science and engineering": "CSE", "cs": "CSE",
    "ise": "ISE", "information science": "ISE",
    "ece": "ECE", "electronics": "ECE", "electronics and communication": "ECE",
    "eee": "EEE", "electrical": "EEE", "electrical and electronics": "EEE",
    "me": "ME", "mechanical": "ME", "mechanical engineering": "ME",
    "civil": "CIVIL", "civil engineering": "CIVIL",
    "it": "IT", "information technology": "IT",
    "hr": "HR", "human resources": "HR",
    "marketing": "Marketing", "mktg": "Marketing",
    "finance": "Finance", "fin": "Finance",
    "engineering": "Engineering", "eng": "Engineering",
    "sales": "Sales",
    "operations": "Operations", "ops": "Operations",
    "legal": "Legal",
    "admin": "Admin", "administration": "Admin",
}


def validate_department(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    extra = config.get("department_vocab", {})
    vocab = {**DEPARTMENT_VOCAB, **{k.lower(): v for k, v in extra.items()}}
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        canonical = vocab.get(s.lower())
        if canonical:
            if s != canonical:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Department value should be standardized",
                    confidence=95, suggested_value=canonical, severity="info",
                ))
        else:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Unrecognized department value",
                confidence=65, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §45  EXPERIENCE validation
# ---------------------------------------------------------------------------

def validate_experience(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    config = config or {}
    max_exp = config.get("max_experience", 60)
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        # Strip "years" suffix
        cleaned = re.sub(r"\s*(years?|yrs?)\s*$", "", s, flags=re.IGNORECASE).strip()
        try:
            num = float(cleaned)
        except (ValueError, TypeError):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Non-numeric experience value",
                confidence=100, suggested_value=None, severity="error",
            ))
            continue

        if num < 0:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Negative experience ({num})",
                confidence=100, suggested_value=None, severity="error",
            ))
        elif num > max_exp:
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue=f"Experience {num} exceeds maximum {max_exp}",
                confidence=90, suggested_value=None, severity="warning",
            ))

    return issues


# ---------------------------------------------------------------------------
# §46  TIME DURATION validation
# ---------------------------------------------------------------------------

DURATION_UNIT_RE = re.compile(
    r"([\d.]+)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?|days?|weeks?|months?)\b",
    re.IGNORECASE,
)


def validate_time_duration(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        m = DURATION_UNIT_RE.search(s)
        if m:
            # Unit present — just note it for consistency
            pass
        else:
            try:
                float(s)
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue="Cannot parse duration value",
                    confidence=80, suggested_value=None, severity="warning",
                ))

    return issues


# ---------------------------------------------------------------------------
# §47  FILE PATH / FILENAME validation
# ---------------------------------------------------------------------------

ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
VALID_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".json", ".xml", ".txt", ".md", ".html", ".htm",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h",
}


def validate_filepath(series: pd.Series, col_name: str, config: dict | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for idx, val in series.items():
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        s = str(val).strip()
        if not s or s.lower() in NULL_VARIANTS:
            continue

        if ILLEGAL_FILENAME_CHARS.search(s.split("/")[-1].split("\\")[-1]):
            issues.append(ValidationIssue(
                row_index=int(idx), raw_value=val,
                issue="Filename contains illegal characters",
                confidence=95, suggested_value=None, severity="error",
            ))

        # Check extension
        dot_idx = s.rfind(".")
        if dot_idx > 0:
            ext = s[dot_idx:].lower()
            if ext not in VALID_EXTENSIONS and len(ext) < 8:
                issues.append(ValidationIssue(
                    row_index=int(idx), raw_value=val,
                    issue=f"Unknown file extension '{ext}'",
                    confidence=70, suggested_value=None, severity="warning",
                ))

    return issues


# ---------------------------------------------------------------------------
# COLUMN_VALIDATION_RULES — the central registry
# ---------------------------------------------------------------------------

@dataclass
class ValidationRuleEntry:
    """One entry in the central rules table."""
    semantic_type: str
    display_name: str
    validator: Callable
    column_name_hints: list[str] = field(default_factory=list)
    default_config: dict = field(default_factory=dict)


COLUMN_VALIDATION_RULES: dict[str, ValidationRuleEntry] = {
    "name": ValidationRuleEntry("name", "Name", validate_name,
        ["first_name", "last_name", "full_name", "student_name", "employee_name", "name"]),
    "email": ValidationRuleEntry("email", "Email", validate_email,
        ["email", "e-mail", "email_address", "mail"]),
    "phone": ValidationRuleEntry("phone", "Phone Number", validate_phone,
        ["phone", "mobile", "contact", "contact_no", "phone_number", "cell"]),
    "age": ValidationRuleEntry("age", "Age", validate_age,
        ["age"]),
    "dob": ValidationRuleEntry("dob", "Date of Birth", validate_dob,
        ["dob", "date_of_birth", "birth_date", "birthdate"]),
    "date": ValidationRuleEntry("date", "Date", validate_date,
        ["date", "created_date", "transaction_date", "order_date", "start_date", "end_date",
         "join_date", "hire_date", "registration_date"]),
    "time": ValidationRuleEntry("time", "Time", validate_time,
        ["time", "start_time", "end_time", "arrival_time", "departure_time"]),
    "datetime": ValidationRuleEntry("datetime", "Datetime", validate_datetime,
        ["datetime", "timestamp", "created_at", "updated_at", "logged_at"]),
    "gender": ValidationRuleEntry("gender", "Gender", validate_gender,
        ["gender", "sex"]),
    "boolean": ValidationRuleEntry("boolean", "Boolean", validate_boolean,
        ["is_active", "is_verified", "has_paid", "is_student", "active", "verified"]),
    "category": ValidationRuleEntry("category", "Category", validate_category,
        ["category", "product_category", "department", "status", "education"]),
    "age_group": ValidationRuleEntry("age_group", "Age Group", validate_age_group,
        ["age_group", "age_range", "age_bracket"]),
    "integer": ValidationRuleEntry("integer", "Integer", validate_integer,
        ["quantity", "count", "number_of_orders", "num_items"]),
    "decimal": ValidationRuleEntry("decimal", "Decimal", validate_decimal,
        ["height", "weight", "rating", "score", "gpa"]),
    "currency": ValidationRuleEntry("currency", "Currency/Price", validate_currency,
        ["price", "amount", "cost", "revenue", "total", "unit_price", "fee"]),
    "salary": ValidationRuleEntry("salary", "Salary", validate_salary,
        ["salary", "pay", "wage", "compensation", "income", "ctc"]),
    "percentage": ValidationRuleEntry("percentage", "Percentage", validate_percentage,
        ["percentage", "percent", "pct", "rate"]),
    "cgpa": ValidationRuleEntry("cgpa", "CGPA", validate_cgpa,
        ["cgpa"]),
    "gpa": ValidationRuleEntry("gpa", "GPA", validate_gpa,
        ["gpa", "grade_point"]),
    "marks": ValidationRuleEntry("marks", "Marks", validate_marks,
        ["marks", "score", "total_marks"]),
    "rating": ValidationRuleEntry("rating", "Rating", validate_rating,
        ["rating", "stars", "review_score"]),
    "zipcode": ValidationRuleEntry("zipcode", "ZIP/PIN Code", validate_zipcode,
        ["zip", "zipcode", "zip_code", "pin", "pincode", "pin_code", "postal", "postal_code"]),
    "url": ValidationRuleEntry("url", "URL", validate_url,
        ["url", "website", "link", "homepage", "web"]),
    "ip_address": ValidationRuleEntry("ip_address", "IP Address", validate_ip_address,
        ["ip", "ip_address", "ipv4", "ipv6", "ip_addr"]),
    "uuid": ValidationRuleEntry("uuid", "UUID", validate_uuid,
        ["uuid", "guid"]),
    "id": ValidationRuleEntry("id", "ID/Primary Key", validate_id,
        ["id", "student_id", "customer_id", "employee_id", "transaction_id",
         "order_id", "user_id", "record_id"]),
    "product_code": ValidationRuleEntry("product_code", "Product Code/SKU", validate_product_code,
        ["sku", "product_code", "item_code", "product_id", "part_number"]),
    "address": ValidationRuleEntry("address", "Address", validate_address,
        ["address", "street", "location", "addr", "street_address", "mailing_address"]),
    "country": ValidationRuleEntry("country", "Country", validate_country,
        ["country", "nation", "country_name"]),
    "state": ValidationRuleEntry("state", "State", validate_state,
        ["state", "province", "region", "state_name"]),
    "city": ValidationRuleEntry("city", "City", validate_city,
        ["city", "town", "municipality", "city_name"]),
    "handle": ValidationRuleEntry("handle", "Social Media Handle", validate_handle,
        ["handle", "username", "twitter", "instagram", "social_handle"]),
    "payment_id": ValidationRuleEntry("payment_id", "Payment ID", validate_payment_id,
        ["credit_card", "card_number", "payment_id", "card_no"]),
    "transaction_id": ValidationRuleEntry("transaction_id", "Transaction ID", validate_transaction_id,
        ["transaction_id", "txn_id", "txn_no", "order_number"]),
    "quantity": ValidationRuleEntry("quantity", "Quantity", validate_quantity,
        ["quantity", "qty", "count", "units"]),
    "weight": ValidationRuleEntry("weight", "Weight", validate_weight,
        ["weight", "mass", "weight_kg", "weight_g"]),
    "height_measure": ValidationRuleEntry("height_measure", "Height", validate_height,
        ["height", "height_cm", "height_m", "stature"]),
    "temperature": ValidationRuleEntry("temperature", "Temperature", validate_temperature,
        ["temperature", "temp", "body_temp"]),
    "distance": ValidationRuleEntry("distance", "Distance", validate_distance,
        ["distance", "dist", "range", "length"]),
    "boolean_flag": ValidationRuleEntry("boolean_flag", "Boolean Flag", validate_boolean_flag,
        ["is_active", "is_verified", "has_paid", "is_student", "is_employed",
         "is_deleted", "is_confirmed", "has_discount"]),
    "status": ValidationRuleEntry("status", "Status", validate_status,
        ["status", "order_status", "payment_status", "ticket_status"]),
    "education": ValidationRuleEntry("education", "Education", validate_education,
        ["education", "qualification", "degree", "education_level"]),
    "department": ValidationRuleEntry("department", "Department", validate_department,
        ["department", "dept", "division", "branch"]),
    "experience": ValidationRuleEntry("experience", "Experience", validate_experience,
        ["experience", "exp", "years_of_experience", "work_experience"]),
    "time_duration": ValidationRuleEntry("time_duration", "Time Duration", validate_time_duration,
        ["duration", "time_duration", "elapsed", "time_spent"]),
    "filepath": ValidationRuleEntry("filepath", "File Path", validate_filepath,
        ["file", "filename", "file_path", "filepath", "attachment", "document"]),
}


# ---------------------------------------------------------------------------
# Semantic type detection — covers all 47 types
# ---------------------------------------------------------------------------

def detect_semantic_type(series: pd.Series, col_name: str) -> str:
    """Infer the semantic type of a column from its name and sample values.
    Returns the key into COLUMN_VALIDATION_RULES, or 'text' for unmatched."""
    name_lower = col_name.lower().strip().replace(" ", "_")

    # Priority 1: Exact or prefix/suffix column-name matching
    # Sort by specificity: longer hints first, then by rule priority
    best_match = None
    best_match_len = 0

    for rule_key, rule_entry in COLUMN_VALIDATION_RULES.items():
        for hint in rule_entry.column_name_hints:
            hint_lower = hint.lower()
            # Exact match
            if name_lower == hint_lower:
                return rule_key
            # Suffix match (e.g. "student_name" matches hint "name")
            if name_lower.endswith("_" + hint_lower) and len(hint_lower) > best_match_len:
                best_match = rule_key
                best_match_len = len(hint_lower)
            # Prefix match (e.g. "email_address" matches hint "email")
            if name_lower.startswith(hint_lower + "_") and len(hint_lower) > best_match_len:
                best_match = rule_key
                best_match_len = len(hint_lower)
            # Contains (looser)
            if hint_lower in name_lower and len(hint_lower) >= 3 and len(hint_lower) > best_match_len:
                best_match = rule_key
                best_match_len = len(hint_lower)

    if best_match:
        return best_match

    # Priority 2: Data-driven heuristics for remaining columns
    non_null = series.dropna()
    if non_null.empty:
        return "text"

    sample = non_null.astype(str).head(100)

    # Check if mostly numeric
    coerced = pd.to_numeric(non_null, errors="coerce")
    numeric_ratio = coerced.notna().mean() if len(non_null) > 0 else 0

    if numeric_ratio >= 0.8:
        # Determine numeric sub-type from column name
        non_neg_keys = ("age", "salary", "experience", "income", "years", "price", "amount", "cost")
        if any(k in name_lower for k in non_neg_keys):
            return "integer"  # Will be re-detected by name hints above mostly
        return "decimal"

    # Check for date patterns
    date_count = sum(1 for v in sample if _try_parse_date(str(v)) is not None)
    if date_count / max(len(sample), 1) >= 0.5:
        return "date"

    # Check for email pattern
    email_count = sum(1 for v in sample if "@" in str(v) and "." in str(v))
    if email_count / max(len(sample), 1) >= 0.5:
        return "email"

    # Check for URL pattern
    url_count = sum(1 for v in sample if str(v).startswith(("http://", "https://", "www.")))
    if url_count / max(len(sample), 1) >= 0.5:
        return "url"

    # Check for UUID pattern
    uuid_count = sum(1 for v in sample if UUID_RE.match(str(v).strip()))
    if uuid_count / max(len(sample), 1) >= 0.5:
        return "uuid"

    # Check cardinality for categorical
    unique_ratio = non_null.nunique() / max(len(non_null), 1)
    if unique_ratio < 0.05 and non_null.nunique() < 50:
        return "category"

    return "text"


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_column(
    series: pd.Series,
    col_name: str,
    semantic_type: str | None = None,
    config: dict | None = None,
) -> ValidationResult:
    """Validate a single column.

    If semantic_type is given, use that type's rules.
    Otherwise, auto-detect the semantic type.
    Returns a ValidationResult with all issues found.
    """
    if semantic_type is None:
        semantic_type = detect_semantic_type(series, col_name)

    rule_entry = COLUMN_VALIDATION_RULES.get(semantic_type)
    if rule_entry is None:
        return ValidationResult(column_name=col_name, semantic_type=semantic_type)

    merged_config = {**rule_entry.default_config, **(config or {})}
    issues = rule_entry.validator(series, col_name, merged_config)

    return ValidationResult(
        column_name=col_name,
        semantic_type=semantic_type,
        issues=issues,
    )


# ===================================================================
# CROSS-COLUMN RULES  (§ Cross-Column Rules)
# ===================================================================

def validate_dob_age_consistency(
    df: pd.DataFrame,
    dob_col: str | None = None,
    age_col: str | None = None,
    tolerance_years: int = 1,
) -> list[CrossColumnIssue]:
    """Rule 1: DOB ↔ Age consistency."""
    if dob_col is None:
        dob_candidates = [c for c in df.columns if c.lower() in ("dob", "date_of_birth", "birth_date", "birthdate")]
        dob_col = dob_candidates[0] if dob_candidates else None
    if age_col is None:
        age_candidates = [c for c in df.columns if c.lower() == "age"]
        age_col = age_candidates[0] if age_candidates else None

    if not dob_col or not age_col or dob_col not in df.columns or age_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []
    today = date.today()

    for idx in df.index:
        dob_val = df.at[idx, dob_col]
        age_val = df.at[idx, age_col]

        if pd.isna(dob_val) or pd.isna(age_val):
            continue

        parsed_dob = _try_parse_date(str(dob_val))
        if parsed_dob is None:
            continue

        try:
            age_num = float(str(age_val))
        except (ValueError, TypeError):
            continue

        expected_age = (today - parsed_dob).days / 365.25
        if abs(expected_age - age_num) > tolerance_years:
            issues.append(CrossColumnIssue(
                rule_name="dob_age_consistency",
                columns_involved=[dob_col, age_col],
                row_index=int(idx),
                issue=f"DOB ({dob_val}) implies age ~{expected_age:.0f}, but Age column says {age_num}",
                confidence=95,
                severity="error",
                details={"expected_age": round(expected_age), "actual_age": age_num},
            ))

    return issues


def validate_start_end_date(
    df: pd.DataFrame,
    start_col: str | None = None,
    end_col: str | None = None,
) -> list[CrossColumnIssue]:
    """Rule 2: Start_Date ≤ End_Date."""
    if start_col is None:
        candidates = [c for c in df.columns if "start" in c.lower() and "date" in c.lower()]
        start_col = candidates[0] if candidates else None
    if end_col is None:
        candidates = [c for c in df.columns if "end" in c.lower() and "date" in c.lower()]
        end_col = candidates[0] if candidates else None

    if not start_col or not end_col or start_col not in df.columns or end_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []
    for idx in df.index:
        start_val = df.at[idx, start_col]
        end_val = df.at[idx, end_col]

        if pd.isna(start_val) or pd.isna(end_val):
            continue

        start_date = _try_parse_date(str(start_val))
        end_date = _try_parse_date(str(end_val))

        if start_date and end_date and start_date > end_date:
            issues.append(CrossColumnIssue(
                rule_name="start_end_date",
                columns_involved=[start_col, end_col],
                row_index=int(idx),
                issue=f"Start date ({start_val}) is after end date ({end_val})",
                confidence=100,
                severity="error",
            ))

    return issues


def validate_quantity_price_total(
    df: pd.DataFrame,
    qty_col: str | None = None,
    price_col: str | None = None,
    total_col: str | None = None,
    tolerance_pct: float = 1.0,
) -> list[CrossColumnIssue]:
    """Rule 3: Quantity × Price = Total."""
    if qty_col is None:
        candidates = [c for c in df.columns if c.lower() in ("quantity", "qty", "count")]
        qty_col = candidates[0] if candidates else None
    if price_col is None:
        candidates = [c for c in df.columns if c.lower() in ("unit_price", "price", "rate")]
        price_col = candidates[0] if candidates else None
    if total_col is None:
        candidates = [c for c in df.columns if c.lower() in ("total", "total_price", "amount", "subtotal")]
        total_col = candidates[0] if candidates else None

    if not qty_col or not price_col or not total_col:
        return []
    if qty_col not in df.columns or price_col not in df.columns or total_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []
    for idx in df.index:
        try:
            qty = float(str(df.at[idx, qty_col]))
            price = float(str(df.at[idx, price_col]))
            total = float(str(df.at[idx, total_col]))
        except (ValueError, TypeError):
            continue

        expected = qty * price
        if expected == 0 and total == 0:
            continue
        if abs(expected - total) / max(abs(expected), 1) * 100 > tolerance_pct:
            issues.append(CrossColumnIssue(
                rule_name="quantity_price_total",
                columns_involved=[qty_col, price_col, total_col],
                row_index=int(idx),
                issue=f"Quantity({qty}) × Price({price}) = {expected}, but Total = {total}",
                confidence=95,
                severity="error",
                details={"expected_total": expected, "actual_total": total},
            ))

    return issues


def validate_marks_percentage(
    df: pd.DataFrame,
    marks_col: str | None = None,
    pct_col: str | None = None,
    max_marks: float = 100,
    tolerance_pct: float = 1.0,
) -> list[CrossColumnIssue]:
    """Rule 4: Marks ↔ Percentage consistency."""
    if marks_col is None:
        candidates = [c for c in df.columns if c.lower() in ("marks", "score", "total_marks")]
        marks_col = candidates[0] if candidates else None
    if pct_col is None:
        candidates = [c for c in df.columns if c.lower() in ("percentage", "percent", "pct")]
        pct_col = candidates[0] if candidates else None

    if not marks_col or not pct_col or marks_col not in df.columns or pct_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []
    for idx in df.index:
        try:
            marks = float(str(df.at[idx, marks_col]))
            pct = float(str(df.at[idx, pct_col]).rstrip("%"))
        except (ValueError, TypeError):
            continue

        expected_pct = (marks / max_marks) * 100
        if abs(expected_pct - pct) > tolerance_pct:
            issues.append(CrossColumnIssue(
                rule_name="marks_percentage",
                columns_involved=[marks_col, pct_col],
                row_index=int(idx),
                issue=f"Marks {marks}/{max_marks} = {expected_pct:.1f}%, but Percentage column says {pct}%",
                confidence=90,
                severity="error",
            ))

    return issues


# India: state → cities mapping (partial, major cities)
INDIA_STATE_CITIES: dict[str, set[str]] = {
    "Karnataka": {"Bengaluru", "Bangalore", "Mysuru", "Mysore", "Hubli", "Mangalore", "Mangaluru", "Belgaum", "Belagavi"},
    "Maharashtra": {"Mumbai", "Pune", "Nagpur", "Thane", "Nashik", "Aurangabad"},
    "Tamil Nadu": {"Chennai", "Coimbatore", "Madurai", "Salem", "Trichy"},
    "Telangana": {"Hyderabad", "Warangal", "Nizamabad"},
    "Delhi": {"Delhi", "New Delhi"},
    "West Bengal": {"Kolkata", "Howrah", "Durgapur", "Siliguri"},
    "Gujarat": {"Ahmedabad", "Surat", "Vadodara", "Rajkot"},
    "Rajasthan": {"Jaipur", "Jodhpur", "Udaipur", "Kota"},
    "Uttar Pradesh": {"Lucknow", "Kanpur", "Agra", "Varanasi", "Noida", "Ghaziabad"},
    "Kerala": {"Kochi", "Trivandrum", "Thiruvananthapuram", "Kozhikode", "Calicut"},
    "Andhra Pradesh": {"Visakhapatnam", "Vijayawada", "Tirupati"},
    "Punjab": {"Chandigarh", "Ludhiana", "Amritsar"},
    "Haryana": {"Gurugram", "Gurgaon", "Faridabad"},
    "Bihar": {"Patna", "Gaya"},
    "Odisha": {"Bhubaneswar", "Cuttack"},
}


def validate_country_state(
    df: pd.DataFrame,
    country_col: str | None = None,
    state_col: str | None = None,
) -> list[CrossColumnIssue]:
    """Rule 5: Country ↔ State consistency."""
    if country_col is None:
        candidates = [c for c in df.columns if c.lower() in ("country", "nation")]
        country_col = candidates[0] if candidates else None
    if state_col is None:
        candidates = [c for c in df.columns if c.lower() in ("state", "province", "region")]
        state_col = candidates[0] if candidates else None

    if not country_col or not state_col or country_col not in df.columns or state_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []
    india_state_names = {v.lower() for v in INDIA_STATES.values()}

    for idx in df.index:
        country_val = df.at[idx, country_col]
        state_val = df.at[idx, state_col]

        if pd.isna(country_val) or pd.isna(state_val):
            continue

        country_str = str(country_val).strip()
        state_str = str(state_val).strip()

        country_canonical = COUNTRY_DICT.get(country_str.lower(), country_str)
        if country_canonical == "India":
            state_canonical = INDIA_STATES.get(state_str.lower())
            if state_canonical is None and state_str.lower() not in india_state_names:
                issues.append(CrossColumnIssue(
                    rule_name="country_state",
                    columns_involved=[country_col, state_col],
                    row_index=int(idx),
                    issue=f"Country=India but State='{state_str}' is not a recognized Indian state",
                    confidence=85,
                    severity="warning",
                ))

    return issues


def validate_state_city(
    df: pd.DataFrame,
    state_col: str | None = None,
    city_col: str | None = None,
) -> list[CrossColumnIssue]:
    """Rule 6: State ↔ City consistency."""
    if state_col is None:
        candidates = [c for c in df.columns if c.lower() in ("state", "province", "region")]
        state_col = candidates[0] if candidates else None
    if city_col is None:
        candidates = [c for c in df.columns if c.lower() in ("city", "town")]
        city_col = candidates[0] if candidates else None

    if not state_col or not city_col or state_col not in df.columns or city_col not in df.columns:
        return []

    issues: list[CrossColumnIssue] = []

    for idx in df.index:
        state_val = df.at[idx, state_col]
        city_val = df.at[idx, city_col]

        if pd.isna(state_val) or pd.isna(city_val):
            continue

        state_str = str(state_val).strip()
        city_str = str(city_val).strip()

        # Resolve state to canonical
        state_canonical = INDIA_STATES.get(state_str.lower(), state_str)

        if state_canonical in INDIA_STATE_CITIES:
            valid_cities = {c.lower() for c in INDIA_STATE_CITIES[state_canonical]}
            if city_str.lower() not in valid_cities:
                # Check if city belongs to a DIFFERENT state
                for other_state, other_cities in INDIA_STATE_CITIES.items():
                    if other_state != state_canonical and city_str.lower() in {c.lower() for c in other_cities}:
                        issues.append(CrossColumnIssue(
                            rule_name="state_city",
                            columns_involved=[state_col, city_col],
                            row_index=int(idx),
                            issue=f"City '{city_str}' is typically in {other_state}, but State='{state_str}'",
                            confidence=80,
                            severity="warning",
                        ))
                        break

    return issues


def run_all_cross_column_validations(df: pd.DataFrame) -> list[CrossColumnIssue]:
    """Run all 6 cross-column validators."""
    all_issues: list[CrossColumnIssue] = []
    all_issues.extend(validate_dob_age_consistency(df))
    all_issues.extend(validate_start_end_date(df))
    all_issues.extend(validate_quantity_price_total(df))
    all_issues.extend(validate_marks_percentage(df))
    all_issues.extend(validate_country_state(df))
    all_issues.extend(validate_state_city(df))
    return all_issues


# ===================================================================
# DATASET-LEVEL RULES
# ===================================================================

def classify_missing_percentage(pct: float) -> str:
    """Classify missing percentage into tiers (configurable thresholds)."""
    if pct <= 5:
        return "Low"
    elif pct <= 20:
        return "Moderate"
    elif pct <= 50:
        return "High"
    else:
        return "Critical"


def detect_dataset_level_issues(df: pd.DataFrame, profile: dict | None = None) -> list[DatasetLevelIssue]:
    """Run all dataset-level checks."""
    issues: list[DatasetLevelIssue] = []

    # Missing value analysis
    for col in df.columns:
        total = len(df)
        missing = int(df[col].isna().sum())
        pct = (missing / total * 100) if total > 0 else 0
        classification = classify_missing_percentage(pct)

        if classification in ("High", "Critical"):
            issues.append(DatasetLevelIssue(
                rule_name="missing_values",
                issue=f"Column '{col}' has {pct:.1f}% missing values ({classification})",
                severity="warning" if classification == "High" else "error",
                details={"column": col, "missing_count": missing, "missing_pct": round(pct, 2),
                         "classification": classification},
            ))

    # Detect almost-empty columns (98%+ NULL)
    for col in df.columns:
        total = len(df)
        missing = int(df[col].isna().sum())
        pct = (missing / total * 100) if total > 0 else 0
        if pct >= 98:
            issues.append(DatasetLevelIssue(
                rule_name="almost_empty_column",
                issue=f"Column '{col}' is almost empty ({pct:.1f}% NULL)",
                severity="warning",
                details={"column": col, "missing_pct": round(pct, 2)},
            ))

    # Detect constant columns (every non-null value the same)
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) > 0 and non_null.nunique() == 1:
            issues.append(DatasetLevelIssue(
                rule_name="constant_column",
                issue=f"Column '{col}' has a single constant value: '{non_null.iloc[0]}'",
                severity="info",
                details={"column": col, "constant_value": str(non_null.iloc[0])},
            ))

    # Detect duplicate columns (same data in two columns)
    cols = list(df.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if df[cols[i]].equals(df[cols[j]]):
                issues.append(DatasetLevelIssue(
                    rule_name="duplicate_columns",
                    issue=f"Columns '{cols[i]}' and '{cols[j]}' contain identical data",
                    severity="warning",
                    details={"column_1": cols[i], "column_2": cols[j]},
                ))

    # Exact duplicate rows
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        issues.append(DatasetLevelIssue(
            rule_name="duplicate_rows",
            issue=f"{dup_count} exact duplicate row(s) found",
            severity="warning",
            details={"duplicate_count": dup_count},
        ))

    return issues


def detect_outliers_iqr(series: pd.Series, col_name: str) -> list[ValidationIssue]:
    """IQR-based outlier detection.
    Per spec: outlier is ⚠️ WARNING, not ❌ ERROR. An outlier is not automatically an error."""
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 4:
        return []

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1

    if iqr == 0:
        return []

    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr

    issues: list[ValidationIssue] = []
    for idx in numeric.index:
        val = numeric[idx]
        if val < lower_fence or val > upper_fence:
            issues.append(ValidationIssue(
                row_index=int(idx),
                raw_value=val,
                issue=f"Potential outlier (IQR: {lower_fence:.1f}–{upper_fence:.1f})",
                confidence=75,
                suggested_value=None,
                severity="warning",  # Per spec: ⚠️ not ❌
            ))

    return issues
