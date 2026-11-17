"""
Cleaning rules engine.

Provides automated, rule-based suggestions based on profiling reports,
and executes pipeline steps sequentially on a pandas DataFrame.
"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import datetime
from typing import Any

import pandas as pd


OPPOSITES: set[tuple[str, str]] = {
    ("male", "female"), ("female", "male"),
    ("active", "inactive"), ("inactive", "active"),
    ("yes", "no"), ("no", "yes"),
    ("true", "false"), ("false", "true"),
    ("pass", "fail"), ("fail", "pass"),
    ("open", "closed"), ("closed", "open"),
    ("in", "out"), ("out", "in"),
    ("on", "off"), ("off", "on"),
    ("high", "low"), ("low", "high"),
    ("good", "bad"), ("bad", "good"),
    ("m", "f"), ("f", "m"),
}

# ---------------------------------------------------------------------------
# COLUMN_TYPE_RULES — delegates to centralised validation_rules.py
# ---------------------------------------------------------------------------
# The canonical validation logic lives in validation_rules.py.
# This adapter converts ValidationIssue objects to the legacy dict format
# that the existing UI / pipeline expects (row_index, raw_value,
# suggested_value, reason).

from app.validation_rules import (
    COLUMN_VALIDATION_RULES,
    DOMAIN_RULES,
    UNITS_DICT,
    TENS_DICT,
    SCALES_DICT,
    words_to_number,
    validate_column,
    detect_semantic_type,
    validate_email as _vr_validate_email,
    validate_phone as _vr_validate_phone,
    validate_name as _vr_validate_name,
    validate_age as _vr_validate_age,
    validate_gender as _vr_validate_gender,
    validate_boolean as _vr_validate_boolean,
    validate_currency as _vr_validate_currency,
    validate_salary as _vr_validate_salary,
    validate_percentage as _vr_validate_percentage,
    validate_zipcode as _vr_validate_zipcode,
    validate_id as _vr_validate_id,
    validate_date as _vr_validate_date,
    validate_latitude as _vr_validate_latitude,
    validate_longitude as _vr_validate_longitude,
    validate_quantity as _vr_validate_quantity,
    detect_outliers_iqr,
    detect_dataset_level_issues,
    run_all_cross_column_validations,
)


def _adapt_validation_issues(issues_list) -> list[dict]:
    """Convert ValidationIssue objects to legacy flagged_values dict format."""
    return [
        {
            "row_index": i.row_index,
            "raw_value": i.raw_value,
            "suggested_value": i.suggested_value,
            "reason": i.issue,
            "confidence": i.confidence,
            "severity": i.severity,
        }
        for i in issues_list
    ]


def _make_type_adapter(validator_fn):
    """Create a COLUMN_TYPE_RULES-compatible adapter for a validation_rules validator."""
    def adapter(series: pd.Series, column_name: str) -> list[dict]:
        issues = validator_fn(series, column_name)
        return _adapt_validation_issues(issues)
    return adapter


# Registry: maps inferred_type / semantic_type → validation function.
# Each function signature: (series: pd.Series, column_name: str) -> list[dict]
# Delegates to the canonical validators in validation_rules.py.
COLUMN_TYPE_RULES: dict[str, callable] = {
    "phone": _make_type_adapter(_vr_validate_phone),
    "email": _make_type_adapter(_vr_validate_email),
    "name": _make_type_adapter(_vr_validate_name),
    "age": _make_type_adapter(_vr_validate_age),
    "gender": _make_type_adapter(_vr_validate_gender),
    "boolean": _make_type_adapter(_vr_validate_boolean),
    "currency": _make_type_adapter(_vr_validate_currency),
    "salary": _make_type_adapter(_vr_validate_salary),
    "percentage": _make_type_adapter(_vr_validate_percentage),
    "zipcode": _make_type_adapter(_vr_validate_zipcode),
    "id": _make_type_adapter(_vr_validate_id),
    "date": _make_type_adapter(_vr_validate_date),
    "latitude": _make_type_adapter(_vr_validate_latitude),
    "longitude": _make_type_adapter(_vr_validate_longitude),
    "quantity": _make_type_adapter(_vr_validate_quantity),
}

MISSING_TOKENS: set[str] = {
    "", "na", "n/a", "n.a.", "null", "none", "nan", "-", "?", "unknown", "not available", "n/d", "nil"
}


def normalize_whitespace_string(s: str) -> str:
    """Strip NBSP, zero-width chars, leading/trailing whitespace, and collapse inner space runs."""
    if not isinstance(s, str):
        s = str(s)
    s = re.sub(r"[\u00a0\u200b\ufeff\u200e\u200f]", "", s)
    s = re.sub(r"[ \t\r\n]+", " ", s)
    return s.strip()


def clean_numeric_value(val: Any) -> Any:
    """Normalize numeric values by stripping currency symbols, commas, and whitespace, parsing number words."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return val
    s = normalize_whitespace_string(str(val))
    if not s or s.lower() in MISSING_TOKENS:
        return None

    # Check for English number words (e.g. Twenty -> 20, Ten -> 10)
    word_num = words_to_number(s)
    if word_num is not None:
        return word_num

    # Check for negative format: leading minus, negative sign, or parentheses e.g. (1,000)
    is_neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-") or ("-" in s and not re.search(r"\d-\d", s)):
        is_neg = True

    # Strip currency words and symbols
    s_clean = re.sub(r"(?i)\b(rs|inr|usd|eur|gbp)\.?\s*", "", s)
    s_clean = re.sub(r"[$€£₹¥%]", "", s_clean).strip()

    cleaned = re.sub(r"[^\d.]", "", s_clean)
    if not cleaned or cleaned == ".":
        return None
    try:
        num = float(cleaned) if "." in cleaned else int(cleaned)
        return -num if is_neg else num
    except (ValueError, TypeError):
        return cleaned


DEFAULT_PHONE_COUNTRY: str = "IN"

KNOWN_DOMAIN_TYPOS: dict[str, str] = {
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com",
}

EMAIL_RFC_REGEX = re.compile(r"^[a-zA-Z0-9_.+'\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}$")

EXPLICIT_DATE_FORMATS: list[str] = [
    "%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y",
    "%d %B %Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"
]

DMY_DATE_FORMATS: list[str] = ["%d/%m/%Y", "%d-%m-%Y"]
MDY_DATE_FORMATS: list[str] = ["%m/%d/%Y", "%m-%d-%Y"]
_SLASH_OR_DASH_DMY_RE = re.compile(r"^(\d{1,2})([/-])(\d{1,2})\2(\d{4})$")


def analyze_column_date_order(series: pd.Series) -> str:
    """Detect whether dd/mm vs mm/dd dates in a column can be disambiguated.
    If any value has first part > 12 (and second <= 12) -> 'DMY'.
    If any value has second part > 12 (and first <= 12) -> 'MDY'.
    If ambiguous dd/mm vs mm/dd values exist with neither > 12 -> 'AMBIGUOUS'.
    Otherwise -> 'UNAMBIGUOUS'.
    """
    has_first_gt_12 = False
    has_second_gt_12 = False
    has_ambig_candidate = False
    for val in series.dropna():
        s = normalize_whitespace_string(str(val))
        m = _SLASH_OR_DASH_DMY_RE.match(s)
        if not m:
            continue
        p1, p2 = int(m.group(1)), int(m.group(3))
        if p1 > 12 and p2 <= 12:
            has_first_gt_12 = True
        elif p2 > 12 and p1 <= 12:
            has_second_gt_12 = True
        elif 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
            has_ambig_candidate = True

    if has_first_gt_12 and not has_second_gt_12:
        return "DMY"
    if has_second_gt_12 and not has_first_gt_12:
        return "MDY"
    if has_ambig_candidate:
        return "AMBIGUOUS"
    return "DMY"


def clean_name_value(val: Any) -> tuple[str, bool]:
    """Clean a customer name: strip whitespace/NBSP, remove digits and symbols except ' - . and space.
    Change case ONLY if the whole value is all-lowercase or all-uppercase (-> Title Case).
    Preserve mixed-case (McDonald, O'Brien, De Silva).
    """
    if val is None or pd.isna(val):
        return "", False
    s = normalize_whitespace_string(val)
    if not s or s.lower() in MISSING_TOKENS:
        return "", False
    s_cleaned = re.sub(r"[^a-zA-Z\s.'\-]", "", s)
    s_cleaned = re.sub(r"\s+", " ", s_cleaned).strip()
    if not s_cleaned:
        return "", True
    if s_cleaned.islower() or s_cleaned.isupper():
        s_cased = s_cleaned.title()
    else:
        s_cased = s_cleaned
    return s_cased, (s_cased != str(val))


def clean_email_value(val: Any) -> tuple[str | None, str, bool]:
    """Clean email value: trim, lowercase, remove inner spaces, collapse repeated @.
    Fix known domain typos & tld typos (.con -> .com, .cmo -> .com).
    Returns (cleaned_val_or_None, status: 'valid'|'invalid'|'missing', changed: bool).
    """
    if val is None or pd.isna(val):
        return None, "missing", False
    s = normalize_whitespace_string(str(val)).lower()
    if not s or s in MISSING_TOKENS:
        return None, "missing", False
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"@+", "@", s)
    if "@" not in s:
        return None, "invalid", True
    parts = s.split("@", 1)
    local_part, domain_part = parts[0], parts[1]
    if domain_part in KNOWN_DOMAIN_TYPOS:
        domain_part = KNOWN_DOMAIN_TYPOS[domain_part]
    elif domain_part.endswith(".con"):
        domain_part = domain_part[:-4] + ".com"
    elif domain_part.endswith(".cmo"):
        domain_part = domain_part[:-4] + ".com"
    candidate = f"{local_part}@{domain_part}"
    if not EMAIL_RFC_REGEX.match(candidate):
        return None, "invalid", True
    return candidate, "valid", (candidate != str(val))


def clean_phone_value(val: Any, default_country: str = DEFAULT_PHONE_COUNTRY) -> tuple[str | None, str, bool]:
    """Clean phone value: strip non-digits, drop 91/0 for IN, require 10 digits starting 6-9.
    Returns (cleaned_phone_or_None, status: 'valid'|'invalid'|'missing', changed: bool).
    """
    if val is None or pd.isna(val):
        return None, "missing", False
    s = normalize_whitespace_string(str(val))
    if s.endswith(".0"):
        s = s[:-2]
    if not s or s.lower() in MISSING_TOKENS:
        return None, "missing", False
    # If alphabetic characters exist, invalid
    if re.search(r"[a-zA-Z]", s):
        return None, "invalid", True
    digits = re.sub(r"\D", "", s)
    if default_country == "IN":
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in ("6", "7", "8", "9"):
            return digits, "valid", (digits != str(val))
        return None, "invalid", True
    if 7 <= len(digits) <= 15:
        return digits, "valid", (digits != str(val))
    return None, "invalid", True


def parse_explicit_date(val: Any, date_order: str = "DMY") -> tuple[str | None, str, bool]:
    """Parse date with explicit format list, detect ambiguous/impossible dates and year bounds.
    Returns (formatted_or_None, status: 'valid'|'invalid'|'missing'|'ambiguous'|'suspect', changed: bool).
    """
    if val is None or pd.isna(val):
        return None, "missing", False
    s = normalize_whitespace_string(str(val))
    if not s:
        return None, "missing", False
    if s.lower() in ("not available", "unknown", "tbd", "tba", "invalid"):
        return None, "invalid", True
    if s.lower() in MISSING_TOKENS:
        return None, "missing", False

    parsed_dt = None
    m = _SLASH_OR_DASH_DMY_RE.match(s)
    if m:
        p1, p2 = int(m.group(1)), int(m.group(3))
        if date_order == "AMBIGUOUS" and 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
            return str(val), "ambiguous", False
        fmts_to_try = DMY_DATE_FORMATS if date_order != "MDY" else MDY_DATE_FORMATS
        for fmt in fmts_to_try:
            try:
                parsed_dt = datetime.strptime(s, fmt)
                break
            except (ValueError, TypeError):
                continue
    else:
        for fmt in EXPLICIT_DATE_FORMATS:
            try:
                parsed_dt = datetime.strptime(s, fmt)
                break
            except (ValueError, TypeError):
                continue

    if parsed_dt is None:
        return None, "invalid", True

    current_year = datetime.now().year
    if parsed_dt.year < 1900 or parsed_dt.year > current_year + 5:
        out_str = parsed_dt.strftime("%Y-%m-%d")
        return out_str, "suspect", (out_str != str(val))

    out_str = parsed_dt.strftime("%Y-%m-%d")
    return out_str, "valid", (out_str != str(val))


CATEGORY_ALIASES: dict[str, str] = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "gurgaon": "gurugram",
    "mysore": "mysuru",
    "cochin": "kochi",
    "trivandrum": "thiruvananthapuram",
    "poona": "pune",
    "baroda": "vadodara",
    "benares": "varanasi",
    "banaras": "varanasi",
    "mangalore": "mangaluru",
    "hubli": "hubballi",
    "belgaum": "belagavi",
    "cawnpore": "kanpur",
    "alleppey": "alappuzha",
    "pondicherry": "puducherry",
    "orissa": "odisha",
    "uttaranchal": "uttarakhand",
}

_ANTONYM_PREFIXES: tuple[str, ...] = (
    "in", "un", "im", "il", "ir", "non", "dis", "de", "anti",
)


def is_antonym_or_prefix_pair(a: str, b: str) -> bool:
    """Return True if two strings are known opposites or negative-prefix pairs (e.g. Active/Inactive)."""
    la = re.sub(r"[^a-z0-9]", "", str(a).strip().lower())
    lb = re.sub(r"[^a-z0-9]", "", str(b).strip().lower())
    if not la or not lb or la == lb:
        return False
    if (la, lb) in OPPOSITES or (lb, la) in OPPOSITES:
        return True
    for pfx in _ANTONYM_PREFIXES:
        if (la == pfx + lb and len(lb) >= 3) or (lb == pfx + la and len(la) >= 3):
            return True
    return False


def _levenshtein_distance(a: str, b: str) -> int:
    """Exact Levenshtein edit distance (stdlib only, no extra deps)."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _token_sort_ratio(a: str, b: str) -> float:
    """Token-sorted similarity ratio in 0..100."""
    ta = " ".join(sorted(re.findall(r"[a-z0-9]+", str(a).lower())))
    tb = " ".join(sorted(re.findall(r"[a-z0-9]+", str(b).lower())))
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb).ratio() * 100.0


def _normalize_cat_key(s: str) -> str:
    """Lowercase and strip all punctuation and spaces."""
    return re.sub(r"[^a-z0-9]", "", normalize_whitespace_string(str(s)).lower())


def _singularize_key(k: str) -> str:
    """Light singular/plural folding ('groceries' -> 'grocery', 'electronics' stays 'electronic' if paired)."""
    if len(k) > 4 and k.endswith("ies"):
        return k[:-3] + "y"
    if len(k) > 4 and k.endswith(("ses", "xes", "zes", "ches", "shes")):
        return k[:-2]
    if len(k) > 3 and k.endswith("s") and not k.endswith("ss"):
        return k[:-1]
    return k


def cluster_categorical_column(
    series: pd.Series, max_distinct: int = 60
) -> dict[str, Any]:
    """Deterministic 3-stage categorical clustering (rules first):
      1. Normalized key (lowercase, strip punct/spaces) + light singular/plural folding.
      2. Alias dictionary (CATEGORY_ALIASES).
      3. Fuzzy match against DOMINANT values only (target freq >= 3x source freq AND
         edit distance <= 2 or token-sort ratio >= 90 AND not antonym/prefix pair).
    Canonical form = most frequent surface form after trimming (tie -> Title Case).
    Values already equal to canonical are never touched.
    """
    non_null = series.dropna().astype(str)
    if non_null.empty:
        return {"mapping": {}, "clusters": [], "groups": [], "distinct_values": {}, "variant_confidences": {}}

    raw_counts = non_null.value_counts()
    val_counts: dict[str, int] = {
        str(k): int(v)
        for k, v in raw_counts.items()
        if normalize_whitespace_string(str(k)) and normalize_whitespace_string(str(k)).lower() not in MISSING_TOKENS
    }
    trimmed_distinct = {normalize_whitespace_string(k) for k in val_counts}
    if len(val_counts) < 2 or len(trimmed_distinct) > max_distinct:
        return {"mapping": {}, "clusters": [], "groups": [], "distinct_values": val_counts, "variant_confidences": {}}

    # Stage 1a: Group by normalized key (lowercase, strip punctuation & spaces)
    key_groups: dict[str, dict[str, Any]] = {}
    for raw_v, cnt in val_counts.items():
        nk = _normalize_cat_key(raw_v)
        if not nk:
            continue
        if nk not in key_groups:
            key_groups[nk] = {"raws": [], "count": 0, "reasons": set(), "alias_target": False}
        key_groups[nk]["raws"].append(raw_v)
        key_groups[nk]["count"] += cnt

    # Stage 1b: Light singular/plural folding across distinct normalized keys
    sing_buckets: dict[str, list[str]] = {}
    for nk in key_groups:
        sk = _singularize_key(nk)
        sing_buckets.setdefault(sk, []).append(nk)

    for sk, nks in sing_buckets.items():
        if len(nks) <= 1:
            continue
        nks_sorted = sorted(nks, key=lambda k: key_groups[k]["count"], reverse=True)
        dominant_k = nks_sorted[0]
        for other_k in nks_sorted[1:]:
            if is_antonym_or_prefix_pair(dominant_k, other_k):
                continue
            key_groups[dominant_k]["raws"].extend(key_groups[other_k]["raws"])
            key_groups[dominant_k]["count"] += key_groups[other_k]["count"]
            key_groups[dominant_k]["reasons"].add("singular/plural folding")
            del key_groups[other_k]

    # Stage 2: Alias dictionary (CATEGORY_ALIASES)
    alias_merges: list[tuple[str, str]] = []
    for nk in list(key_groups.keys()):
        if nk in CATEGORY_ALIASES:
            tgt = CATEGORY_ALIASES[nk]
            if tgt in key_groups and tgt != nk:
                alias_merges.append((nk, tgt))

    for src_k, tgt_k in alias_merges:
        if src_k in key_groups and tgt_k in key_groups:
            key_groups[tgt_k]["raws"].extend(key_groups[src_k]["raws"])
            key_groups[tgt_k]["count"] += key_groups[src_k]["count"]
            key_groups[tgt_k]["reasons"].add("alias dictionary")
            key_groups[tgt_k]["alias_target"] = True
            del key_groups[src_k]

    # Stage 3: Fuzzy match against DOMINANT values only
    # Sort keys by count descending so dominant groups are checked first
    keys_by_freq = sorted(key_groups.keys(), key=lambda k: key_groups[k]["count"], reverse=True)
    merged_keys: set[str] = set()
    for src_k in reversed(keys_by_freq):
        if src_k in merged_keys or src_k not in key_groups:
            continue
        if len(src_k) < 4:
            continue
        src_cnt = key_groups[src_k]["count"]
        src_rep = normalize_whitespace_string(key_groups[src_k]["raws"][0])
        best_tgt = None
        best_dist = 999
        best_tgt_cnt = -1

        for tgt_k in keys_by_freq:
            if tgt_k == src_k or tgt_k in merged_keys or tgt_k not in key_groups:
                continue
            if len(tgt_k) < 4:
                continue
            tgt_cnt = key_groups[tgt_k]["count"]
            # Require target frequency >= 3x source frequency
            if tgt_cnt < 3 * src_cnt:
                continue
            if is_antonym_or_prefix_pair(src_k, tgt_k):
                continue
            dist = _levenshtein_distance(src_k, tgt_k)
            tgt_rep = normalize_whitespace_string(key_groups[tgt_k]["raws"][0])
            tsr = _token_sort_ratio(src_rep, tgt_rep)
            if dist <= 2 or tsr >= 90.0:
                if dist < best_dist or (dist == best_dist and tgt_cnt > best_tgt_cnt):
                    best_dist = dist
                    best_tgt = tgt_k
                    best_tgt_cnt = tgt_cnt

        if best_tgt is not None:
            key_groups[best_tgt]["raws"].extend(key_groups[src_k]["raws"])
            key_groups[best_tgt]["count"] += key_groups[src_k]["count"]
            key_groups[best_tgt]["reasons"].add("fuzzy match to dominant value")
            del key_groups[src_k]
            merged_keys.add(src_k)

    # Pick canonical surface form for each group that has > 1 raw variant (or trimmed != raw)
    mapping: dict[str, str] = {}
    variant_confidences: dict[str, str] = {}
    clusters: list[list[str]] = []
    groups_meta: list[dict[str, Any]] = []

    for nk, g in sorted(key_groups.items(), key=lambda kv: kv[1]["count"], reverse=True):
        raws = g["raws"]
        # Count trimmed surface forms
        trimmed_counts: dict[str, int] = {}
        for rv in raws:
            tv = normalize_whitespace_string(rv)
            trimmed_counts[tv] = trimmed_counts.get(tv, 0) + val_counts.get(rv, 0)

        # If alias_target, prefer trimmed forms whose normalized key matches the target key nk
        candidate_forms = list(trimmed_counts.keys())
        if g["alias_target"]:
            target_forms = [tv for tv in candidate_forms if _normalize_cat_key(tv) == nk]
            if target_forms:
                candidate_forms = target_forms

        # Canonical = most frequent trimmed surface form; tie -> Title Case
        canonical = max(
            candidate_forms,
            key=lambda tv: (trimmed_counts[tv], 1 if tv.istitle() else 0, tv),
        )
        # If top candidates tied and none is Title Case (e.g. all lowercase vs all uppercase), use Title Case
        max_cnt = trimmed_counts[canonical]
        tied = [tv for tv in candidate_forms if trimmed_counts[tv] == max_cnt]
        if len(tied) > 1 and not canonical.istitle():
            canonical = canonical.title()

        variants = [rv for rv in raws if rv != canonical]
        if not variants:
            continue

        for rv in variants:
            mapping[rv] = canonical
            variant_confidences[rv] = "high"

        cluster_list = [canonical] + variants
        clusters.append(cluster_list)
        reason_str = ", ".join(sorted(g["reasons"])) if g["reasons"] else "normalized whitespace/case"
        groups_meta.append({
            "canonical": canonical,
            "reasoning": f"Deterministic clustering ({reason_str}) to '{canonical}'",
            "variants": [
                {"value": v, "confidence": "high", "count": int(val_counts.get(v, 0))}
                for v in ([canonical] if canonical in val_counts else []) + variants
            ],
        })

    return {
        "mapping": mapping,
        "clusters": clusters,
        "groups": groups_meta,
        "distinct_values": val_counts,
        "variant_confidences": variant_confidences,
    }


def find_near_duplicate_categories(
    series: pd.Series, cutoff: float = 0.6
) -> list[list[str]]:
    """Cluster near-duplicate text values in a Series using deterministic 3-stage rules.
    Returns a list of clusters, where each cluster is [canonical_variant, variant2, variant3, ...].
    """
    res = cluster_categorical_column(series)
    return res["clusters"]


find_near_duplicate_category_clusters = find_near_duplicate_categories


def suggest_cleaning_steps(df: pd.DataFrame, profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate rule-based cleaning step suggestions from a dataframe and its profile report."""
    suggestions: list[dict[str, Any]] = []

    # 1. Duplicate rows check
    dup_rows = profile.get("duplicate_row_count", 0)
    if dup_rows > 0:
        suggestions.append({
            "id": str(uuid.uuid4()),
            "action": "drop_duplicates",
            "params": {},
            "description": f"Remove {dup_rows} duplicate row{'s' if dup_rows > 1 else ''}",
            "severity": "high",
        })

    # 1b. Possible duplicate rows (same non-blank email or phone with different row data — flag only, never delete)
    dedup_preview = df.drop_duplicates()
    if len(dedup_preview) >= 2:
        dup_key_cols: list[str] = []
        poss_dup_mask = pd.Series(False, index=dedup_preview.index, dtype=bool)
        for col_meta in profile.get("columns", []):
            cname = col_meta["name"]
            if cname not in dedup_preview.columns or "_flag_" in cname or cname.endswith("_outlier"):
                continue
            ctype = col_meta.get("inferred_type", "text")
            clow = cname.lower()
            is_em = (ctype == "email") or any(k in clow for k in ("email", "e-mail"))
            is_ph = (ctype == "phone") or any(k in clow for k in ("phone", "mobile", "contact"))
            if not (is_em or is_ph):
                continue
            s_vals = dedup_preview[cname].dropna().astype(str).map(normalize_whitespace_string)
            if is_em:
                s_vals = s_vals.str.lower()
            elif is_ph:
                s_vals = s_vals.map(lambda v: re.sub(r"\D", "", v[:-2] if v.endswith(".0") else v))
            s_vals = s_vals[(s_vals != "") & (~s_vals.str.lower().isin(MISSING_TOKENS))]
            if len(s_vals) >= 2:
                # Only treat as person-level duplicate key when column is predominantly unique (>50%)
                if (s_vals.nunique() / len(s_vals)) > 0.5:
                    dups = s_vals[s_vals.duplicated(keep=False)]
                    if not dups.empty:
                        dup_key_cols.append(cname)
                        poss_dup_mask.loc[dups.index] = True
        if dup_key_cols and poss_dup_mask.any():
            cnt = int(poss_dup_mask.sum())
            suggestions.append({
                "id": str(uuid.uuid4()),
                "action": "flag_possible_duplicates",
                "params": {"columns": dup_key_cols},
                "description": f"Flag {cnt} possible duplicate rows sharing the same {', '.join(dup_key_cols)} (no rows deleted)",
                "severity": "medium",
            })

    # 2. Column missing values, text cleanliness, fuzzy categories, and numeric validity checks
    for col in profile.get("columns", []):
        col_name = col["name"]
        if col_name not in df.columns:
            continue
        # Skip generated flag / outlier columns to guarantee idempotency (G5)
        if "_flag_" in col_name or col_name.endswith("_outlier"):
            continue

        col_series = df[col_name]
        missing_count = col.get("missing_count", 0)
        missing_pct = col.get("missing_pct", 0)
        inferred_type = col.get("inferred_type", "text")
        col_lower = col_name.lower()
        is_phone_col = (inferred_type == "phone") or any(k in col_lower for k in ("phone", "mobile", "contact"))
        is_email_col = (inferred_type == "email") or any(k in col_lower for k in ("email", "e-mail"))

        # Missing values
        # PII / unique-per-person column types must NEVER be offered
        # fill_mode/fill_mean/fill_median — doing so would fabricate a real
        # person's actual value on a row where it doesn't belong.  The only
        # valid options for these types are drop_missing (remove the row) or
        # flag_missing (leave as null).
        _PII_TYPES = {
            "email", "phone", "name", "id", "handle", "address",
            "uuid", "payment_id", "transaction_id", "product_code",
            "url", "ip_address", "filepath",
        }
        is_pii_col = is_phone_col or is_email_col or inferred_type in _PII_TYPES
        # Also catch by effective_type (which runs the full 47-type detector)
        if not is_pii_col:
            _eff = detect_semantic_type(col_series, col_name)
            if _eff in _PII_TYPES:
                is_pii_col = True

        # Exclude rows already explained by {col}_flag_invalid so reruns stay idempotent (G5)
        unexplained_missing_count = missing_count
        if missing_count > 0 and f"{col_name}_flag_invalid" in df.columns:
            _inv_mask = df[f"{col_name}_flag_invalid"].fillna(False).astype(bool)
            _cur_miss = col_series.isna() | col_series.astype(str).str.strip().str.lower().isin(MISSING_TOKENS)
            unexplained_missing_count = int((_cur_miss & (~_inv_mask)).sum())

        if unexplained_missing_count > 0:
            if missing_pct >= 50.0:
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "drop_column",
                    "params": {"column": col_name},
                    "description": f"Drop column '{col_name}' ({missing_pct}% missing values)",
                    "severity": "high",
                })
            elif is_pii_col:
                # PII columns: NEVER drop rows (G2 hard gate). Leave as null and flag.
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_missing",
                    "params": {"column": col_name},
                    "description": (
                        f"Flag {unexplained_missing_count} missing value{'s' if unexplained_missing_count > 1 else ''} "
                        f"in '{col_name}' (unique-per-person column — row retained as null)"
                    ),
                    "severity": "medium",
                })
            elif (
                inferred_type in ("numeric", "non_negative_numeric", "identifier", "currency", "salary", "percentage", "marks", "rating", "integer", "float")
                or (col_name in df.columns and pd.api.types.is_numeric_dtype(df[col_name]))
            ):
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_missing",
                    "params": {"column": col_name},
                    "description": f"Flag {unexplained_missing_count} missing value{'s' if unexplained_missing_count > 1 else ''} in '{col_name}'",
                    "severity": "medium",
                })
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "fill_missing",
                    "params": {"column": col_name, "strategy": "median"},
                    "description": f"Fill {unexplained_missing_count} missing value{'s' if unexplained_missing_count > 1 else ''} in '{col_name}' with median",
                    "severity": "low",
                    "recommended": False,
                })
            else:
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_missing",
                    "params": {"column": col_name},
                    "description": f"Flag {unexplained_missing_count} missing value{'s' if unexplained_missing_count > 1 else ''} in '{col_name}'",
                    "severity": "medium",
                })
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "fill_missing",
                    "params": {"column": col_name, "strategy": "mode"},
                    "description": f"Fill {unexplained_missing_count} missing value{'s' if unexplained_missing_count > 1 else ''} in '{col_name}' with mode",
                    "severity": "low",
                    "recommended": False,
                })

        # Centralised per-type validation via COLUMN_TYPE_RULES registry.
        # Uses the full 47-type semantic detection from validation_rules.py.
        # Determines effective type for this column and runs the registered
        # validator if one exists.
        effective_type = detect_semantic_type(col_series, col_name)
        # Backward compat overrides:
        if is_phone_col:
            effective_type = "phone"
        elif is_email_col:
            effective_type = "email"

        is_coord_col = effective_type in ("latitude", "longitude")
        is_name_col = effective_type == "name"
        is_qty_col = effective_type == "quantity" or col_lower in ("quantity", "qty")
        is_amount_col = effective_type in ("currency", "salary") or col_lower in ("amount", "price", "salary", "revenue", "cost")

        rule_fn = COLUMN_TYPE_RULES.get(effective_type)
        if rule_fn is not None:
            flagged_items = rule_fn(col_series, col_name)
            if flagged_items:
                action_name = f"flag_invalid_{effective_type}"
                sample_details = ""
                raw_samples = []
                for it in flagged_items:
                    rv = it.get("raw_value")
                    if rv is None:
                        rv = it.get("value")
                    if pd.notna(rv) and str(rv).strip():
                        raw_samples.append(str(rv).strip())
                if raw_samples:
                    sample_details = f" ({', '.join(raw_samples[:4])})"
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": action_name,
                    "params": {"column": col_name, "flagged_count": len(flagged_items)},
                    "description": (
                        f"Flag {len(flagged_items)} {effective_type} value"
                        f"{'s' if len(flagged_items) > 1 else ''}"
                        f" with invalid format in '{col_name}'{sample_details}"
                    ),
                    "severity": "medium",
                    "recommended": True,
                    "flagged_values": flagged_items,
                })


        # Phase 3a & 4: Non-numeric text values or formatted numbers in numeric-typed columns (excluding phone)
        if not is_phone_col and not is_email_col and (
            inferred_type in ("numeric", "non_negative_numeric", "identifier", "currency", "salary", "age", "integer", "float", "quantity", "decimal")
            or effective_type in ("numeric", "non_negative_numeric", "currency", "salary", "age", "integer", "float", "quantity", "decimal", "latitude", "longitude")
            or pd.api.types.is_numeric_dtype(col_series)
        ):
            non_null = col_series.dropna()
            if not non_null.empty:
                raw_coerced = pd.to_numeric(non_null, errors="coerce")
                raw_fails = int((non_null.notna() & raw_coerced.isna()).sum())

                cleaned_non_null = non_null.apply(clean_numeric_value)
                coerced = pd.to_numeric(cleaned_non_null, errors="coerce")
                failed_mask = non_null.notna() & coerced.isna()
                unparseable_count = int(failed_mask.sum())

                is_stored_as_text = str(col_series.dtype) == "object" or not pd.api.types.is_numeric_dtype(col_series)

                if unparseable_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "coerce_numeric",
                        "params": {"column": col_name},
                        "description": f"Convert {unparseable_count} non-numeric text value{'s' if unparseable_count > 1 else ''} in '{col_name}' to NaN",
                        "severity": "high",
                    })
                elif is_stored_as_text and (inferred_type in ("numeric", "non_negative_numeric") or raw_fails > 0):
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "coerce_numeric",
                        "params": {"column": col_name},
                        "description": f"Convert '{col_name}' to numeric (strip currency symbols and commas)",
                        "severity": "medium",
                    })

        # Phase 4b: Fallback — detect currency/comma-formatted numeric columns that profiling typed as text
        # This catches columns like "Revenue" containing "₹1,500" where pd.to_numeric() alone fails,
        # causing the profiler to label them as "text" instead of "numeric".
        elif not is_phone_col and not is_email_col and (
            inferred_type in ("text", "categorical")
            and str(col_series.dtype) == "object"
        ):
            non_null = col_series.dropna()
            if len(non_null) >= 2:
                cleaned_vals = non_null.apply(clean_numeric_value)
                coerced_vals = pd.to_numeric(cleaned_vals, errors="coerce")
                valid_count = int(coerced_vals.notna().sum())
                # If ≥50% of non-null values become valid numbers after stripping
                # currency symbols and commas, this is a numeric column in disguise
                if valid_count >= max(2, len(non_null) * 0.5):
                    # Check that raw pd.to_numeric would actually fail on some values
                    # (otherwise there's nothing to clean and no suggestion needed)
                    raw_coerced = pd.to_numeric(non_null, errors="coerce")
                    raw_valid = int(raw_coerced.notna().sum())
                    if raw_valid < valid_count:
                        suggestions.append({
                            "id": str(uuid.uuid4()),
                            "action": "coerce_numeric",
                            "params": {"column": col_name},
                            "description": f"Convert '{col_name}' to numeric (strip currency symbols and commas)",
                            "severity": "medium",
                        })

        # Phase 3b: Negative values in numeric / non_negative_numeric columns (excluding phone & coordinates)
        if not is_phone_col and not is_email_col and not is_coord_col and (
            inferred_type in ("non_negative_numeric", "numeric", "currency", "salary", "age", "integer", "float", "quantity")
            or effective_type in ("currency", "salary", "age", "quantity")
            or pd.api.types.is_numeric_dtype(col_series)
        ):
            coerced_nums = pd.to_numeric(col_series.apply(clean_numeric_value), errors="coerce")
            neg_mask = coerced_nums < 0
            neg_count = int(neg_mask.sum())
            if neg_count > 0:
                flagged_items = []
                for idx in col_series.index[neg_mask]:
                    raw_v = col_series.loc[idx]
                    num_v = coerced_nums.loc[idx]
                    sugg_v = abs(num_v) if pd.notna(num_v) else 0
                    if hasattr(sugg_v, "item"):
                        sugg_v = sugg_v.item()
                    raw_out = raw_v
                    if hasattr(raw_out, "item"):
                        raw_out = raw_out.item()
                    elif not isinstance(raw_out, (int, float, str)):
                        raw_out = str(raw_out)

                    flagged_items.append({
                        "row_index": int(idx),
                        "raw_value": raw_out,
                        "suggested_value": sugg_v,
                        "reason": f"Negative value ({raw_v}) in non-negative column",
                    })
                val_previews = ", ".join(str(f["raw_value"]) for f in flagged_items[:3])
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "flag_negative_values",
                    "params": {"column": col_name},
                    "description": f"Flag {neg_count} negative value{'s' if neg_count > 1 else ''} in '{col_name}': {val_previews}",
                    "severity": "medium",
                    "flagged_values": flagged_items,
                })

            # Phase 3c: Zero values in quantity columns (keep value + flag_zero)
            if is_qty_col:
                zero_mask = coerced_nums == 0
                zero_count = int(zero_mask.sum())
                if zero_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "flag_zero_values",
                        "params": {"column": col_name},
                        "description": f"Flag {zero_count} zero value{'s' if zero_count > 1 else ''} in '{col_name}' (value kept)",
                        "severity": "medium",
                    })

            # Phase 3d: Sentinel values in amount/salary/price columns (keep value + flag_suspect)
            if is_amount_col:
                sentinels = DOMAIN_RULES["amount"]["sentinels"]
                sentinel_mask = coerced_nums.isin(sentinels)
                sentinel_count = int(sentinel_mask.sum())
                if sentinel_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "flag_suspect_values",
                        "params": {"column": col_name},
                        "description": f"Flag {sentinel_count} suspect sentinel value{'s' if sentinel_count > 1 else ''} in '{col_name}' (value kept)",
                        "severity": "medium",
                    })

        # Text cleanliness checks for text/categorical columns (excluding phone)
        if not is_phone_col and (inferred_type in ("text", "categorical", "email") or str(col_series.dtype) == "object"):
            non_null_str = col_series.dropna().astype(str)
            if not non_null_str.empty:
                # 1a. Extra spaces
                space_mask = non_null_str.str.contains(r"^\s|\s$|\s{2,}", regex=True)
                space_count = int(space_mask.sum())
                if space_count > 0:
                    suggestions.append({
                        "id": str(uuid.uuid4()),
                        "action": "trim_whitespace",
                        "params": {"column": col_name},
                        "description": f"Trim leading/trailing and extra internal spaces in '{col_name}' ({space_count} value{'s' if space_count > 1 else ''})",
                        "severity": "low",
                    })

                # 1b. Deterministic 3-stage category consistency (standardize_category)
                has_category_clusters = False
                is_date_col = inferred_type in ("datetime", "date") or effective_type == "date" or any(k in col_name.lower() for k in ("date", "dob"))
                is_non_cat = is_date_col or is_name_col or is_email_col or is_phone_col or effective_type in ("id", "latitude", "longitude", "age", "quantity", "currency", "salary")
                if not is_non_cat and inferred_type not in ("numeric", "non_negative_numeric", "identifier", "email") and (
                    inferred_type in ("categorical", "text")
                    or (str(col_series.dtype) == "object" and col_series.nunique() <= 60)
                ):
                    cat_res = cluster_categorical_column(col_series, max_distinct=60)
                    mapping = cat_res["mapping"]
                    groups_meta = cat_res["groups"]
                    val_counts = cat_res["distinct_values"]
                    variant_confidences = cat_res["variant_confidences"]
                    if mapping:
                        sample_pairs = [f"'{k}' → '{v}'" for k, v in list(mapping.items())[:4]]
                        suggestions.append({
                            "id": str(uuid.uuid4()),
                            "action": "standardize_category",
                            "params": {
                                "column": col_name,
                                "mapping": mapping,
                                "distinct_values": val_counts,
                                "variant_confidences": variant_confidences,
                                "groups": groups_meta,
                            },
                            "description": f"Standardize {len(mapping)} category variant{'s' if len(mapping) > 1 else ''} in '{col_name}' ({', '.join(sample_pairs)})",
                            "severity": "medium",
                            "recommended": True,
                        })
                        has_category_clusters = True

                # 1c. Inconsistent capitalization (skip names/emails/ids/dates so mixed-case names like McDonald stay intact)
                if not is_non_cat:
                    stripped_str = non_null_str.str.strip()
                    lower_groups = stripped_str.groupby(stripped_str.str.lower()).nunique()
                    inconsistent_groups = lower_groups[lower_groups > 1]
                    if not inconsistent_groups.empty:
                        title_cnt = int(stripped_str.apply(lambda s: s.istitle()).sum())
                        lower_cnt = int(stripped_str.apply(lambda s: s.islower()).sum())
                        case_param = "title" if title_cnt >= lower_cnt else "lower"

                        suggestions.append({
                            "id": str(uuid.uuid4()),
                            "action": "normalize_case",
                            "params": {"column": col_name, "case": case_param},
                            "description": f"Normalize inconsistent capitalization in '{col_name}' ({len(inconsistent_groups)} variant group{'s' if len(inconsistent_groups) > 1 else ''})",
                            "severity": "low",
                        })

        # 3. Numeric outlier checks (excluding phone)
        if not is_phone_col:
            numeric_stats = col.get("numeric_stats")
            if numeric_stats and numeric_stats.get("outlier_count", 0) > 0:
                outlier_cnt = numeric_stats["outlier_count"]
                suggestions.append({
                    "id": str(uuid.uuid4()),
                    "action": "remove_outliers",
                    "params": {"column": col_name, "method": "iqr"},
                    "description": f"Flag {outlier_cnt} outlier{'s' if outlier_cnt > 1 else ''} in '{col_name}' with IQR method (adds '{col_name}_outlier' column)",
                    "severity": "medium",
                })

    return suggestions


def apply_pipeline(
    df: pd.DataFrame, steps: list[Any]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Execute a list of cleaning steps sequentially on a DataFrame and return (cleaned_df, log)."""
    cleaned_df = df.copy()
    log: list[dict[str, Any]] = []

    for step in steps:
        if hasattr(step, "action"):
            action = step.action
            params = step.params or {}
            description = step.description
        else:
            action = step.get("action", "")
            params = step.get("params") or {}
            description = step.get("description", "")

        rows_before = len(cleaned_df)

        if action == "drop_duplicates":
            cleaned_df = cleaned_df.drop_duplicates()
        elif action == "drop_column":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df = cleaned_df.drop(columns=[col])
        elif action == "drop_missing":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df = cleaned_df.dropna(subset=[col])
            else:
                cleaned_df = cleaned_df.dropna()
        elif action == "fill_missing":
            col = params.get("column")
            strategy = params.get("strategy", "median")
            if col and col in cleaned_df.columns:
                if strategy == "median":
                    num = pd.to_numeric(cleaned_df[col], errors="coerce")
                    fill_val = num.median() if not num.dropna().empty else 0
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                elif strategy == "mean":
                    num = pd.to_numeric(cleaned_df[col], errors="coerce")
                    fill_val = num.mean() if not num.dropna().empty else 0
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                elif strategy == "mode":
                    mode_res = cleaned_df[col].mode()
                    fill_val = mode_res.iloc[0] if not mode_res.empty else "Unknown"
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                else:
                    fill_val = params.get("value", "Unknown")
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
        elif action == "trim_whitespace":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                non_null_mask = cleaned_df[col].notna()
                cleaned_df.loc[non_null_mask, col] = (
                    cleaned_df.loc[non_null_mask, col]
                    .astype(str)
                    .apply(normalize_whitespace_string)
                )
        elif action == "flag_missing":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                col_s = cleaned_df[col]
                missing_mask = col_s.isna() | col_s.astype(str).str.strip().str.lower().isin(MISSING_TOKENS)
                invalid_col = f"{col}_flag_invalid"
                if invalid_col in cleaned_df.columns:
                    missing_mask = missing_mask & (~cleaned_df[invalid_col].fillna(False).astype(bool))
                if missing_mask.any():
                    cleaned_df.loc[missing_mask, col] = None
                    cleaned_df[f"{col}_flag_missing"] = missing_mask
        elif action == "normalize_case":
            col = params.get("column")
            case = params.get("case", "title")
            if col and col in cleaned_df.columns:
                non_null_mask = cleaned_df[col].notna()
                # When a style is applied, also strip leading/trailing whitespace and collapse internal double-spaces
                trimmed = (
                    cleaned_df.loc[non_null_mask, col]
                    .astype(str)
                    .str.strip()
                    .str.replace(r"\s+", " ", regex=True)
                )
                if case == "title":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.title()
                elif case == "lower":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.lower()
                elif case == "upper":
                    cleaned_df.loc[non_null_mask, col] = trimmed.str.upper()
        elif action == "standardize_category":
            col = params.get("column")
            mapping = params.get("mapping", {})
            if col and col in cleaned_df.columns and mapping:
                # Phase 3: Build mapping ONCE per distinct raw value before touching any rows
                norm_map: dict[str, str] = {}
                for k, v in mapping.items():
                    k_str = str(k)
                    if k_str not in norm_map:
                        norm_map[k_str] = v
                    k_strip = k_str.strip()
                    if k_strip not in norm_map:
                        norm_map[k_strip] = v
                    k_lower = k_strip.lower()
                    if k_lower not in norm_map:
                        norm_map[k_lower] = v

                distinct_vals = cleaned_df[col].dropna().unique()
                lookup: dict[Any, Any] = {}
                for val in distinct_vals:
                    v_str = str(val)
                    v_strip = v_str.strip()
                    v_lower = v_strip.lower()
                    if v_str in mapping:
                        lookup[val] = mapping[v_str]
                    elif v_strip in mapping:
                        lookup[val] = mapping[v_strip]
                    elif v_str in norm_map:
                        lookup[val] = norm_map[v_str]
                    elif v_strip in norm_map:
                        lookup[val] = norm_map[v_strip]
                    elif v_lower in norm_map:
                        lookup[val] = norm_map[v_lower]

                if lookup:
                    cleaned_df[col] = cleaned_df[col].replace(lookup)
        elif action == "standardize_date_format":
            col = params.get("column")
            value_map = params.get("value_map") or {}
            if col and col in cleaned_df.columns and value_map:
                cleaned_df[col] = cleaned_df[col].replace(value_map)
                resilient_map = {}
                for k, v in value_map.items():
                    k_str = str(k)
                    resilient_map[k_str] = v
                    resilient_map[k_str.strip()] = v
                cleaned_df[col] = cleaned_df[col].replace(resilient_map)
        elif action == "coerce_numeric":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                # Explicitly exclude phone and id columns from coerce_numeric
                col_lower = col.lower()
                is_phone = (col_lower in ("phone", "mobile", "contact_no")) or ("phone" in col_lower)
                is_id = (col_lower in ("id", "record_id", "user_id")) or ("id" in col_lower and not col_lower.endswith("_idx"))
                if not is_phone and not is_id:
                    cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                    num = pd.to_numeric(cleaned_series, errors="coerce")
                    non_null = num.dropna()
                    if not non_null.empty and (non_null % 1 == 0).all():
                        cleaned_df[col] = num.astype("Int64")
                    else:
                        cleaned_df[col] = num
        elif action == "flag_negative_values":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                neg_mask = (num < 0).fillna(False)
                if neg_mask.any():
                    cleaned_df[f"{col}_flag_negative"] = neg_mask
        elif action == "flag_zero_values":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                zero_mask = (num == 0).fillna(False)
                if zero_mask.any():
                    cleaned_df[f"{col}_flag_zero"] = zero_mask
        elif action == "flag_suspect_values":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                sentinels = DOMAIN_RULES["amount"]["sentinels"]
                suspect_mask = num.isin(sentinels).fillna(False)
                if suspect_mask.any():
                    cleaned_df[f"{col}_flag_suspect"] = suspect_mask
        elif action == "flag_invalid_name":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        continue
                    s_raw = normalize_whitespace_string(str(val))
                    if not s_raw or s_raw.lower() in MISSING_TOKENS:
                        continue
                    cleaned_val, changed = clean_name_value(val)
                    if not cleaned_val:
                        cleaned_df.at[idx, col] = None
                        invalid_mask.at[idx] = True
                    elif changed:
                        cleaned_df.at[idx, col] = cleaned_val
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
        elif action == "flag_invalid_email":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        continue
                    cleaned_val, status, changed = clean_email_value(val)
                    if status == "invalid":
                        cleaned_df.at[idx, col] = None
                        invalid_mask.at[idx] = True
                    elif status == "valid" and changed:
                        cleaned_df.at[idx, col] = cleaned_val
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
        elif action == "flag_invalid_phone":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].astype(object)
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        continue
                    cleaned_val, status, changed = clean_phone_value(val)
                    if status == "invalid":
                        cleaned_df.at[idx, col] = None
                        invalid_mask.at[idx] = True
                    elif status == "valid" and (changed or not isinstance(val, str)):
                        cleaned_df.at[idx, col] = cleaned_val
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
        elif action == "flag_invalid_age":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                min_age = DOMAIN_RULES["age"]["min"]
                max_age = DOMAIN_RULES["age"]["max"]
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                new_vals: list[Any] = []
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        new_vals.append(None)
                        continue
                    s_raw = normalize_whitespace_string(str(val))
                    if not s_raw or s_raw.lower() in MISSING_TOKENS:
                        new_vals.append(None)
                        continue
                    parsed = clean_numeric_value(val)
                    try:
                        num = float(parsed)
                        if pd.isna(num):
                            raise ValueError
                    except (ValueError, TypeError):
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                        continue
                    if num < min_age or num > max_age:
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                    else:
                        new_vals.append(int(num) if num % 1 == 0 else num)
                num_series = pd.to_numeric(pd.Series(new_vals, index=cleaned_df.index), errors="coerce")
                non_null = num_series.dropna()
                if not non_null.empty and (non_null % 1 == 0).all():
                    cleaned_df[col] = num_series.astype("Int64")
                else:
                    cleaned_df[col] = num_series
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
        elif action in ("flag_invalid_currency", "flag_invalid_salary"):
            col = params.get("column")
            if col and col in cleaned_df.columns:
                sentinels = DOMAIN_RULES["amount"]["sentinels"]
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                suspect_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                new_vals = []
                changed_any = False
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        new_vals.append(val)
                        continue
                    s_raw = normalize_whitespace_string(str(val))
                    if not s_raw or s_raw.lower() in MISSING_TOKENS:
                        new_vals.append(None)
                        changed_any = True
                        continue
                    parsed = clean_numeric_value(val)
                    try:
                        num = float(parsed)
                        if pd.isna(num):
                            raise ValueError
                    except (ValueError, TypeError):
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                        changed_any = True
                        continue
                    if num < 0:
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                        changed_any = True
                    elif num in sentinels:
                        new_vals.append(val)
                        suspect_mask.at[idx] = True
                    else:
                        if isinstance(val, str):
                            new_vals.append(num)
                            changed_any = True
                        else:
                            new_vals.append(val)
                if changed_any:
                    cleaned_df[col] = pd.to_numeric(pd.Series(new_vals, index=cleaned_df.index), errors="coerce")
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
                if suspect_mask.any():
                    cleaned_df[f"{col}_flag_suspect"] = suspect_mask
        elif action in ("flag_invalid_latitude", "flag_invalid_longitude"):
            col = params.get("column")
            if col and col in cleaned_df.columns:
                rule_key = "latitude" if action == "flag_invalid_latitude" else "longitude"
                min_v = DOMAIN_RULES[rule_key]["min"]
                max_v = DOMAIN_RULES[rule_key]["max"]
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                new_vals = []
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        new_vals.append(None)
                        continue
                    s_raw = normalize_whitespace_string(str(val))
                    if not s_raw:
                        new_vals.append(None)
                        continue
                    if s_raw.lower() in MISSING_TOKENS:
                        new_vals.append(None)
                        if s_raw.lower() in ("unknown", "not available"):
                            invalid_mask.at[idx] = True
                        continue
                    try:
                        num = float(s_raw)
                        if pd.isna(num):
                            raise ValueError
                    except (ValueError, TypeError):
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                        continue
                    if num < min_v or num > max_v:
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                    else:
                        new_vals.append(num)
                cleaned_df[col] = pd.to_numeric(pd.Series(new_vals, index=cleaned_df.index), errors="coerce")
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
        elif action == "flag_invalid_date":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                date_order = analyze_column_date_order(cleaned_df[col])
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                ambig_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                suspect_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        continue
                    parsed_val, status, changed = parse_explicit_date(val, date_order=date_order)
                    if status == "invalid":
                        cleaned_df.at[idx, col] = None
                        invalid_mask.at[idx] = True
                    elif status == "ambiguous":
                        ambig_mask.at[idx] = True
                    elif status == "suspect":
                        if changed and parsed_val is not None:
                            cleaned_df.at[idx, col] = parsed_val
                        suspect_mask.at[idx] = True
                    elif status == "valid" and changed and parsed_val is not None:
                        cleaned_df.at[idx, col] = parsed_val
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
                if ambig_mask.any():
                    cleaned_df[f"{col}_flag_ambiguous"] = ambig_mask
                if suspect_mask.any():
                    cleaned_df[f"{col}_flag_suspect"] = suspect_mask
        elif action == "flag_invalid_quantity":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                invalid_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                neg_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                zero_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                new_vals = []
                for idx, val in cleaned_df[col].items():
                    if val is None or pd.isna(val):
                        new_vals.append(None)
                        continue
                    s_raw = normalize_whitespace_string(str(val))
                    if not s_raw or s_raw.lower() in MISSING_TOKENS:
                        new_vals.append(None)
                        continue
                    parsed = clean_numeric_value(val)
                    try:
                        num = float(parsed)
                        if pd.isna(num):
                            raise ValueError
                    except (ValueError, TypeError):
                        new_vals.append(None)
                        invalid_mask.at[idx] = True
                        continue
                    if num < 0:
                        neg_mask.at[idx] = True
                    elif num == 0:
                        zero_mask.at[idx] = True
                    if num % 1 != 0:
                        invalid_mask.at[idx] = True
                    new_vals.append(int(num) if num % 1 == 0 else num)
                num_series = pd.to_numeric(pd.Series(new_vals, index=cleaned_df.index), errors="coerce")
                non_null = num_series.dropna()
                if not non_null.empty and (non_null % 1 == 0).all():
                    cleaned_df[col] = num_series.astype("Int64")
                else:
                    cleaned_df[col] = num_series
                if invalid_mask.any():
                    cleaned_df[f"{col}_flag_invalid"] = invalid_mask
                if neg_mask.any():
                    cleaned_df[f"{col}_flag_negative"] = neg_mask
                if zero_mask.any():
                    cleaned_df[f"{col}_flag_zero"] = zero_mask
        elif action == "flag_invalid_id":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].astype(object)
                reassigned_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)

                # Detect dominant ID pattern (e.g. REC-1001 -> prefix='REC-', width=4, max_num=1115)
                id_pattern_re = re.compile(r"^([A-Za-z_\-\s]*?)(\d+)$")
                prefix_counts: dict[str, int] = {}
                prefix_max: dict[str, int] = {}
                prefix_width: dict[str, int] = {}
                all_existing_ids: set[str] = set()

                for val in cleaned_df[col]:
                    if val is None or pd.isna(val):
                        continue
                    s = normalize_whitespace_string(str(val))
                    if not s or s.lower() in MISSING_TOKENS:
                        continue
                    all_existing_ids.add(s)
                    m = id_pattern_re.match(s)
                    if m:
                        pfx, num_str = m.group(1), m.group(2)
                        num_val = int(num_str)
                        prefix_counts[pfx] = prefix_counts.get(pfx, 0) + 1
                        prefix_max[pfx] = max(prefix_max.get(pfx, 0), num_val)
                        prefix_width[pfx] = max(prefix_width.get(pfx, 0), len(num_str))

                if prefix_counts:
                    dom_prefix = max(prefix_counts, key=lambda p: prefix_counts[p])
                    next_num = prefix_max[dom_prefix] + 1
                    num_width = prefix_width[dom_prefix]
                else:
                    dom_prefix = "ID-"
                    next_num = 1
                    num_width = 4

                seen_so_far: set[str] = set()
                for idx, val in cleaned_df[col].items():
                    s = ""
                    if val is not None and not pd.isna(val):
                        s = normalize_whitespace_string(str(val))
                    is_blank = (not s) or (s.lower() in MISSING_TOKENS)
                    is_collision = (not is_blank) and (s in seen_so_far)

                    if is_blank or is_collision:
                        while True:
                            candidate = f"{dom_prefix}{str(next_num).zfill(num_width)}"
                            next_num += 1
                            if candidate not in all_existing_ids and candidate not in seen_so_far:
                                break
                        cleaned_df.at[idx, col] = candidate
                        all_existing_ids.add(candidate)
                        seen_so_far.add(candidate)
                        reassigned_mask.at[idx] = True
                    else:
                        if s != str(val):
                            cleaned_df.at[idx, col] = s
                        seen_so_far.add(s)

                if reassigned_mask.any():
                    cleaned_df[f"{col}_flag_reassigned"] = reassigned_mask
        elif action == "flag_possible_duplicates":
            key_cols = params.get("columns") or []
            if key_cols:
                poss_mask = pd.Series(False, index=cleaned_df.index, dtype=bool)
                for cname in key_cols:
                    if cname not in cleaned_df.columns:
                        continue
                    clow = cname.lower()
                    is_em = any(k in clow for k in ("email", "e-mail"))
                    is_ph = any(k in clow for k in ("phone", "mobile", "contact"))
                    s_vals = cleaned_df[cname].dropna().astype(str).map(normalize_whitespace_string)
                    if is_em:
                        s_vals = s_vals.str.lower()
                    elif is_ph:
                        s_vals = s_vals.map(lambda v: re.sub(r"\D", "", v[:-2] if v.endswith(".0") else v))
                    s_vals = s_vals[(s_vals != "") & (~s_vals.str.lower().isin(MISSING_TOKENS))]
                    if len(s_vals) >= 2 and (s_vals.nunique() / len(s_vals)) > 0.5:
                        dups = s_vals[s_vals.duplicated(keep=False)]
                        if not dups.empty:
                            poss_mask.loc[dups.index] = True
                if poss_mask.any():
                    cleaned_df["_flag_possible_duplicate"] = poss_mask
        elif action == "clip_negative_to_null":
            col = params.get("column")
            if col and col in cleaned_df.columns:
                cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                num = pd.to_numeric(cleaned_series, errors="coerce")
                cleaned_df.loc[num < 0, col] = None
        elif action == "manual_value_override":
            # Phase 6: Direct cell value overrides by row index or matching raw value
            col = params.get("column")
            overrides = params.get("overrides", {})
            if col and col in cleaned_df.columns and overrides:
                for key, new_val in overrides.items():
                    set_by_idx = False
                    try:
                        idx = int(key)
                        if idx in cleaned_df.index:
                            cleaned_df.at[idx, col] = new_val
                            set_by_idx = True
                    except (ValueError, TypeError):
                        set_by_idx = False

                    if not set_by_idx:
                        mask = cleaned_df[col].astype(str) == str(key)
                        if mask.any():
                            cleaned_df.loc[mask, col] = new_val
        elif action == "remove_outliers":
            # Non-destructive: add a boolean flag column instead of deleting rows.
            col = params.get("column")
            if col and col in cleaned_df.columns:
                col_lower = col.lower()
                is_phone = (col_lower in ("phone", "mobile", "contact_no")) or ("phone" in col_lower)
                if not is_phone:
                    cleaned_series = cleaned_df[col].apply(clean_numeric_value)
                    num = pd.to_numeric(cleaned_series, errors="coerce")
                    non_null = num.dropna()
                    if not non_null.empty:
                        q1 = non_null.quantile(0.25)
                        q3 = non_null.quantile(0.75)
                        iqr = q3 - q1
                        lower_fence = q1 - 1.5 * iqr
                        upper_fence = q3 + 1.5 * iqr
                        outlier_mask = ((num < lower_fence) | (num > upper_fence)).fillna(False)
                        if outlier_mask.any():
                            cleaned_df[f"{col}_outlier"] = outlier_mask

        rows_after = len(cleaned_df)
        rows_affected = max(0, rows_before - rows_after)

        log.append({
            "action": action,
            "description": description,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "rows_affected": rows_affected,
        })

    return cleaned_df, log