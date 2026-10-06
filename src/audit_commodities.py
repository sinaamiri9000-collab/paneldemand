from __future__ import annotations

import numpy as np
import pandas as pd

from common import append_issues, config, path


PURCHASE_METHODS = {"Purchase", "Purchase_Free_Price", "Purchase_Subsidised_Price"}


def valid_positive(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.isfinite(numeric) & numeric.gt(0), index=series.index)


def main() -> int:
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    annual: list[pd.DataFrame] = []
    issues: list[dict] = []
    label_metadata: dict[str, dict[str, set[str]]] = {}

    for year in range(start, end + 1):
        food = pd.read_parquet(path("yearly") / str(year) / "food.parquet")
        hh = pd.read_parquet(path("yearly") / str(year) / "household.parquet", columns=["ID", "Weight"])
        n_sample = int(hh["ID"].nunique())
        if food["Commodity_Code"].isna().any():
            issues.append({"Year": year, "Scope": "food.Commodity_Code", "Issue": "missing_commodity_code", "Severity": "warning", "Details": f"{int(food['Commodity_Code'].isna().sum())} food rows lack a commodity code; rows retained."})
        food["__method"] = food["Provision_Method"].astype("string")
        for col in ["Amount", "Price", "Expenditure"]:
            food[f"__valid_{col}"] = valid_positive(food[col])
        food["__purchase"] = food["__method"].isin(PURCHASE_METHODS)
        weighted = hh[["ID", "Weight"]].copy()
        weighted["Weight"] = pd.to_numeric(weighted["Weight"], errors="coerce")
        weighted = weighted.drop_duplicates("ID", keep="first").set_index("ID")["Weight"]
        weighted.index = weighted.index.astype("uint64").astype(str)

        grouped = []
        for code, group in food.groupby("Commodity_Code", dropna=False, observed=True, sort=True):
            def unique_value(column: str):
                if column not in group:
                    return ""
                vals = group[column].dropna().astype(str).drop_duplicates().tolist()
                return vals[0] if vals else ""

            record_count = len(group)
            ids = group["ID"].dropna().astype("uint64").astype(str)
            purchaser_ids = group.loc[group["__purchase"], "ID"].dropna().astype("uint64").astype(str).unique()
            values = {
                "Year": year,
                "Commodity_Code": code,
                "Commodity_Name": unique_value("Commodity_Name"),
                "HBSIR_Category_Level_1": unique_value("HBSIR_Category_Level_1"),
                "HBSIR_Category_Level_2": unique_value("HBSIR_Category_Level_2"),
                "HBSIR_Category_Level_3": unique_value("HBSIR_Category_Level_3"),
                "Number_of_Households": n_sample,
                "Households_With_Commodity_Record": int(ids.nunique()),
                "Number_of_Purchasing_Households": int(len(purchaser_ids)),
                "Purchase_Rate": len(purchaser_ids) / n_sample if n_sample else np.nan,
                "Number_of_Records": record_count,
            }
            for field, source in [("Amount", "Amount"), ("Price", "Price"), ("Expenditure", "Expenditure")]:
                valid = group[f"__valid_{source}"]
                values[f"Number_With_Valid_{field}"] = int(valid.sum())
                values[f"Share_With_Valid_{field}"] = float(valid.mean()) if record_count else np.nan
                household_valid = group.loc[valid, "ID"].dropna().nunique()
                values[f"Households_With_Valid_{field}"] = int(household_valid)
                values[f"Household_Share_With_Valid_{field}"] = household_valid / n_sample if n_sample else np.nan
                numeric = pd.to_numeric(group.loc[valid, source], errors="coerce")
                values[f"Median_{field}"] = float(numeric.median()) if len(numeric) else np.nan
            weights_present = weighted.reindex(purchaser_ids).dropna()
            denom_weights = weighted.dropna()
            denom_weights = denom_weights[np.isfinite(denom_weights) & denom_weights.gt(0)]
            values["Purchase_Rate_Weighted"] = (
                float(weights_present[weights_present.gt(0)].sum() / denom_weights.sum())
                if len(denom_weights) and denom_weights.sum() > 0
                else np.nan
            )
            values["Number_HBSIR_Amount_Backfilled"] = int(group["Amount_Source"].eq("HBSIR_Expenditure_divided_by_Price").sum())
            values["Share_HBSIR_Amount_Backfilled"] = values["Number_HBSIR_Amount_Backfilled"] / record_count if record_count else np.nan
            values["Records_Price_Raw_Zero"] = int(pd.to_numeric(group.get("Price_Raw"), errors="coerce").eq(0).sum()) if "Price_Raw" in group else 0
            values["Records_Price_Raw_Negative"] = int(pd.to_numeric(group.get("Price_Raw"), errors="coerce").lt(0).sum()) if "Price_Raw" in group else 0
            grouped.append(values)
            code_key = str(code)
            info = label_metadata.setdefault(code_key, {"name": set(), "level1": set(), "level2": set(), "level3": set(), "years": set()})
            for target, source in [("name", "Commodity_Name"), ("level1", "HBSIR_Category_Level_1"), ("level2", "HBSIR_Category_Level_2"), ("level3", "HBSIR_Category_Level_3")]:
                info[target].update(group[source].dropna().astype(str).unique())
            info["years"].add(str(year))
        annual.append(pd.DataFrame(grouped))

        price_zeros = int(pd.to_numeric(food.get("Price_Raw"), errors="coerce").eq(0).sum()) if "Price_Raw" in food else 0
        price_negative = int(pd.to_numeric(food.get("Price_Raw"), errors="coerce").lt(0).sum()) if "Price_Raw" in food else 0
        if price_zeros or price_negative:
            details = f"{price_zeros} Price_Raw values are zero and {price_negative} are negative in the HBSIR cleaned-source table; these are not asserted to be unprocessed official-source values. The 1402 normalized Price column was also checked against direct Access extraction."
            issues.append({"Year": year, "Scope": "food.Price", "Issue": "zero_or_negative_price_in_hbsir_cleaned_source", "Severity": "warning", "Details": details})

    combined = pd.concat(annual, ignore_index=True)
    for idx, row in combined.iterrows():
        info = label_metadata[str(row["Commodity_Code"])]
        combined.loc[idx, "First_Year_Observed"] = min(map(int, info["years"]))
        combined.loc[idx, "Last_Year_Observed"] = max(map(int, info["years"]))
        combined.loc[idx, "Years_Observed"] = ";".join(sorted(info["years"], key=int))
        combined.loc[idx, "Commodity_Name_Changes_In_Period"] = len(info["name"])
        combined.loc[idx, "Commodity_Name_Changed_In_Period"] = len(info["name"]) > 1
        combined.loc[idx, "HBSIR_Category_Changed_In_Period"] = any(len(info[k]) > 1 for k in ["level1", "level2", "level3"])
        combined.loc[idx, "HBSIR_Year_Specific_Mapping"] = combined.loc[idx, "HBSIR_Category_Changed_In_Period"] or combined.loc[idx, "Commodity_Name_Changed_In_Period"]

    out_dir = path("audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_dir / "commodity_year_audit.parquet", index=False)
    dictionary_rows = []
    for code, info in label_metadata.items():
        dictionary_rows.append({
            "Commodity_Code": code,
            "Years_Observed": ";".join(sorted(info["years"], key=int)),
            "First_Year_Observed": min(map(int, info["years"])),
            "Last_Year_Observed": max(map(int, info["years"])),
            "Commodity_Names": " | ".join(sorted(info["name"])),
            "HBSIR_Category_Level_1_Values": " | ".join(sorted(info["level1"])),
            "HBSIR_Category_Level_2_Values": " | ".join(sorted(info["level2"])),
            "HBSIR_Category_Level_3_Values": " | ".join(sorted(info["level3"])),
            "Name_Changed": len(info["name"]) > 1,
            "HBSIR_Category_Changed": any(len(info[k]) > 1 for k in ["level1", "level2", "level3"]),
        })
    pd.DataFrame(dictionary_rows).to_csv(path("metadata") / "commodity_dictionary.csv", index=False, encoding="utf-8-sig")
    append_issues(issues)
    print(f"commodity-year rows={len(combined)}, unique codes={len(label_metadata)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
