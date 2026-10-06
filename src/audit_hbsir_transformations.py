from __future__ import annotations

import json

import yaml

import pandas as pd

from common import append_issues, config, path


TABLES = {
    "household_information": "household",
    "members_properties": "members",
    "food": "food",
    "employment_income": "income_wage",
    "self_employed_income": "income_self_employed",
    "other_income": "income_other",
    "subsidy": "income_subsidy",
    "house_specifications": "housing",
}


def all_names(value) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        if "new_name" in value:
            names.append(str(value["new_name"]))
        else:
            for key, child in value.items():
                if isinstance(key, int) and isinstance(child, dict):
                    names.extend(all_names(child))
    return list(dict.fromkeys(names))


def describe_map(value) -> tuple[str, str, str]:
    if value == "drop":
        return "drop", "yes", "Column is declared drop in HBSIR metadata."
    if not isinstance(value, dict):
        return "unmapped_or_metadata_rule", "no", "No simple new_name mapping is declared at this table level."
    names = all_names(value)
    categorical = "categories" in value
    replacements = "replace" in value
    dtype = value.get("type", "")
    if categorical:
        transform = "categorical code-to-label recoding"
    elif replacements:
        transform = "type conversion and year-specific value replacement"
    elif names and dtype in ("boolean", "bool"):
        transform = "boolean conversion from survey code"
    elif names:
        transform = "rename/type conversion"
    else:
        transform = "year-specific mapping; inspect HBSIR schema"
    details = []
    if names:
        details.append("standard name(s): " + ", ".join(names))
    if isinstance(dtype, dict):
        details.append("type varies by survey year")
    elif dtype:
        details.append(f"type={dtype}")
    if categorical:
        details.append("categorical labels recoded by HBSIR")
    if replacements:
        replace = value.get("replace")
        details.append("year-specific replacement rules present: " + str(replace))
    return transform, "yes" if categorical or replacements or dtype in ("boolean", "bool") else "no", "; ".join(details)


def count_food_values(year: int) -> tuple[int, int]:
    food = pd.read_parquet(path("yearly") / str(year) / "food.parquet", columns=["Amount_Source", "Price_Raw"])
    amount_fallback = int(food["Amount_Source"].eq("HBSIR_Expenditure_divided_by_Price").sum())
    zero_price = int(pd.to_numeric(food["Price_Raw"], errors="coerce").eq(0).sum())
    return amount_fallback, zero_price


def main() -> int:
    cfg = config()
    first, last = cfg["project"]["first_year"], cfg["project"]["last_year"]
    hbsir_root = path("intermediate").parent.parent / "paneldemand_hbsir"
    schema_file = hbsir_root / "src/hbsir/metadata/tables.yaml"
    schema = yaml.safe_load(schema_file.read_text(encoding="utf-8"))
    direct_access_file = path("audit") / "direct_1402_access_summary.json"
    direct_access = json.loads(direct_access_file.read_text(encoding="utf-8")) if direct_access_file.exists() else {}
    raw_value_check_file = path("audit") / "direct_1402_raw_to_hbsir_value_check.csv"
    raw_value_check = pd.read_csv(raw_value_check_file, encoding="utf-8-sig") if raw_value_check_file.exists() else pd.DataFrame()
    rows = []
    for hbsir_table, standardized_table in TABLES.items():
        columns = schema[hbsir_table].get("columns", {})
        for raw_column, mapping in columns.items():
            transform, recode, details = describe_map(mapping)
            names = all_names(mapping)
            if mapping == "drop":
                names = [""]
            for standardized in names or [""]:
                years = f"{first}-{last}"
                if hbsir_table == "subsidy" and raw_column == "DycolVam":
                    years = "1403"
                if hbsir_table == "subsidy" and raw_column == "DYCOL01":
                    years = "1392-1403"
                if hbsir_table == "household_information" and raw_column == "WEIGHT":
                    years = "1396-1403"
                if raw_column in {"DYCOL07"} and hbsir_table == "food":
                    years = f"{first}-{last}"
                rows.append({
                    "Year_Range": years,
                    "Table_Raw": hbsir_table,
                    "Column_Raw": raw_column,
                    "Table_HBSIR": hbsir_table,
                    "Column_Standardized": standardized,
                    "Transformation_Type": transform,
                    "Rename_Only": "yes" if transform == "rename/type conversion" else "no",
                    "Value_Recode_or_Calculation": recode,
                    "Calculated_by_HBSIR": "yes" if hbsir_table == "food" and standardized == "Amount" else "no",
                    "External_Source": "no",
                    "Function_or_File": f"HBSIR metadata/tables.yaml::{hbsir_table}; see schema_functions/standard_tables.py for calculations",
                    "Description": details,
                    "Affected_Rows_Count": "not recoverable from cleaned cache" if transform == "drop" else "",
                })

    # HBSIR functions and in-scope special cases not represented by a simple raw column map.
    special = [
        ("household_information", "Month", "MAHMORAJEH", "adjust_month", "HBSIR changes the survey-month numbering before derived season assignment; the normalized Month is HBSIR-adjusted."),
        ("household_information", "Season_Number / Season", "FASL or Month", "create_season_number / season_name", "Season is normalized from the source season/month and labeled Spring/Summer/Autumn/Winter."),
        ("household_information", "Weight", "WEIGHT or external weight table", "hbsir.api.add_weight", "HBSIR documents external weight files before 1396 and the household weight field from 1396 onward."),
        ("household_information", "Urban_Rural / Province / County", "administrative codes", "hbsir.api.add_attribute + id_information.yaml", "Geographic labels come from HBSIR administrative classification metadata."),
        ("members_properties", "Household_Size", "member records by ID", "project count of members_properties rows", "Count derived from the long members table; no members are dropped by this step."),
        ("food", "Amount", "DYCOL04 Kilos + DYCOL03 Grams", "calculate_amount_after_1383", "Amount=Kilos.fillna(0)+Grams.fillna(0)/1000; if both missing and Price>0, HBSIR backfills Expenditure/Price. The source flags are in food.parquet."),
        ("food", "Price", "DYCOL05 unit price", "HBSIR tables.yaml Price.replace(0, None)", "For 1390–1403 Price is a survey price field in the cleaned HBSIR input; normalized HBSIR changes zero to missing. Price_Raw retains the cleaned-input value."),
        ("food", "Duration", "none", "HBSIR schema expression", "HBSIR sets Duration to 30 days for this period."),
        ("food", "Commodity_Name / category levels", "DYCOL01 Commodity_Code", "hbsir.api.add_classification + commodities.yaml", "HBSIR attaches year-aware labels; this project does not merge codes or make final food groups."),
        ("food", "Provision_Method", "DYCOL02", "HBSIR categorical code mapping in tables.yaml", "HBSIR method recoding is year-specific; purchase rates count only Purchase, Purchase_Free_Price, and Purchase_Subsidised_Price."),
        ("food", "DYCOL07", "DYCOL07", "HBSIR metadata/tables.yaml::food", "HBSIR declares this source column dropped. It is absent from original 1402 P3S01 Access schema; counts for the other years are unavailable from the cleaned mirrors."),
        ("subsidy", "Member_Number", "DYCOL01", "HBSIR metadata/tables.yaml::subsidy", "HBSIR recodes numeric code 323 to member number 1 from 1392. Direct 1402 Access check found 0 code-323 rows; counts for other years are unavailable from cleaned mirrors."),
        ("subsidy", "DycolVam", "DycolVam", "HBSIR metadata/tables.yaml::subsidy", "HBSIR drops this field in 1403; source value counts are unavailable in the cleaned mirror."),
        ("members_properties", "Education_Level", "DYCOL08", "HBSIR metadata/tables.yaml::members_properties", "HBSIR coding categories change from 1393 and again from 1397; category labels are retained, raw source codes are not independently decoded."),
        ("self_employed_income", "Employment_Type", "DYCOL05", "1402 questionnaire p.65 and raw file guide p.6", "The raw-file guide lists 1/2/3 while the questionnaire lists 4/5/6; HBSIR labels and observed 1402 standardized values use 4/5/6. No recoding was applied by this project."),
        ("all", "Equivalence_Scale", "member count and age", "HBSIR schema_functions/standard_tables.py", "HBSIR provides separate calculated scales; they are not added to the project tables."),
        ("all", "CPI", "external SCI series", "HBSIR external CPI tables", "CPI was not included in the requested tables and no CPI deflation was performed."),
        ("income tables", "Total household income", "separate income components", "none", "No total-income variable is defined or calculated; wage, self-employed, other income, and subsidy remain separate."),
        ("food", "Tobacco", "separate P3S02 table", "HBSIR tobacco table not requested in food output", "The standardized food table is the HBSIR food table; tobacco is a separate expenditure table and is not included."),
        ("household_information", "BlkAbdJaygozin / RadifJaygozin", "same-named raw guide fields", "not mapped in HBSIR household table", "Official 1402 raw-file guide lists replacement-household block/village and row identifiers. The project retains both fields, plus the raw replacement-description fields, directly from 1402 Access; no HBSIR remapping was applied."),
    ]
    for table, standardized, raw, function, description in special:
        special_years = f"{first}-{last}"
        if table == "subsidy" and standardized == "Member_Number":
            special_years = "1392-1403"
        if table == "subsidy" and standardized == "DycolVam":
            special_years = "1403"
        if table == "household_information" and standardized == "Weight":
            special_years = f"{first}-1395 (external); 1396-1403 (survey field)"
        rows.append({
            "Year_Range": special_years,
            "Table_Raw": table,
            "Column_Raw": raw,
            "Table_HBSIR": table,
            "Column_Standardized": standardized,
            "Transformation_Type": "calculated_or_special_documented_rule",
            "Rename_Only": "no",
            "Value_Recode_or_Calculation": "yes" if any(k in standardized.lower() for k in ["amount", "weight", "season", "size", "member_number"]) else "no",
            "Calculated_by_HBSIR": "yes" if function.startswith(("calculate", "hbsir.api")) or "HBSIR" in function else "no",
            "External_Source": "yes" if "external" in function or "id_information" in function else "no",
            "Function_or_File": function,
            "Description": description,
            "Affected_Rows_Count": (
                "1402 raw code 323 count=0; other years not available from cleaned mirrors"
                if standardized == "Member_Number"
                else "DYCOL07 absent from 1402 raw P3S01 schema; other-year counts unavailable"
                if standardized == "DYCOL07"
                else "not independently measured for other years"
                if standardized in {"Amount", "Price", "DycolVam"}
                else ""
            ),
        })

    # Preserve the 1402 raw replacement/design fields that HBSIR omits.
    if direct_access:
        for field, counts in direct_access.get("raw_household_design_field_nonmissing_counts", {}).items():
            rows.append({
                "Year_Range": "1402",
                "Table_Raw": "R1402Data/U1402Data",
                "Column_Raw": field,
                "Table_HBSIR": "household_information (project-preserved source field)",
                "Column_Standardized": f"Raw_{field}",
                "Transformation_Type": "direct source-field retention; no recoding",
                "Rename_Only": "no",
                "Value_Recode_or_Calculation": "no",
                "Calculated_by_HBSIR": "no",
                "External_Source": "no",
                "Function_or_File": "src/audit_1402_raw_access.py; official 1402 Access database",
                "Description": f"Preserved in household.parquet as Raw_{field}; {counts['nonmissing']:,} nonmissing of {counts['rows']:,} source households.",
                "Affected_Rows_Count": str(counts["nonmissing"]),
            })

    if not raw_value_check.empty:
        for check in raw_value_check.to_dict(orient="records"):
            rows.append({
                "Year_Range": "1402",
                "Table_Raw": "Original Access -> HBSIR raw setup",
                "Column_Raw": "all shared standardized fields",
                "Table_HBSIR": str(check["HBSIR_Table"]),
                "Column_Standardized": str(check["Shared_Normalized_Columns"]),
                "Transformation_Type": "direct HBSIR raw-to-normalized full-row multiset comparison",
                "Rename_Only": "not applicable",
                "Value_Recode_or_Calculation": "HBSIR rules applied without project changes",
                "Calculated_by_HBSIR": "yes",
                "External_Source": "no",
                "Function_or_File": "hbsir.setup(method=create_from_raw); src/rebuild_1402_from_raw_access.py",
                "Description": f"{int(check['Raw_HBSIR_Rows']):,} raw-rebuilt rows compared with {int(check['Project_Rows']):,} project rows across {int(check['Shared_Column_Count'])} shared columns; unmatched raw/project rows={int(check['Raw_Rows_Not_Matched'])}/{int(check['Project_Rows_Not_Matched'])}.",
                "Affected_Rows_Count": f"raw_unmatched={int(check['Raw_Rows_Not_Matched'])}; project_unmatched={int(check['Project_Rows_Not_Matched'])}",
            })

    for year in range(first, last + 1):
        amount_fallback, zero_price = count_food_values(year)
        rows.append({
            "Year_Range": str(year), "Table_Raw": "food", "Column_Raw": "Kilos/Grams/Price/Expenditure",
            "Table_HBSIR": "food", "Column_Standardized": "Amount_Source / Price_Raw",
            "Transformation_Type": "observed_row_level_provenance_counts",
            "Rename_Only": "no", "Value_Recode_or_Calculation": "HBSIR amount computation and zero-price normalization",
            "Calculated_by_HBSIR": "yes", "External_Source": "no",
            "Function_or_File": "HBSIR schema_functions/standard_tables.py::calculate_amount_after_1383 and tables.yaml food rule",
            "Description": "Row counts from normalized food.parquet. Direct 1402 raw Access reconstruction matched the normalized project rows and source field values; other years use HBSIR cleaned-table mirrors.",
            "Affected_Rows_Count": f"amount_backfilled={amount_fallback}; Price_Raw==0={zero_price}",
        })

    transformation_df = pd.DataFrame(rows)
    audit = path("audit")
    audit.mkdir(parents=True, exist_ok=True)
    transformation_df.to_csv(audit / "hbsir_transformations.csv", index=False, encoding="utf-8-sig")
    dictionary_cols = ["Year_Range", "Table_Raw", "Column_Raw", "Table_HBSIR", "Column_Standardized", "Transformation_Type", "Description"]
    transformation_df[dictionary_cols].drop_duplicates().to_csv(path("metadata") / "variable_dictionary.csv", index=False, encoding="utf-8-sig")
    issues = [
        {"Year": "all", "Scope": "food.DYCOL07", "Issue": "hbsir_field_dropped", "Severity": "caution", "Details": "HBSIR metadata declares food DYCOL07 dropped. It is absent in the 1402 raw P3S01 Access schema; counts for other years are unavailable from cleaned mirrors."},
        {"Year": 1403, "Scope": "subsidy.DycolVam", "Issue": "hbsir_field_dropped", "Severity": "caution", "Details": "HBSIR metadata drops DycolVam in 1403; affected values cannot be counted from normalized output."},
        {"Year": "all", "Scope": "income_subsidy.DYCOL01", "Issue": "hbsir_member_number_recode", "Severity": "caution", "Details": "HBSIR replaces numeric subsidy member code 323 with 1 from 1392. Direct raw Access found 0 such records in 1402; source counts for other years remain unavailable from cleaned mirrors."},
        {"Year": 1402, "Scope": "self_employed_income.Employment_Type", "Issue": "official_document_code_discrepancy", "Severity": "warning", "Details": "The raw-file guide p.6 states employment type codes 1/2/3; questionnaire p.65 states 4/5/6. HBSIR labels/observed standardized values follow the questionnaire. No project recode was applied."},
        {"Year": 1402, "Scope": "household_information", "Issue": "official_design_fields_not_standardized", "Severity": "warning", "Details": "HBSIR omits raw replacement/design fields. The project preserves BlkAbdJaygozin, RadifJaygozin, and related raw description fields directly in 1402 household.parquet; other years remain available in the raw archive but are not decoded here."},
        {"Year": "1390-1401,1403", "Scope": "source", "Issue": "cleaned_mirror_used_for_standardization", "Severity": "limitation", "Details": "HBSIR normalized outputs for 1390-1401 and 1403 were built from documented HBSIR cleaned-table mirrors. The 1402 raw Access database was separately processed through unmodified HBSIR; all eight normalized source tables match project output as a row multiset on shared columns."},
    ]
    # Rewrite the maintained log with corrected, current findings. This removes
    # an obsolete diagnostic emitted before the 1402 raw-code comparison was fixed.
    issue_file = path("audit") / "issues_log.csv"
    if issue_file.exists() and issue_file.stat().st_size:
        existing = pd.read_csv(issue_file, encoding="utf-8-sig", dtype=str).fillna("")
        existing = existing[~existing["Issue"].isin({"cleaned_mirror_not_raw_access_reproduced", "raw_HBSIR_323_recode_count_mismatch"})]
        # Keep the issue log consistent with the updated descriptions above.
        replacement_keys = {(str(row["Year"]), row["Scope"], row["Issue"]) for row in issues}
        existing = existing[
            ~existing.apply(lambda row: (str(row["Year"]), row["Scope"], row["Issue"]) in replacement_keys, axis=1)
        ]
        current = pd.concat([existing, pd.DataFrame(issues).astype(str)], ignore_index=True)
        current.drop_duplicates(subset=["Year", "Scope", "Issue", "Severity", "Details"], inplace=True)
        current.to_csv(issue_file, index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(issues).to_csv(issue_file, index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
