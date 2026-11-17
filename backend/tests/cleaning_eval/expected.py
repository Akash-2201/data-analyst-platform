"""
Expected test assertions for messy_project_testing_dataset_120_rows.xlsx.
Machine-checkable specifications for all must-pass cases from Section 3.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ExpectedCase:
    category: str
    case_id: str
    description: str
    check_fn: Callable[[Any, Any], tuple[str, str]]
    # check_fn(raw_df, cleaned_df) -> (status, detail)
    # status: "fixed" | "flagged_only" | "silently_kept" | "silently_wrong" | "deleted_wrongly"


def get_expected_cases() -> list[ExpectedCase]:
    cases = []

    # 1. Exact duplicates (3 injected)
    for dup_id in ["REC-1010", "REC-1025", "REC-1050"]:
        def _check_dup(raw_df, cleaned_df, target_id=dup_id):
            matches = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if len(matches) == 1:
                return "fixed", f"{target_id} kept exactly once"
            elif len(matches) > 1:
                return "silently_kept", f"{target_id} still appears {len(matches)} times"
            else:
                return "deleted_wrongly", f"{target_id} completely deleted"

        cases.append(ExpectedCase(
            category="Duplicates",
            case_id=f"dup_{dup_id}",
            description=f"Exact duplicate {dup_id} removed; appears exactly once",
            check_fn=_check_dup,
        ))

    # Total row count check (must be 117)
    def _check_row_count(raw_df, cleaned_df):
        if len(cleaned_df) == 117:
            return "fixed", "Cleaned dataframe has exactly 117 rows"
        elif len(cleaned_df) < 117:
            return "deleted_wrongly", f"Cleaned dataframe has {len(cleaned_df)} rows (< 117, rows wrongly deleted)"
        else:
            return "silently_kept", f"Cleaned dataframe has {len(cleaned_df)} rows (> 117, duplicates not removed)"

    cases.append(ExpectedCase(
        category="Row Count",
        case_id="row_count_117",
        description="Dataset row count is exactly 117 (only 3 exact duplicates removed)",
        check_fn=_check_row_count,
    ))

    # 2. ID collisions (2 injected: REC-1005 row 113, REC-1040 row 114)
    def _check_collision_1005(raw_df, cleaned_df):
        # The collision row was user113@example.com / Rahul
        row = cleaned_df[cleaned_df["Email"].astype(str).str.strip() == "user113@example.com"]
        if row.empty:
            return "deleted_wrongly", "Row with user113@example.com was deleted"
        cur_id = row.iloc[0]["Record_ID"]
        flag_val = row.iloc[0].get("Record_ID_flag_reassigned", False)
        if cur_id != "REC-1005" and (flag_val is True or bool(flag_val)):
            return "fixed", f"Reassigned to {cur_id} and flagged"
        elif cur_id != "REC-1005":
            return "fixed", f"Reassigned to {cur_id}"
        else:
            return "silently_kept", f"Still has colliding ID {cur_id}"

    cases.append(ExpectedCase(
        category="ID Collision",
        case_id="collision_REC-1005",
        description="Second REC-1005 (Rahul, user113@example.com) gets new unique ID + flag",
        check_fn=_check_collision_1005,
    ))

    def _check_collision_1040(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Email"].astype(str).str.strip() == "user114@example.com"]
        if row.empty:
            return "deleted_wrongly", "Row with user114@example.com was deleted"
        cur_id = row.iloc[0]["Record_ID"]
        flag_val = row.iloc[0].get("Record_ID_flag_reassigned", False)
        if cur_id != "REC-1040" and (flag_val is True or bool(flag_val)):
            return "fixed", f"Reassigned to {cur_id} and flagged"
        elif cur_id != "REC-1040":
            return "fixed", f"Reassigned to {cur_id}"
        else:
            return "silently_kept", f"Still has colliding ID {cur_id}"

    cases.append(ExpectedCase(
        category="ID Collision",
        case_id="collision_REC-1040",
        description="Second REC-1040 (Ravi, user114@example.com) gets new unique ID + flag",
        check_fn=_check_collision_1040,
    ))

    # 3. Blank Customer_Names (REC-1003, REC-1057)
    for rid in ["REC-1003", "REC-1057"]:
        def _check_blank_name(raw_df, cleaned_df, target_id=rid):
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted (G2 violation)"
            val = row.iloc[0]["Customer_Name"]
            flag = row.iloc[0].get("Customer_Name_flag_missing", False)
            import pandas as pd
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
            if is_blank:
                return "fixed", f"{target_id} retained with blank name (flag={flag})"
            else:
                return "silently_wrong", f"{target_id} name was fabricated as {repr(val)}"

        cases.append(ExpectedCase(
            category="Missing Values (Row Retention)",
            case_id=f"blank_name_{rid}",
            description=f"{rid} retained with blank Customer_Name + flag_missing",
            check_fn=_check_blank_name,
        ))

    # 4. Customer_Name formatting (5 injected)
    name_checks = [
        ("REC-1002", "Akash", "  akash "),
        ("REC-1007", "Ravi", "RAVI"),
        ("REC-1092", "Meera", "  Meera"),
        ("REC-1019", "Priya", "Priya123"),
        ("REC-1034", "Ananya", "Ananya@"),
    ]
    for rid, expected_name, raw_val in name_checks:
        def _check_name(raw_df, cleaned_df, target_id=rid, exp=expected_name):
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = str(row.iloc[0]["Customer_Name"]).strip()
            if val == exp:
                return "fixed", f"Customer_Name correctly formatted to {exp}"
            elif val == raw_val.strip() or val == raw_val:
                return "silently_kept", f"Customer_Name unchanged: {repr(val)}"
            else:
                return "silently_wrong", f"Customer_Name transformed to unexpected value: {repr(val)}"

        cases.append(ExpectedCase(
            category="Customer_Name",
            case_id=f"name_{rid}",
            description=f"{rid}: Customer_Name {repr(raw_val)} -> {expected_name}",
            check_fn=_check_name,
        ))

    # 5. Email (6 injected)
    def _check_email_trim(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1090"]
        if row.empty:
            return "deleted_wrongly", "REC-1090 was deleted"
        val = str(row.iloc[0]["Email"]).strip()
        if val == "user90@example.com":
            return "fixed", "user90@example.com trimmed"
        return "silently_kept", f"Email was {repr(val)}"

    cases.append(ExpectedCase(
        category="Email",
        case_id="email_trim_REC-1090",
        description="REC-1090: ' user90@example.com ' -> user90@example.com",
        check_fn=_check_email_trim,
    ))

    def _check_email_collapse(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1022"]
        if row.empty:
            return "deleted_wrongly", "REC-1022 was deleted"
        val = str(row.iloc[0]["Email"]).strip()
        if val == "akash@gmail.com":
            return "fixed", "akash@@gmail.com collapsed to akash@gmail.com"
        return "silently_kept", f"Email was {repr(val)}"

    cases.append(ExpectedCase(
        category="Email",
        case_id="email_collapse_REC-1022",
        description="REC-1022: akash@@gmail.com -> akash@gmail.com",
        check_fn=_check_email_collapse,
    ))

    for rid, raw_em in [("REC-1011", "invalidemail"), ("REC-1039", "user.com")]:
        def _check_invalid_email(raw_df, cleaned_df, target_id=rid):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = row.iloc[0]["Email"]
            flag = row.iloc[0].get("Email_flag_invalid", False)
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
            if is_blank and bool(flag):
                return "fixed", f"{target_id} invalid email blanked and Email_flag_invalid set"
            elif is_blank:
                return "fixed", f"{target_id} invalid email blanked"
            elif bool(flag):
                return "flagged_only", f"{target_id} invalid email kept but flagged"
            else:
                return "silently_kept", f"{target_id} invalid email kept without flag"

        cases.append(ExpectedCase(
            category="Email",
            case_id=f"email_invalid_{rid}",
            description=f"{rid}: {raw_em} -> blank + Email_flag_invalid",
            check_fn=_check_invalid_email,
        ))

    for rid in ["REC-1014", "REC-1089"]:
        def _check_blank_email(raw_df, cleaned_df, target_id=rid):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = row.iloc[0]["Email"]
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
            if is_blank:
                return "fixed", f"{target_id} blank email preserved (never filled)"
            else:
                return "silently_wrong", f"{target_id} blank email fabricated as {repr(val)}"

        cases.append(ExpectedCase(
            category="Email",
            case_id=f"email_blank_{rid}",
            description=f"{rid}: blank email stays blank + flag_missing (never filled)",
            check_fn=_check_blank_email,
        ))

    # 6. Phone (3 injected)
    def _check_phone_91(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1047"]
        if row.empty:
            return "deleted_wrongly", "REC-1047 was deleted"
        val = str(row.iloc[0]["Phone"]).strip()
        if val == "9876543210":
            return "fixed", "+91-98765-43210 normalized to 9876543210"
        return "silently_kept", f"Phone was {repr(val)}"

    cases.append(ExpectedCase(
        category="Phone",
        case_id="phone_norm_REC-1047",
        description="REC-1047: +91-98765-43210 -> 9876543210",
        check_fn=_check_phone_91,
    ))

    for rid, raw_ph in [("REC-1009", "12345"), ("REC-1028", "abc9876543")]:
        def _check_invalid_phone(raw_df, cleaned_df, target_id=rid):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = row.iloc[0]["Phone"]
            flag = row.iloc[0].get("Phone_flag_invalid", False)
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
            if is_blank and bool(flag):
                return "fixed", f"{target_id} invalid phone blanked and Phone_flag_invalid set"
            elif is_blank:
                return "fixed", f"{target_id} invalid phone blanked"
            elif bool(flag):
                return "flagged_only", f"{target_id} invalid phone kept but flagged"
            else:
                return "silently_kept", f"{target_id} invalid phone kept without flag"

        cases.append(ExpectedCase(
            category="Phone",
            case_id=f"phone_invalid_{rid}",
            description=f"{rid}: {raw_ph} -> blank + Phone_flag_invalid",
            check_fn=_check_invalid_phone,
        ))

    # 7. City (5 injected + 6 distinct check)
    def _check_city_mumbai(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1029"]
        if row.empty:
            return "deleted_wrongly", "REC-1029 was deleted"
        val = str(row.iloc[0]["City"]).strip()
        if val == "Mumbai":
            return "fixed", "Mum bai normalized to Mumbai"
        return "silently_kept", f"City was {repr(val)}"

    cases.append(ExpectedCase(
        category="City",
        case_id="city_mumbai_REC-1029",
        description="REC-1029: 'Mum bai' -> Mumbai",
        check_fn=_check_city_mumbai,
    ))

    def _check_city_delhi(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1044"]
        if row.empty:
            return "deleted_wrongly", "REC-1044 was deleted"
        val = str(row.iloc[0]["City"]).strip()
        if val == "Delhi":
            return "fixed", "DELHI normalized to Delhi"
        return "silently_kept", f"City was {repr(val)}"

    cases.append(ExpectedCase(
        category="City",
        case_id="city_delhi_REC-1044",
        description="REC-1044: DELHI -> Delhi",
        check_fn=_check_city_delhi,
    ))

    def _check_city_bengaluru(raw_df, cleaned_df):
        # All Bangalore/bengaluru should be Bengaluru
        cities = cleaned_df["City"].dropna().astype(str).str.strip().tolist()
        b_variants = [c for c in cities if c.lower() in ["bangalore", "bengaluru"]]
        non_beng = [c for c in b_variants if c != "Bengaluru"]
        if not non_beng and len(b_variants) > 0:
            return "fixed", f"All {len(b_variants)} Bangalore variants unified to Bengaluru"
        elif len(non_beng) > 0:
            return "silently_kept", f"Unmerged variants exist: {set(non_beng)}"
        return "silently_wrong", "No Bengaluru entries found"

    cases.append(ExpectedCase(
        category="City",
        case_id="city_bengaluru_variants",
        description="Bangalore / ' Bangalore ' / bengaluru -> Bengaluru",
        check_fn=_check_city_bengaluru,
    ))

    def _check_city_blank(raw_df, cleaned_df):
        import pandas as pd
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1033"]
        if row.empty:
            return "deleted_wrongly", "REC-1033 was deleted"
        val = row.iloc[0]["City"]
        is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
        if is_blank:
            return "fixed", "REC-1033 blank city preserved + flag_missing"
        return "silently_wrong", f"REC-1033 city was filled with {repr(val)}"

    cases.append(ExpectedCase(
        category="City",
        case_id="city_blank_REC-1033",
        description="REC-1033: blank city stays blank + City_flag_missing",
        check_fn=_check_city_blank,
    ))

    def _check_distinct_cities(raw_df, cleaned_df):
        cities = set(cleaned_df["City"].dropna().astype(str).str.strip().unique()) - {"", "nan", "None"}
        expected_cities = {"Bengaluru", "Chennai", "Delhi", "Hyderabad", "Mumbai", "Pune"}
        if cities == expected_cities:
            return "fixed", f"Exactly 6 canonical cities: {sorted(list(cities))}"
        elif len(cities) > 6:
            extra = cities - expected_cities
            return "silently_kept", f"More than 6 distinct cities ({len(cities)}): extra {extra}"
        else:
            return "silently_wrong", f"Fewer than 6 distinct cities ({len(cities)}): {cities}"

    cases.append(ExpectedCase(
        category="City",
        case_id="city_distinct_6",
        description="Exactly 6 distinct non-blank cities (Bengaluru, Chennai, Delhi, Hyderabad, Mumbai, Pune)",
        check_fn=_check_distinct_cities,
    ))

    # 8. Category (4 injected + 4 distinct check)
    def _check_cat_electronics(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1071"]
        if row.empty:
            return "deleted_wrongly", "REC-1071 was deleted"
        val = str(row.iloc[0]["Category"]).strip()
        if val == "Electronics":
            return "fixed", "Eletronics normalized to Electronics"
        return "silently_kept", f"Category was {repr(val)}"

    cases.append(ExpectedCase(
        category="Category",
        case_id="cat_electronics_REC-1071",
        description="REC-1071: 'Eletronics' -> Electronics",
        check_fn=_check_cat_electronics,
    ))

    def _check_cat_grocery(raw_df, cleaned_df):
        cats = cleaned_df["Category"].dropna().astype(str).str.strip().tolist()
        groc_sing = [c for c in cats if c == "Grocery"]
        if not groc_sing and "Groceries" in cats:
            return "fixed", "'Grocery' folded to 'Groceries'"
        return "silently_kept", f"{len(groc_sing)} 'Grocery' instances remain"

    cases.append(ExpectedCase(
        category="Category",
        case_id="cat_grocery_folding",
        description="'Grocery' folded into 'Groceries'",
        check_fn=_check_cat_grocery,
    ))

    def _check_distinct_categories(raw_df, cleaned_df):
        cats = set(cleaned_df["Category"].dropna().astype(str).str.strip().unique()) - {"", "nan", "None"}
        expected_cats = {"Clothing", "Electronics", "Furniture", "Groceries"}
        if cats == expected_cats:
            return "fixed", f"Exactly 4 canonical categories: {sorted(list(cats))}"
        elif len(cats) > 4:
            extra = cats - expected_cats
            return "silently_kept", f"More than 4 distinct categories ({len(cats)}): extra {extra}"
        else:
            return "silently_wrong", f"Fewer than 4 distinct categories ({len(cats)}): {cats}"

    cases.append(ExpectedCase(
        category="Category",
        case_id="cat_distinct_4",
        description="Exactly 4 distinct categories (Clothing, Electronics, Furniture, Groceries)",
        check_fn=_check_distinct_categories,
    ))

    # 9. Purchase_Date (5 injected)
    date_format_checks = [
        ("REC-1013", "2026-03-15", "15/03/2026"),
        ("REC-1023", "2026-03-22", "March 22, 2026"),
        ("REC-1038", "2026-04-10", "2026/04/10"),
    ]
    for rid, exp_iso, raw_str in date_format_checks:
        def _check_date_fmt(raw_df, cleaned_df, target_id=rid, exp=exp_iso):
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = str(row.iloc[0]["Purchase_Date"]).strip()
            # check string or parsed date
            if val.startswith(exp):
                return "fixed", f"{target_id}: parsed as {exp}"
            return "silently_kept", f"{target_id}: date is {repr(val)}"

        cases.append(ExpectedCase(
            category="Purchase_Date",
            case_id=f"date_parsed_{rid}",
            description=f"{rid}: {raw_str} -> {exp_iso}",
            check_fn=_check_date_fmt,
        ))

    for rid, raw_dt in [("REC-1049", "not available"), ("REC-1060", "2026-15-45")]:
        def _check_invalid_date(raw_df, cleaned_df, target_id=rid):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = row.iloc[0]["Purchase_Date"]
            flag = row.iloc[0].get("Purchase_Date_flag_invalid", False)
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none", "nat"]
            if is_blank and bool(flag):
                return "fixed", f"{target_id} impossible/non-date blanked + Purchase_Date_flag_invalid set"
            elif is_blank:
                return "fixed", f"{target_id} impossible/non-date blanked"
            elif bool(flag):
                return "flagged_only", f"{target_id} impossible date kept but flagged"
            else:
                return "silently_kept", f"{target_id} impossible date kept without flag"

        cases.append(ExpectedCase(
            category="Purchase_Date",
            case_id=f"date_invalid_{rid}",
            description=f"{rid}: {raw_dt} -> blank + Purchase_Date_flag_invalid",
            check_fn=_check_invalid_date,
        ))

    # 10. Age (3 injected)
    def _check_age_word(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1024"]
        if row.empty:
            return "deleted_wrongly", "REC-1024 was deleted"
        val = row.iloc[0]["Age"]
        try:
            if int(val) == 20:
                return "fixed", "Age 'Twenty' parsed to 20"
        except (ValueError, TypeError):
            pass
        return "silently_kept", f"Age was {repr(val)}"

    cases.append(ExpectedCase(
        category="Age",
        case_id="age_word_REC-1024",
        description="REC-1024: 'Twenty' -> 20 (number-word)",
        check_fn=_check_age_word,
    ))

    for rid, raw_v in [("REC-1004", 150), ("REC-1016", -5)]:
        def _check_invalid_age(raw_df, cleaned_df, target_id=rid):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            val = row.iloc[0]["Age"]
            flag = row.iloc[0].get("Age_flag_invalid", False)
            is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
            if is_blank and bool(flag):
                return "fixed", f"{target_id} out-of-bounds age blanked + Age_flag_invalid"
            elif is_blank:
                return "fixed", f"{target_id} out-of-bounds age blanked"
            elif bool(flag):
                return "flagged_only", f"{target_id} out-of-bounds age kept but flagged"
            else:
                return "silently_kept", f"{target_id} out-of-bounds age kept without flag"

        cases.append(ExpectedCase(
            category="Age",
            case_id=f"age_bounds_{rid}",
            description=f"{rid}: Age {raw_v} -> blank + Age_flag_invalid",
            check_fn=_check_invalid_age,
        ))

    # Age Int64 check
    def _check_age_int64(raw_df, cleaned_df):
        import pandas as pd
        dt = str(cleaned_df["Age"].dtype)
        if dt.startswith("Int") or dt.startswith("int"):
            return "fixed", f"Age column is integer dtype: {dt}"
        # Check if values have trailing .0
        str_vals = cleaned_df["Age"].dropna().astype(str).tolist()
        has_dots = any(v.endswith(".0") for v in str_vals)
        if not has_dots:
            return "fixed", f"Age values have no .0, dtype={dt}"
        return "silently_kept", f"Age has floating point representation (.0), dtype={dt}"

    cases.append(ExpectedCase(
        category="Age",
        case_id="age_dtype_int64",
        description="Age column is Int64 (no '19.0')",
        check_fn=_check_age_int64,
    ))

    # 11. Quantity (3 injected)
    def _check_qty_word(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1065"]
        if row.empty:
            return "deleted_wrongly", "REC-1065 was deleted"
        val = row.iloc[0]["Quantity"]
        try:
            if int(val) == 10:
                return "fixed", "Quantity 'Ten' parsed to 10"
        except (ValueError, TypeError):
            pass
        return "silently_kept", f"Quantity was {repr(val)}"

    cases.append(ExpectedCase(
        category="Quantity",
        case_id="qty_word_REC-1065",
        description="REC-1065: 'Ten' -> 10 (number-word)",
        check_fn=_check_qty_word,
    ))

    def _check_qty_zero(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1063"]
        if row.empty:
            return "deleted_wrongly", "REC-1063 was deleted"
        val = row.iloc[0]["Quantity"]
        flag = row.iloc[0].get("Quantity_flag_zero", False)
        if int(val) == 0 and bool(flag):
            return "fixed", "Quantity 0 kept + Quantity_flag_zero set"
        elif int(val) == 0:
            return "flagged_only", "Quantity 0 kept without specific flag"
        return "silently_wrong", f"Quantity was altered to {repr(val)}"

    cases.append(ExpectedCase(
        category="Quantity",
        case_id="qty_zero_REC-1063",
        description="REC-1063: Quantity 0 -> kept + Quantity_flag_zero",
        check_fn=_check_qty_zero,
    ))

    def _check_qty_negative(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1064"]
        if row.empty:
            return "deleted_wrongly", "REC-1064 was deleted"
        val = row.iloc[0]["Quantity"]
        flag = row.iloc[0].get("Quantity_flag_negative", False)
        if int(val) == -3 and bool(flag):
            return "fixed", "Quantity -3 kept + Quantity_flag_negative set"
        elif int(val) == -3:
            return "flagged_only", "Quantity -3 kept without specific flag"
        return "silently_wrong", f"Quantity was altered to {repr(val)}"

    cases.append(ExpectedCase(
        category="Quantity",
        case_id="qty_negative_REC-1064",
        description="REC-1064: Quantity -3 -> kept + Quantity_flag_negative",
        check_fn=_check_qty_negative,
    ))

    # 12. Amount (2 injected)
    def _check_amount_negative(raw_df, cleaned_df):
        import pandas as pd
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1030"]
        if row.empty:
            return "deleted_wrongly", "REC-1030 was deleted"
        val = row.iloc[0]["Amount"]
        flag = row.iloc[0].get("Amount_flag_invalid", False)
        is_blank = pd.isna(val) or str(val).strip() == "" or str(val).strip().lower() in ["nan", "none"]
        if is_blank and bool(flag):
            return "fixed", "REC-1030: negative amount blanked + Amount_flag_invalid set"
        elif is_blank:
            return "fixed", "REC-1030: negative amount blanked"
        elif bool(flag):
            return "flagged_only", "REC-1030: negative amount kept but flagged"
        return "silently_kept", f"REC-1030: negative amount kept: {repr(val)}"

    cases.append(ExpectedCase(
        category="Amount",
        case_id="amt_negative_REC-1030",
        description="REC-1030: Amount -4500 -> blank + Amount_flag_invalid",
        check_fn=_check_amount_negative,
    ))

    def _check_amount_sentinel(raw_df, cleaned_df):
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1055"]
        if row.empty:
            return "deleted_wrongly", "REC-1055 was deleted"
        val = float(row.iloc[0]["Amount"])
        flag = row.iloc[0].get("Amount_flag_suspect", False)
        if val == 9999999.0 and bool(flag):
            return "fixed", "REC-1055: sentinel 9999999 kept + Amount_flag_suspect set"
        elif val == 9999999.0:
            return "flagged_only", "REC-1055: sentinel 9999999 kept without suspect flag"
        return "silently_wrong", f"REC-1055: sentinel was altered: {repr(val)}"

    cases.append(ExpectedCase(
        category="Amount",
        case_id="amt_sentinel_REC-1055",
        description="REC-1055: Amount 9999999 -> kept + Amount_flag_suspect",
        check_fn=_check_amount_sentinel,
    ))

    # 13. Coordinates (5 injected)
    def _check_coord_unknown(raw_df, cleaned_df):
        import pandas as pd
        row = cleaned_df[cleaned_df["Record_ID"] == "REC-1080"]
        if row.empty:
            return "deleted_wrongly", "REC-1080 was deleted"
        lat = row.iloc[0]["Latitude"]
        is_blank = pd.isna(lat) or str(lat).strip() in ["", "nan", "none", "unknown"]
        flag = row.iloc[0].get("Latitude_flag_missing", False) or row.iloc[0].get("Latitude_flag_invalid", False)
        if (pd.isna(lat) or str(lat).strip() in ["", "nan", "none"]) and bool(flag):
            return "fixed", "Latitude 'unknown' blanked and flagged"
        elif pd.isna(lat) or str(lat).strip() in ["", "nan", "none"]:
            return "fixed", "Latitude 'unknown' blanked"
        return "silently_kept", f"Latitude was {repr(lat)}"

    cases.append(ExpectedCase(
        category="Coordinates",
        case_id="coord_unknown_REC-1080",
        description="REC-1080: Latitude 'unknown' -> blank + flag",
        check_fn=_check_coord_unknown,
    ))

    coord_bounds = [
        ("REC-1012", "Latitude", 123.456, "lat 123.456 > 90"),
        ("REC-1031", "Latitude", -200.0, "lat -200 < -90"),
        ("REC-1036", "Longitude", 250.123, "lon 250.123 > 180"),
        ("REC-1048", "Longitude", -500.0, "lon -500 < -180"),
    ]
    for rid, col, val_in, desc in coord_bounds:
        def _check_coord_bound(raw_df, cleaned_df, target_id=rid, cname=col):
            import pandas as pd
            row = cleaned_df[cleaned_df["Record_ID"] == target_id]
            if row.empty:
                return "deleted_wrongly", f"{target_id} was deleted"
            v = row.iloc[0][cname]
            flag = row.iloc[0].get(f"{cname}_flag_invalid", False)
            is_blank = pd.isna(v) or str(v).strip() in ["", "nan", "none"]
            if is_blank and bool(flag):
                return "fixed", f"{target_id}: {cname} blanked + {cname}_flag_invalid set"
            elif is_blank:
                return "fixed", f"{target_id}: {cname} blanked"
            elif bool(flag):
                return "flagged_only", f"{target_id}: {cname} kept but flagged"
            return "silently_kept", f"{target_id}: {cname} kept: {repr(v)}"

        cases.append(ExpectedCase(
            category="Coordinates",
            case_id=f"coord_bound_{rid}_{col}",
            description=f"{rid}: {desc} -> blank + {col}_flag_invalid",
            check_fn=_check_coord_bound,
        ))

    return cases
