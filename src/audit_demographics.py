from __future__ import annotations

import numpy as np
import pandas as pd

from common import append_issues, config, path


VAR_SPECS = [
    ("Age", "members", "Age", "DYCOL05", "Members properties", "Age in completed years; no adjustment"),
    ("Sex", "members", "Sex", "DYCOL04", "Members properties", "HBSIR categorical labels: Male/Female"),
    ("Relationship", "members", "Relationship", "DYCOL03", "Members properties", "HBSIR categorical labels for relationship to household head"),
    ("Education level", "members", "Education_Level", "DYCOL08", "Members properties", "HBSIR education coding changes in 1393 and 1397; labels retained"),
    ("Activity status", "members", "Activity_Status", "DYCOL09", "Members properties", "HBSIR categorical labels; definitions follow HBSIR codebook"),
    ("Marital status", "members", "Marital_Status", "DYCOL10", "Members properties", "HBSIR categorical labels"),
    ("Household size", "household", "Household_Size", "Derived from members_properties count by ID", "Household/member tables", "Row count of standardized member records; no household exclusion"),
    ("Urban/rural", "household", "Urban_Rural", "HBSIR administrative classification lookup", "household_information + HBSIR id_information.yaml", "Added from HBSIR external classification metadata"),
    ("Province", "household", "Province", "HBSIR province classification lookup", "household_information + HBSIR id_information.yaml", "Province English and Farsi labels added from HBSIR lookup"),
    ("County", "household", "County", "HBSIR county classification lookup", "household_information + HBSIR id_information.yaml", "County English and Farsi labels added from HBSIR lookup; coding standards change"),
    ("Weight", "household", "Weight", "WEIGHT / HBSIR external weight table", "household_information; hbsir.api.add_weight pre-1396", "Canonical Weight is HBSIR normalized weight; Weight_Raw retained when available"),
]


def value_code_summary(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return ""
    if pd.api.types.is_numeric_dtype(values):
        if values.nunique() <= 30:
            return "; ".join(f"{k}:{v}" for k, v in values.value_counts(dropna=False).sort_index().items())
        return f"numeric_range={values.min()}..{values.max()}; distinct={values.nunique()}"
    counts = values.astype(str).value_counts(dropna=False).sort_index()
    return "; ".join(f"{k}:{v}" for k, v in counts.items())


def main() -> int:
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    demographic_rows = []
    summary_rows = []
    issues = []
    previous_codes: dict[str, set[str]] = {}
    for year in range(start, end + 1):
        base = path("yearly") / str(year)
        hh = pd.read_parquet(base / "household.parquet")
        members = pd.read_parquet(base / "members.parquet")
        food = pd.read_parquet(base / "food.parquet")
        n_sample = int(hh["ID"].nunique())
        hdup_rows = int(hh["ID"].duplicated(keep=False).sum())
        hdup_ids = int(hh.loc[hh["ID"].duplicated(keep=False), "ID"].nunique())
        if hdup_rows:
            issues.append({"Year": year, "Scope": "household.ID", "Issue": "duplicate_household_id_within_year", "Severity": "warning", "Details": f"{hdup_ids} IDs occur in {hdup_rows} rows; no rows were removed."})

        for concept, table_name, column, raw_name, raw_table, note in VAR_SPECS:
            frame = hh if table_name == "household" else members
            present = column in frame.columns
            if not present:
                demographic_rows.append({
                    "Year": year, "Variable": concept, "Present": False, "Raw_Name": raw_name,
                    "Standardized_Name": column, "Source_Table": raw_table, "Data_Type": "",
                    "Coding_or_Values": "", "Missing_Percent": np.nan,
                    "Coding_Change_From_Previous_Year": "missing", "Source_or_Transformation": note,
                })
                issues.append({"Year": year, "Scope": f"{table_name}.{column}", "Issue": "required_demographic_column_missing", "Severity": "warning", "Details": "Column not present in standardized table; no substitute imputed."})
                continue
            series = frame[column]
            code_values = set(series.dropna().astype(str).unique())
            change = "first_year" if concept not in previous_codes else ("changed" if code_values != previous_codes[concept] else "unchanged")
            previous_codes[concept] = code_values
            missing = float(series.isna().mean() * 100) if len(series) else np.nan
            source_note = note
            if concept == "Weight":
                if "Weight_Source" in frame:
                    sources = "; ".join(sorted(frame["Weight_Source"].dropna().astype(str).unique()))
                    source_note += f"; actual source={sources}"
                if "Weight_Raw" in frame:
                    source_note += f"; Weight_Raw nonmissing={int(frame['Weight_Raw'].notna().sum())}/{len(frame)}"
            demographic_rows.append({
                "Year": year,
                "Variable": concept,
                "Present": True,
                "Raw_Name": raw_name,
                "Standardized_Name": column,
                "Source_Table": raw_table,
                "Data_Type": str(series.dtype),
                "Coding_or_Values": value_code_summary(series),
                "Missing_Percent": missing,
                "Coding_Change_From_Previous_Year": change,
                "Source_or_Transformation": source_note,
            })

        def numeric_valid(col: str) -> pd.Series:
            values = pd.to_numeric(food[col], errors="coerce")
            return pd.Series(np.isfinite(values) & values.gt(0), index=food.index)

        amount_valid, price_valid, expenditure_valid = (numeric_valid(k) for k in ["Amount", "Price", "Expenditure"])
        urban = hh.get("Urban_Rural", pd.Series(index=hh.index, dtype="object")).astype("string")
        summary_rows.append({
            "Year": year,
            "Household_Rows": len(hh),
            "Households_Unique_ID": n_sample,
            "Household_ID_Duplicate_Rows": hdup_rows,
            "Household_ID_Duplicate_Count": hdup_ids,
            "Member_Rows": len(members),
            "Food_Rows": len(food),
            "Unique_Food_Codes": food["Commodity_Code"].nunique(dropna=True),
            "Food_Valid_Amount_Records": int(amount_valid.sum()),
            "Food_Valid_Amount_Percent": float(amount_valid.mean() * 100),
            "Food_Valid_Price_Records": int(price_valid.sum()),
            "Food_Valid_Price_Percent": float(price_valid.mean() * 100),
            "Food_Valid_Expenditure_Records": int(expenditure_valid.sum()),
            "Food_Valid_Expenditure_Percent": float(expenditure_valid.mean() * 100),
            "Food_Amount_HBSIR_Backfill_Rows": int(food.get("Amount_Source", pd.Series(dtype=str)).eq("HBSIR_Expenditure_divided_by_Price").sum()),
            "Food_Price_Source_Zero_Rows": int(pd.to_numeric(food.get("Price_Raw"), errors="coerce").eq(0).sum()) if "Price_Raw" in food else 0,
            "Province_Count": hh["Province"].nunique(dropna=True) if "Province" in hh else 0,
            "County_Count": hh["County"].nunique(dropna=True) if "County" in hh else 0,
            "Urban_Households": int(urban.str.contains("urban", case=False, na=False).sum()),
            "Rural_Households": int(urban.str.contains("rural", case=False, na=False).sum()),
            "Unclassified_Urban_Rural": int(urban.isna().sum()),
            "Household_Weight_Nonmissing": int(pd.to_numeric(hh.get("Weight"), errors="coerce").notna().sum()) if "Weight" in hh else 0,
            "Household_Weight_Source": "; ".join(sorted(hh.get("Weight_Source", pd.Series(dtype=str)).dropna().astype(str).unique())),
        })

    out = path("audit")
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(demographic_rows).to_csv(out / "demographic_variable_audit.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(summary_rows).to_csv(out / "yearly_sample_summary.csv", index=False, encoding="utf-8-sig")
    append_issues(issues)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
