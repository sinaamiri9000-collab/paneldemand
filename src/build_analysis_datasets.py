"""Build the 1392–1403 demand-analysis base files without estimating a model.

The script uses exact raw Access Address values for matching to HBSIR IDs,
scopes panel IDs to the audited design frame, and keeps source food records
long. No final commodity grouping or price index is created.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
YEARS = list(range(1392, 1404))
PRIVATE = ROOT / "intermediate/three_wave_validation/private"
OUT = ROOT / "combined"
AUDIT = ROOT / "audit"
META = ROOT / "metadata"
PURCHASE_METHODS = {"Purchase", "Purchase_Free_Price", "Purchase_Subsidised_Price"}
PANEL_B_BENCHMARK = 46_347
PANEL_B_HH_YEAR_BENCHMARK = PANEL_B_BENCHMARK * 3
OLD_MAPPING_SOURCE = META / "old_article_mapping_source.csv"


def frame_for_year(year: int) -> str:
    if 1392 <= year <= 1396:
        return "Frame_1392_1396"
    if 1397 <= year <= 1403:
        return "Frame_1397_1403"
    raise ValueError(f"year outside analysis window: {year}")


def clean_text(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    return text if text else pd.NA


def clean_code_series(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip()
    text = text.mask(text.eq(""))
    numeric = pd.to_numeric(text, errors="coerce")
    numeric_mask = numeric.notna()
    out = text.copy()
    out.loc[numeric_mask] = numeric.loc[numeric_mask].astype("Int64").astype("string").str.zfill(5)
    return out


def number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("float64")


def status_kind(takmil: Any, jaygozin: Any) -> str:
    t, j = clean_text(takmil), clean_text(jaygozin)
    t = None if pd.isna(t) else str(t)
    j = None if pd.isna(j) else str(j)
    if t == "1" and j == "1":
        return "Conflicting_Original_and_Substitute_Yes"
    if t == "1":
        return "Original"
    if j == "1":
        return "Substitute"
    if t == "2" and j == "2":
        return "No_Completed_Interview"
    if t == "2":
        return "Original_Nonresponse"
    return "Ambiguous_or_Missing"


def load_candidate_keys() -> pd.DataFrame:
    candidate = pd.read_parquet(AUDIT / "panel_candidates_1392_1403.parquet")
    if int(candidate["Sample_B"].fillna(False).sum()) != PANEL_B_BENCHMARK:
        raise AssertionError("Panel B count differs from the audited 46,347 candidate benchmark")
    pieces = []
    for wave in (1, 2, 3):
        year_col = f"Year_{wave}"
        piece = candidate[
            ["Panel_ID", "Address", "Frame", "Cohort", "Sample_B", "Sample_Level_1", "Sample_Level_2", year_col]
        ].copy()
        piece = piece.rename(columns={"Panel_ID": "panel_id", "Address": "address_raw", year_col: "year"})
        piece["wave"] = wave
        piece["address_raw"] = piece["address_raw"].astype("string")
        piece["year"] = pd.to_numeric(piece["year"], errors="raise").astype("int16")
        piece["panel_B"] = piece["Sample_B"].fillna(False).astype(bool).astype("int8")
        piece["panel_level1"] = piece["Sample_Level_1"].fillna(False).astype(bool).astype("int8")
        piece["panel_level2"] = piece["Sample_Level_2"].fillna(False).astype(bool).astype("int8")
        piece["cohort"] = piece["Cohort"].astype("string").where(piece["panel_B"].eq(1), pd.NA)
        piece["wave"] = piece["wave"].astype("int8").where(piece["panel_B"].eq(1), pd.NA)
        piece = piece[["address_raw", "year", "Frame", "panel_id", "cohort", "wave", "panel_B", "panel_level1", "panel_level2"]]
        piece = piece.rename(columns={"Frame": "frame"})
        if not piece["panel_id"].astype("string").eq(piece["frame"].astype("string") + ":" + piece["address_raw"]).all():
            raise AssertionError("candidate panel_id is not design frame + exact raw Address")
        pieces.append(piece)
    keys = pd.concat(pieces, ignore_index=True)
    key_cols = ["frame", "address_raw", "year"]
    dup = keys.duplicated(key_cols, keep=False)
    if dup.any():
        raise AssertionError(f"candidate frame/address/year has {int(dup.sum())} duplicate rows")
    panel = keys[keys.panel_B.eq(1)]
    waves = panel.groupby("panel_id")["year"].agg(["nunique", "size"])
    if not waves["nunique"].eq(3).all() or not waves["size"].eq(3).all():
        raise AssertionError("each Panel B panel_id must have exactly three distinct household-years")
    if panel["panel_id"].nunique() != PANEL_B_BENCHMARK or len(panel) != PANEL_B_HH_YEAR_BENCHMARK:
        raise AssertionError("Panel B does not reproduce the expected household and household-year counts")
    return keys


def make_head_table(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    members = pd.read_parquet(ROOT / "yearly" / str(year) / "members.parquet")
    members = members.copy()
    members["address_raw"] = members["ID"].astype("string")
    rel = members["Relationship"].astype("string").str.strip()
    head_rows = members[rel.eq("Head")].copy()
    head_n = head_rows.groupby("address_raw", dropna=False).size().rename("head_member_rows").reset_index()
    member_n = members.groupby("address_raw", dropna=False).size().rename("n_members_file").reset_index()
    head_one = head_rows.merge(head_n, on="address_raw", how="left", validate="many_to_one")
    head_one = head_one[head_one["head_member_rows"].eq(1)].copy()
    take = {
        "Member_Number": "head_member_number",
        "Relationship": "head_relationship",
        "Age": "head_age",
        "Sex": "head_sex",
        "Education_Level": "head_education",
        "Is_Literate": "head_is_literate",
        "Is_Student": "head_is_student",
        "Marital_Status": "head_marital_status",
        "Activity_Status": "head_activity_status",
    }
    head_one = head_one[["address_raw", *[c for c in take if c in head_one.columns]]].rename(columns=take)
    counts = head_n.merge(member_n, on="address_raw", how="outer", validate="one_to_one")
    return head_one, counts


def load_household_years(candidate_keys: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual_records: list[pd.DataFrame] = []
    flow: list[dict[str, Any]] = []
    candidate_keys = candidate_keys.copy()
    for year in YEARS:
        raw = pd.read_parquet(PRIVATE / f"raw_household_{year}.parquet").copy()
        if "Address_Raw" not in raw:
            raise KeyError(f"raw Access household file has no Address_Raw for {year}")
        access_weight_columns = [c for c in raw.columns if str(c).casefold() == "weight"]
        if len(access_weight_columns) > 1:
            raise ValueError(f"ambiguous raw Access weight columns in {year}: {access_weight_columns}")
        if access_weight_columns:
            raw = raw.rename(columns={access_weight_columns[0]: "access_weight_raw"})
        else:
            raw["access_weight_raw"] = pd.NA
        raw["address_raw"] = raw["Address_Raw"].astype("string")
        if raw["address_raw"].isna().any() or raw["address_raw"].duplicated().any():
            raise AssertionError(f"raw Address is missing or nonunique in {year}")
        raw["year"] = year
        raw["frame"] = frame_for_year(year)
        raw["panel_id"] = raw["frame"].astype("string") + ":" + raw["address_raw"]
        raw["takmil"] = raw["Takmil"].map(clean_text) if "Takmil" in raw else pd.NA
        raw["jaygozin"] = raw["Jaygozin"].map(clean_text) if "Jaygozin" in raw else pd.NA
        t = raw["takmil"].astype("string")
        j = raw["jaygozin"].astype("string")
        raw["completed_interview"] = (t.eq("1") | j.eq("1")).fillna(False).astype("int8")
        raw["respondent_kind"] = [status_kind(a, b) for a, b in zip(raw["takmil"], raw["jaygozin"])]
        raw["raw_table_name"] = raw["Raw_Table"].astype("string") if "Raw_Table" in raw else pd.NA
        raw["urban_rural_raw_table"] = np.where(raw["raw_table_name"].astype("string").str.startswith("U"), "Urban", "Rural")
        raw["mah_morajeh_raw"] = raw["MahMorajeh"].map(clean_text) if "MahMorajeh" in raw else pd.NA
        raw["fasl_raw"] = raw["Fasl"].map(clean_text) if "Fasl" in raw else pd.NA

        hhs = pd.read_parquet(ROOT / "yearly" / str(year) / "household.parquet").copy()
        hhs["address_raw"] = hhs["ID"].astype("string")
        selected = {
            "Month": "interview_month",
            "Season_Number": "season_number",
            "Season": "season",
            "Weight": "weight",
            "Weight_Raw": "weight_raw",
            "Weight_Source": "weight_source",
            "Household_Type": "household_type",
            "Main_Household": "main_household_hbsir",
            "Alternative_Household": "alternative_household_hbsir",
            "Urban_Rural": "urban_rural",
            "Province": "province",
            "Province_Farsi": "province_farsi",
            "County": "county",
            "County_Farsi": "county_farsi",
            "Household_Size": "household_size",
        }
        cols = ["address_raw", *[c for c in selected if c in hhs.columns]]
        hhs = hhs[cols].rename(columns=selected)
        if hhs["address_raw"].duplicated().any():
            raise AssertionError(f"HBSIR household ID is nonunique in {year}")
        raw = raw.merge(hhs, on="address_raw", how="left", validate="one_to_one", indicator="_household_merge")
        raw["household_table_matched"] = raw["_household_merge"].eq("both").astype("int8")
        raw = raw.drop(columns="_household_merge")
        access_weight = number(raw.get("access_weight_raw", pd.Series(np.nan, index=raw.index)))
        hbsir_weight = number(raw.get("weight", pd.Series(np.nan, index=raw.index)))
        both_weights = access_weight.notna() & hbsir_weight.notna()
        raw["access_weight_match_check"] = pd.Series(pd.NA, index=raw.index, dtype="Int8")
        raw.loc[both_weights, "access_weight_match_check"] = np.isclose(
            access_weight[both_weights], hbsir_weight[both_weights], rtol=1e-10, atol=1e-12
        ).astype("int8")
        if "panel_id_candidate" in raw and not raw.loc[raw["panel_id_candidate"].notna(), "panel_id_candidate"].astype("string").eq(
            raw.loc[raw["panel_id_candidate"].notna(), "panel_id"].astype("string")
        ).all():
            raise AssertionError(f"candidate panel_id does not equal frame + Address in {year}")
        raw["urban_rural_match_check"] = (
            raw["urban_rural"].astype("string").eq(raw["urban_rural_raw_table"].astype("string"))
        ).fillna(False).astype("int8")

        head, counts = make_head_table(year)
        raw = raw.merge(head, on="address_raw", how="left", validate="one_to_one")
        raw = raw.merge(counts, on="address_raw", how="left", validate="one_to_one")
        raw["head_demographics_matched"] = raw["head_member_rows"].eq(1).fillna(False).astype("int8")
        raw["member_table_matched"] = raw["n_members_file"].notna().astype("int8")

        food_ids = pd.read_parquet(ROOT / "yearly" / str(year) / "food.parquet", columns=["ID"])["ID"].astype("string").dropna().unique()
        raw["food_matched"] = raw["address_raw"].isin(set(food_ids)).astype("int8")

        ckey = candidate_keys[candidate_keys["year"].eq(year)].drop(columns="year")
        raw = raw.merge(ckey, on=["address_raw", "frame"], how="left", validate="one_to_one", suffixes=("", "_candidate"))
        for col in ("panel_B", "panel_level1", "panel_level2"):
            raw[col] = pd.to_numeric(raw[col], errors="coerce").fillna(0).astype("int8")
        raw["cohort"] = raw["cohort"].astype("string").where(raw["panel_B"].eq(1), pd.NA)
        raw["wave"] = pd.to_numeric(raw["wave"], errors="coerce").astype("Int8")
        raw["wave"] = raw["wave"].where(raw["panel_B"].eq(1), pd.NA)
        raw["n_food_rows"] = pd.NA
        raw["food_exp_observed_total"] = np.nan
        raw["n_food_items_positive"] = pd.NA
        raw["n_food_items_purchased"] = pd.NA
        raw["n_food_rows_uncoded"] = pd.NA
        raw["food_exp_uncoded"] = np.nan

        n_raw = len(raw)
        n_complete = int(raw["completed_interview"].sum())
        n_hh = int((raw["completed_interview"].eq(1) & raw["household_table_matched"].eq(1)).sum())
        n_demo = int((raw["completed_interview"].eq(1) & raw["household_table_matched"].eq(1) & raw["head_demographics_matched"].eq(1)).sum())
        n_food = int((raw["completed_interview"].eq(1) & raw["household_table_matched"].eq(1) & raw["food_matched"].eq(1)).sum())
        b = raw[raw["panel_B"].eq(1)]
        if len(b) and not b["takmil"].astype("string").eq("1").all():
            raise AssertionError(f"Panel B contains Takmil != 1 in year {year}")
        flow.extend([
            {"sample": "All_Cross_Section", "year": year, "stage": "raw_access_households", "role": "sequence", "n_household_year": n_raw, "n_lost_from_previous_stage": pd.NA, "notes": "Direct Access household rows before completion filter."},
            {"sample": "All_Cross_Section", "year": year, "stage": "completed_interview", "role": "sequence", "n_household_year": n_complete, "n_lost_from_previous_stage": n_raw - n_complete, "notes": "Takmil=1 or Jaygozin=1; exact affirmative codes only."},
            {"sample": "All_Cross_Section", "year": year, "stage": "standardized_household_table_matched", "role": "sequence", "n_household_year": n_hh, "n_lost_from_previous_stage": n_complete - n_hh, "notes": "Matched by exact Address string to HBSIR ID; no geographic approximation."},
            {"sample": "All_Cross_Section", "year": year, "stage": "head_demographics_matched", "role": "diagnostic_not_filter", "n_household_year": n_demo, "n_lost_from_previous_stage": pd.NA, "notes": "Exactly one HBSIR members_properties row with Relationship=Head; missing head fields are retained."},
            {"sample": "All_Cross_Section", "year": year, "stage": "food_table_matched", "role": "sequence", "n_household_year": n_food, "n_lost_from_previous_stage": n_hh - n_food, "notes": "At least one HBSIR food row; valid amount is not required if expenditure/other fields are usable."},
            {"sample": "All_Cross_Section", "year": year, "stage": "final_household_year_all", "role": "final", "n_household_year": n_food, "n_lost_from_previous_stage": 0, "notes": "Completed + household table + at least one food-table row."},
            {"sample": "Panel_B", "year": year, "stage": "panel_B_identified", "role": "sequence", "n_household_year": len(b), "n_lost_from_previous_stage": pd.NA, "notes": "Audited raw Address, three-wave cohort, all Takmil=1; 1396/1397 boundary is not linked."},
            {"sample": "Panel_B", "year": year, "stage": "raw_access_and_status_matched", "role": "sequence", "n_household_year": int(b["completed_interview"].eq(1).sum()), "n_lost_from_previous_stage": len(b) - int(b["completed_interview"].eq(1).sum()), "notes": "Must equal identified Panel B; retained as a failure diagnostic."},
            {"sample": "Panel_B", "year": year, "stage": "standardized_household_table_matched", "role": "sequence", "n_household_year": int(b["household_table_matched"].sum()), "n_lost_from_previous_stage": len(b) - int(b["household_table_matched"].sum()), "notes": "Matched by exact Address string to HBSIR ID."},
            {"sample": "Panel_B", "year": year, "stage": "head_demographics_matched", "role": "diagnostic_not_filter", "n_household_year": int(b["head_demographics_matched"].sum()), "n_lost_from_previous_stage": pd.NA, "notes": "Exactly one head record; observations with missing head data remain in Panel B file."},
            {"sample": "Panel_B", "year": year, "stage": "food_table_matched", "role": "sequence", "n_household_year": int(b["food_matched"].sum()), "n_lost_from_previous_stage": len(b) - int(b["food_matched"].sum()), "notes": "Food-usable Panel B household-years used for item audits and future common comparison."},
            {"sample": "Panel_B", "year": year, "stage": "final_household_year_panelB", "role": "final", "n_household_year": len(b), "n_lost_from_previous_stage": 0, "notes": "All identified Panel B rows are preserved; food_matched=0 rows are not assigned zero expenditure."},
        ])
        annual_records.append(raw)
        print(f"loaded household year {year}: raw={n_raw:,} complete={n_complete:,} all_food_matched={n_food:,} panelB={len(b):,}", flush=True)

    records = pd.concat(annual_records, ignore_index=True, sort=False)
    records["year"] = pd.to_numeric(records["year"], errors="raise").astype("int16")
    expected = candidate_keys[candidate_keys.panel_B.eq(1)][["frame", "address_raw", "year"]]
    observed = records[records.panel_B.eq(1)][["frame", "address_raw", "year"]]
    missing = expected.merge(observed, on=["frame", "address_raw", "year"], how="left", indicator=True)
    if missing["_merge"].ne("both").any():
        raise AssertionError(f"{int(missing['_merge'].ne('both').sum())} Panel B candidate household-years did not match raw Access")
    panel_ids = records[records.panel_B.eq(1)].groupby("panel_id")["year"].nunique()
    if len(panel_ids) != PANEL_B_BENCHMARK or not panel_ids.eq(3).all():
        raise AssertionError("Panel B household-year file must contain 46,347 IDs with exactly three years each")
    return records, pd.DataFrame(flow)


def household_food_metrics(food: pd.DataFrame) -> pd.DataFrame:
    if food.empty:
        return pd.DataFrame(columns=["address_raw", "n_food_rows", "food_exp_observed_total", "n_food_items_positive", "n_food_items_purchased", "n_food_rows_uncoded", "food_exp_uncoded"])
    f = food.copy()
    f["expenditure_raw"] = number(f["Expenditure"])
    f["commodity_code"] = clean_code_series(f["Commodity_Code"])
    f["provision_method"] = f["Provision_Method"].astype("string").str.strip()
    f["is_purchase"] = f["provision_method"].isin(PURCHASE_METHODS)
    total = f.groupby("address_raw", sort=False)["expenditure_raw"].sum(min_count=1).rename("food_exp_observed_total")
    row_count = f.groupby("address_raw", sort=False).size().rename("n_food_rows")
    uncoded = f[f["commodity_code"].isna()]
    uncoded_count = uncoded.groupby("address_raw", sort=False).size().rename("n_food_rows_uncoded")
    uncoded_exp = uncoded.groupby("address_raw", sort=False)["expenditure_raw"].sum(min_count=1).rename("food_exp_uncoded")
    coded = f[f["commodity_code"].notna()].copy()
    coded_exp = coded.groupby(["address_raw", "commodity_code"], sort=False)["expenditure_raw"].sum(min_count=1)
    positive = coded_exp[coded_exp.gt(0)].reset_index().groupby("address_raw").size().rename("n_food_items_positive")
    purchase = coded[coded["is_purchase"]]
    purchase_exp = purchase.groupby(["address_raw", "commodity_code"], sort=False)["expenditure_raw"].sum(min_count=1)
    bought = purchase_exp[purchase_exp.gt(0)].reset_index().groupby("address_raw").size().rename("n_food_items_purchased")
    result = pd.concat([total, row_count, uncoded_count, uncoded_exp, positive, bought], axis=1).reset_index()
    for col in ("n_food_items_positive", "n_food_items_purchased", "n_food_rows_uncoded"):
        result[col] = result[col].fillna(0).astype("int32")
    return result


def make_food_long(food: pd.DataFrame, sample_keys: pd.DataFrame, year: int) -> pd.DataFrame:
    f = food.copy()
    f["source_record_number"] = np.arange(1, len(f) + 1, dtype="int32")
    f["address_raw"] = f["ID"].astype("string")
    keys = sample_keys[
        ["address_raw", "panel_id", "frame", "cohort", "wave", "panel_B", "urban_rural", "province", "weight"]
    ].drop_duplicates("address_raw")
    f = f.merge(keys, on="address_raw", how="inner", validate="many_to_one")
    f["year"] = np.int16(year)
    f["commodity_code"] = clean_code_series(f["Commodity_Code"])
    f["commodity_name"] = f.get("Commodity_Name", pd.Series(pd.NA, index=f.index)).astype("string")
    f["provision_method"] = f["Provision_Method"].astype("string").str.strip()
    f["kilos_raw"] = number(f.get("Kilos_Raw", pd.Series(np.nan, index=f.index)))
    f["grams_raw"] = number(f.get("Grams_Raw", pd.Series(np.nan, index=f.index)))
    raw_mass_present = f["kilos_raw"].notna() | f["grams_raw"].notna()
    f["amount_raw"] = f["kilos_raw"].fillna(0).mul(1000).add(f["grams_raw"].fillna(0)).where(raw_mass_present, np.nan)
    f["amount_raw_unit"] = pd.Series("g_equivalent", index=f.index, dtype="string").where(raw_mass_present, pd.NA)
    f["amount_standardized"] = number(f.get("Amount", pd.Series(np.nan, index=f.index)))
    f["price_raw"] = number(f.get("Price_Raw", pd.Series(np.nan, index=f.index)))
    f["price_hbsir"] = number(f.get("Price", pd.Series(np.nan, index=f.index)))
    f["expenditure_raw"] = number(f.get("Expenditure", pd.Series(np.nan, index=f.index)))
    f["unit_value"] = f["price_raw"].where(np.isfinite(f["price_raw"]) & f["price_raw"].gt(0), np.nan)
    f["amount_source"] = f.get("Amount_Source", pd.Series(pd.NA, index=f.index)).astype("string")
    f["price_source"] = f.get("Price_Source", pd.Series(pd.NA, index=f.index)).astype("string")
    f["amount_fallback_flag"] = f["amount_source"].eq("HBSIR_Expenditure_divided_by_Price").astype("int8")
    f["amount_invalid_flag"] = (~np.isfinite(f["amount_standardized"]) | f["amount_standardized"].le(0)).astype("int8")
    f["price_zero_flag"] = f["price_raw"].eq(0).fillna(False).astype("int8")
    f["price_negative_flag"] = f["price_raw"].lt(0).fillna(False).astype("int8")
    f["price_invalid_flag"] = (~np.isfinite(f["price_raw"]) | f["price_raw"].le(0)).astype("int8")
    f["price_normalization_changed_flag"] = (f["price_raw"].notna() & f["price_hbsir"].isna()).astype("int8")
    f["expenditure_invalid_flag"] = (~np.isfinite(f["expenditure_raw"]) | f["expenditure_raw"].lt(0)).astype("int8")
    f["purchase_method_flag"] = f["provision_method"].isin(PURCHASE_METHODS).astype("int8")
    f["nonmarket_acquisition_flag"] = (~f["provision_method"].isin(PURCHASE_METHODS) & f["provision_method"].notna()).astype("int8")
    f["provision_method_missing_flag"] = f["provision_method"].isna().astype("int8")
    f["price_unit_definition"] = "HBSIR cleaned-source survey price field; raw field retained; no group price/index"
    keep = [
        "source_record_number", "address_raw", "panel_id", "year", "frame", "cohort", "wave", "panel_B",
        "commodity_code", "commodity_name", "provision_method", "amount_raw", "amount_raw_unit",
        "kilos_raw", "grams_raw", "amount_standardized", "price_raw", "price_hbsir", "unit_value",
        "expenditure_raw", "urban_rural", "province", "weight", "amount_source", "price_source",
        "amount_fallback_flag", "amount_invalid_flag", "price_zero_flag", "price_negative_flag",
        "price_invalid_flag", "price_normalization_changed_flag", "expenditure_invalid_flag",
        "purchase_method_flag", "nonmarket_acquisition_flag", "provision_method_missing_flag", "price_unit_definition",
    ]
    out = f[keep].copy()
    out["year"] = out["year"].astype("int16")
    for col in ("panel_B", "amount_fallback_flag", "amount_invalid_flag", "price_zero_flag", "price_negative_flag", "price_invalid_flag", "price_normalization_changed_flag", "expenditure_invalid_flag", "purchase_method_flag", "nonmarket_acquisition_flag", "provision_method_missing_flag"):
        out[col] = out[col].fillna(0).astype("int8")
    for col in ("amount_raw", "kilos_raw", "grams_raw", "amount_standardized", "price_raw", "price_hbsir", "unit_value", "expenditure_raw", "weight"):
        out[col] = number(out[col])
    return out


def aggregate_item_household(food: pd.DataFrame) -> pd.DataFrame:
    """Aggregate source food records to household-year-code for itemwide output.

    Expenditure and standardized amount are summed within commodity across all
    provision methods. The raw unit-price field is retained per source row;
    wide uv is purchase-only, using quantity-weighting when needed.
    """
    f = food.copy()
    f["commodity_code"] = clean_code_series(f["Commodity_Code"])
    f = f[f["commodity_code"].notna()].copy()
    if f.empty:
        return pd.DataFrame(columns=["address_raw", "commodity_code", "n_records", "expenditure_all", "expenditure_purchase", "quantity_all", "unit_value_purchase", "buy"])
    f["expenditure"] = number(f["Expenditure"])
    f["quantity"] = number(f["Amount"])
    f["price"] = number(f["Price_Raw"])
    f["method"] = f["Provision_Method"].astype("string").str.strip()
    f["purchase"] = f["method"].isin(PURCHASE_METHODS)
    keys = ["address_raw", "commodity_code"]
    all_exp = f.groupby(keys, sort=False)["expenditure"].sum(min_count=1).rename("expenditure_all")
    all_q = f.groupby(keys, sort=False)["quantity"].sum(min_count=1).rename("quantity_all")
    n_records = f.groupby(keys, sort=False).size().rename("n_records")
    p = f[f["purchase"]]
    if len(p):
        p_exp = p.groupby(keys, sort=False)["expenditure"].sum(min_count=1).rename("expenditure_purchase")
        p_count = p.groupby(keys, sort=False).size().rename("n_purchase_records")
        p_qvalid = p[np.isfinite(p["quantity"]) & p["quantity"].gt(0)].groupby(keys, sort=False).size().rename("n_purchase_quantity_valid_records")
    else:
        p_exp = pd.Series(dtype="float64", name="expenditure_purchase")
        p_count = pd.Series(dtype="int64", name="n_purchase_records")
        p_qvalid = pd.Series(dtype="int64", name="n_purchase_quantity_valid_records")
    result = pd.concat([all_exp, all_q, n_records, p_exp, p_count, p_qvalid], axis=1).reset_index()
    no_purchase_rows = result["n_purchase_records"].isna()
    result.loc[no_purchase_rows, "expenditure_purchase"] = 0.0
    result["n_purchase_records"] = result["n_purchase_records"].fillna(0).astype("int32")
    result["n_purchase_quantity_valid_records"] = result["n_purchase_quantity_valid_records"].fillna(0).astype("int32")
    result["buy"] = (np.isfinite(result["expenditure_purchase"]) & result["expenditure_purchase"].gt(0)).astype("int8")

    pgood = p[np.isfinite(p["price"]) & p["price"].gt(0)].copy()
    if len(pgood):
        pgood["weighted_value"] = np.where(np.isfinite(pgood["quantity"]) & pgood["quantity"].gt(0), pgood["price"] * pgood["quantity"], np.nan)
        pgood["weight_quantity"] = np.where(np.isfinite(pgood["quantity"]) & pgood["quantity"].gt(0), pgood["quantity"], np.nan)
        price_stats = pgood.groupby(keys, sort=False).agg(
            n_valid_price_records=("price", "size"),
            n_unique_valid_prices=("price", "nunique"),
            single_price=("price", "first"),
        )
        weighted = pgood.groupby(keys, sort=False).agg(
            weighted_value_sum=("weighted_value", "sum"),
            weighted_quantity_sum=("weight_quantity", "sum"),
            n_weighted_price_records=("weight_quantity", "count"),
        )
        price_stats = price_stats.join(weighted)
        uv = pd.Series(np.nan, index=price_stats.index, dtype="float64")
        single = price_stats["n_valid_price_records"].eq(1) | price_stats["n_unique_valid_prices"].eq(1)
        uv.loc[single] = price_stats.loc[single, "single_price"]
        weighted_ok = (
            ~single
            & price_stats["n_weighted_price_records"].eq(price_stats["n_valid_price_records"])
            & price_stats["weighted_quantity_sum"].gt(0)
        )
        uv.loc[weighted_ok] = price_stats.loc[weighted_ok, "weighted_value_sum"] / price_stats.loc[weighted_ok, "weighted_quantity_sum"]
        result = result.merge(uv.rename("unit_value_purchase").reset_index(), on=keys, how="left", validate="one_to_one")
        result = result.merge(price_stats[["n_valid_price_records"]].reset_index(), on=keys, how="left", validate="one_to_one")
    else:
        result["unit_value_purchase"] = np.nan
        result["n_valid_price_records"] = 0
    result["n_valid_price_records"] = result["n_valid_price_records"].fillna(0).astype("int32")
    return result


def make_itemwide(households: pd.DataFrame, aggregate: pd.DataFrame, codes_all: list[str], codes_available: set[str]) -> pd.DataFrame:
    core = households.copy()
    index = pd.Index(core["address_raw"].astype("string"), name="address_raw")
    ag = aggregate.copy()
    if len(ag):
        ag = ag.set_index(["address_raw", "commodity_code"])
        if not ag.index.is_unique:
            raise AssertionError("item aggregate must be unique by address and commodity")
    if len(ag):
        presence = ag["n_records"].unstack("commodity_code").reindex(index=index, columns=codes_all).notna()
    else:
        presence = pd.DataFrame(False, index=index, columns=codes_all)
    matched = core["food_matched"].fillna(0).astype(bool).to_numpy()
    wide_result = core.reset_index(drop=True)
    fields = [
        ("expenditure_all", "exp_c", True),
        ("expenditure_purchase", "exp_purchase_c", True),
        ("unit_value_purchase", "uv_c", False),
        ("quantity_all", "q_c", True),
        ("buy", "buy_c", True),
    ]
    for field, prefix, zero_if_absent in fields:
        if len(ag):
            values = ag[field].unstack("commodity_code").reindex(index=index, columns=codes_all)
        else:
            values = pd.DataFrame(np.nan, index=index, columns=codes_all)
        block_columns: dict[str, np.ndarray] = {}
        for code in codes_all:
            col_name = f"{prefix}{code}"
            if code not in codes_available:
                block_columns[col_name] = np.full(len(core), np.nan, dtype="float64")
                continue
            col = values[code].copy()
            if zero_if_absent:
                col.loc[~presence[code]] = 0.0
            col.loc[~matched] = np.nan
            block_columns[col_name] = pd.to_numeric(col, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
        wide_result = pd.concat([wide_result, pd.DataFrame(block_columns)], axis=1)
        del block_columns
        del values
    return wide_result


def item_audit_rows(food: pd.DataFrame, households: pd.DataFrame, codes: list[str], sample_name: str, year: int) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Compute annual audit metrics and return household-code aggregates."""
    use_cols = [c for c in ["ID", "Commodity_Code", "Commodity_Name", "Provision_Method", "Amount", "Price_Raw", "Price", "Expenditure", "Amount_Source", "Price_Source", "Kilos_Raw", "Grams_Raw", "HBSIR_Category_Level_1", "HBSIR_Category_Level_2", "HBSIR_Category_Level_3"] if c in food.columns]
    f = food[use_cols].copy()
    f["address_raw"] = f["ID"].astype("string")
    f["commodity_code"] = clean_code_series(f["Commodity_Code"])
    f["provision_method"] = f["Provision_Method"].astype("string").str.strip()
    f["purchase"] = f["provision_method"].isin(PURCHASE_METHODS)
    f["expenditure"] = number(f["Expenditure"])
    f["quantity"] = number(f["Amount"])
    f["price_raw"] = number(f["Price_Raw"])
    coded = f[f["commodity_code"].notna()].copy()
    agg = aggregate_item_household(coded)
    hh = households.copy()
    hh["address_raw"] = hh["address_raw"].astype("string")
    n_sample = len(hh)
    total_food_exp = float(pd.to_numeric(f["expenditure"], errors="coerce").sum(skipna=True))
    weight_all = number(hh.get("weight", pd.Series(np.nan, index=hh.index)))
    weight_ok = np.isfinite(weight_all) & weight_all.gt(0)
    total_weight = float(weight_all[weight_ok].sum())
    urban = hh.set_index("address_raw")["urban_rural"].astype("string")
    weight = hh.set_index("address_raw")["weight"]
    agg_by_code = {code: g for code, g in agg.groupby("commodity_code", sort=False)} if len(agg) else {}
    food_by_code = {code: g for code, g in coded.groupby("commodity_code", sort=False)} if len(coded) else {}
    rows = []
    for code in codes:
        g = food_by_code.get(code, coded.iloc[0:0])
        a = agg_by_code.get(code, agg.iloc[0:0])
        n_buy = int(a["buy"].eq(1).sum()) if len(a) else 0
        buyers = a[a["buy"].eq(1)] if len(a) else a
        n_q = int(buyers["n_purchase_quantity_valid_records"].gt(0).sum()) if len(buyers) else 0
        n_uv = int(buyers["unit_value_purchase"].notna().sum()) if len(buyers) else 0
        uv = pd.to_numeric(buyers.get("unit_value_purchase", pd.Series(dtype="float64")), errors="coerce").dropna()
        purchase_records = g[g["purchase"]]
        n_purchase_records = len(purchase_records)
        price = purchase_records["price_raw"]
        n_zero_price = int(price.eq(0).sum())
        n_negative_price = int(price.lt(0).sum())
        n_invalid_price = int((~np.isfinite(price) | price.le(0)).sum())
        nonmarket = g[~g["purchase"]]
        exp_sum = float(pd.to_numeric(g["expenditure"], errors="coerce").sum(skipna=True)) if len(g) else 0.0
        exp_purchase_sum = float(pd.to_numeric(purchase_records["expenditure"], errors="coerce").sum(skipna=True)) if len(purchase_records) else 0.0
        buyer_exp = exp_purchase_sum / n_buy if n_buy else np.nan
        wt_buy = 0.0
        if len(buyers):
            bw = pd.to_numeric(weight.reindex(buyers["address_raw"].astype("string")).to_numpy(), errors="coerce")
            wt_buy = float(bw[np.isfinite(bw) & (bw > 0)].sum())
        weighted_rate = wt_buy / total_weight if total_weight > 0 else np.nan
        buyers_urban = buyers["address_raw"].map(urban) if len(buyers) else pd.Series(dtype="string")
        all_urban = hh["urban_rural"].astype("string")
        urban_n = int(all_urban.eq("Urban").sum())
        rural_n = int(all_urban.eq("Rural").sum())
        urban_buy = int(buyers_urban.eq("Urban").sum())
        rural_buy = int(buyers_urban.eq("Rural").sum())
        fallback_n = int(g.get("Amount_Source", pd.Series(dtype="string")).astype("string").eq("HBSIR_Expenditure_divided_by_Price").sum())
        unit_names = set()
        has_mass = (
            g.get("Kilos_Raw", pd.Series(np.nan, index=g.index)).notna()
            | g.get("Grams_Raw", pd.Series(np.nan, index=g.index)).notna()
        )
        if has_mass.any():
            unit_names.add("kg_equivalent_from_Kilos_Grams")
        if g.get("Amount_Source", pd.Series(dtype="string")).astype("string").eq("HBSIR_Expenditure_divided_by_Price").any():
            unit_names.add("HBSIR_amount_fallback_from_expenditure_price")
        if g.get("Amount_Source", pd.Series(dtype="string")).astype("string").eq("missing").any():
            unit_names.add("amount_missing")
        price_sources = set(g.get("Price_Source", pd.Series(dtype="string")).dropna().astype(str).unique())
        hbsir_names = g.get("Commodity_Name", pd.Series(dtype="string")).dropna().astype(str).unique()
        hbsir_categories = []
        for c in ("HBSIR_Category_Level_1", "HBSIR_Category_Level_2", "HBSIR_Category_Level_3"):
            vals = g.get(c, pd.Series(dtype="string")).dropna().astype(str).unique()
            if len(vals):
                hbsir_categories.append(" > ".join(sorted(vals)))
        rows.append({
            "sample": sample_name,
            "year": year,
            "commodity_code": code,
            "commodity_name": " | ".join(sorted(set(hbsir_names))),
            "hbsir_category": " || ".join(hbsir_categories),
            "n_sample_households": n_sample,
            "n_households_with_item_record": int(a["address_raw"].nunique()) if len(a) else 0,
            "n_buying_households": n_buy,
            "purchase_rate": n_buy / n_sample if n_sample else np.nan,
            "purchase_rate_weighted": weighted_rate,
            "expenditure_sum_reported_all_provisions": exp_sum,
            "expenditure_sum_purchase_provisions": exp_purchase_sum,
            "mean_expenditure_all_households": exp_sum / n_sample if n_sample else np.nan,
            "mean_expenditure_among_buyers": buyer_exp,
            "food_expenditure_share": exp_sum / total_food_exp if total_food_exp > 0 else np.nan,
            "n_quantity_valid_between_buyers": n_q,
            "quantity_valid_rate_between_buyers": n_q / n_buy if n_buy else np.nan,
            "n_price_valid_between_buyers": n_uv,
            "price_valid_rate_between_buyers": n_uv / n_buy if n_buy else np.nan,
            "median_unit_value": float(uv.median()) if len(uv) else np.nan,
            "p10_unit_value": float(uv.quantile(0.10)) if len(uv) else np.nan,
            "p25_unit_value": float(uv.quantile(0.25)) if len(uv) else np.nan,
            "p75_unit_value": float(uv.quantile(0.75)) if len(uv) else np.nan,
            "p90_unit_value": float(uv.quantile(0.90)) if len(uv) else np.nan,
            "n_purchase_food_records": n_purchase_records,
            "zero_price_record_rate": n_zero_price / n_purchase_records if n_purchase_records else np.nan,
            "negative_price_record_rate": n_negative_price / n_purchase_records if n_purchase_records else np.nan,
            "invalid_price_record_rate": n_invalid_price / n_purchase_records if n_purchase_records else np.nan,
            "n_nonmarket_records": len(nonmarket),
            "nonmarket_acquisition_record_rate": len(nonmarket) / len(g) if len(g) else np.nan,
            "n_households_with_nonmarket_record": int(nonmarket["ID"].nunique()) if len(nonmarket) else 0,
            "urban_sample_households": urban_n,
            "urban_buying_households": urban_buy,
            "urban_coverage": urban_buy / urban_n if urban_n else np.nan,
            "rural_sample_households": rural_n,
            "rural_buying_households": rural_buy,
            "rural_coverage": rural_buy / rural_n if rural_n else np.nan,
            "amount_fallback_records": fallback_n,
            "amount_fallback_record_rate": fallback_n / len(g) if len(g) else np.nan,
            "price_source_values": " | ".join(sorted(price_sources)),
            "unit_value_not_comparable_flag": int(len(price_sources) > 1),
            "price_source_heterogeneity_review_flag": int(len(price_sources) > 1),
            "amount_source_unit_support_flag": int("amount_missing" in unit_names or "HBSIR_amount_fallback_from_expenditure_price" in unit_names),
            "n_food_records": len(g),
        })
    return rows, agg


def commodity_preflight() -> tuple[list[str], dict[int, set[str]]]:
    by_year: dict[int, set[str]] = {}
    all_codes: set[str] = set()
    for year in YEARS:
        values = pd.read_parquet(ROOT / "yearly" / str(year) / "food.parquet", columns=["Commodity_Code"])["Commodity_Code"]
        codes = set(clean_code_series(values).dropna().astype(str))
        by_year[year] = codes
        all_codes.update(codes)
    return sorted(all_codes), by_year


def update_commodity_dictionary(info: dict[str, dict[str, Any]], food: pd.DataFrame, year: int) -> None:
    code = clean_code_series(food["Commodity_Code"])
    for c, idx in food.groupby(code, dropna=True, sort=False).groups.items():
        key = str(c)
        g = food.loc[idx]
        item = info.setdefault(key, {"years": set(), "names": set(), "categories": set(), "unit_sources": set(), "price_sources": set(), "amount_sources": set()})
        item["years"].add(year)
        item["names"].update(g.get("Commodity_Name", pd.Series(dtype="string")).dropna().astype(str).unique())
        for col in ("HBSIR_Category_Level_1", "HBSIR_Category_Level_2", "HBSIR_Category_Level_3"):
            if col in g:
                item["categories"].update((col + ": " + x) for x in g[col].dropna().astype(str).unique())
        item["price_sources"].update(g.get("Price_Source", pd.Series(dtype="string")).dropna().astype(str).unique())
        item["amount_sources"].update(g.get("Amount_Source", pd.Series(dtype="string")).dropna().astype(str).unique())
        mass = g.get("Kilos_Raw", pd.Series(np.nan, index=g.index)).notna() | g.get("Grams_Raw", pd.Series(np.nan, index=g.index)).notna()
        item["unit_sources"].add("HBSIR Kilos/Grams fields to kg-equivalent" if mass.any() else "No observed raw mass component on some rows")


def build_commodity_dictionary(info: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for code, item in sorted(info.items()):
        years = sorted(item["years"])
        names = sorted(item["names"])
        cats = sorted(item["categories"])
        rows.append({
            "commodity_code": code,
            "commodity_name": " | ".join(names),
            "years_observed": ";".join(map(str, years)),
            "first_year": min(years) if years else pd.NA,
            "last_year": max(years) if years else pd.NA,
            "HBSIR_category": " | ".join(cats),
            "name_changed_across_years": int(len(names) > 1),
            "category_changed_across_years": int(len(cats) > 3),
            "unit_information": "HBSIR amount is based on Kilos + Grams/1000 (kg-equivalent); HBSIR Amount may use Expenditure/Price fallback. Price_Raw is the cleaned-source survey unit-price field.",
            "unit_source_values": " | ".join(sorted(item["unit_sources"])),
            "amount_source_values": " | ".join(sorted(item["amount_sources"])),
            "price_source_values": " | ".join(sorted(item["price_sources"])),
            "notes": "Names/categories retained as observed. No commodity grouping or price index applied.",
        })
    return pd.DataFrame(rows)


def create_old_crosswalk(dictionary: pd.DataFrame) -> pd.DataFrame:
    if not OLD_MAPPING_SOURCE.exists():
        raise FileNotFoundError(f"old article mapping source missing: {OLD_MAPPING_SOURCE}")
    old = pd.read_csv(OLD_MAPPING_SOURCE, dtype="string")
    code_col = next((c for c in old.columns if c.casefold().strip() == "code"), None)
    if code_col is None:
        raise ValueError("old mapping CSV must include a code column")
    old["commodity_code"] = clean_code_series(old[code_col])
    observed = set(dictionary["commodity_code"].astype(str))
    rows = []
    old_by = {str(c): g for c, g in old[old["commodity_code"].notna()].groupby("commodity_code", sort=False)}
    for code in sorted(observed | set(old_by)):
        g = old_by.get(code)
        new = dictionary[dictionary["commodity_code"].eq(code)]
        old_groups = sorted(set(g["group"].dropna().astype(str))) if g is not None and "group" in g else []
        old_names = sorted(set(g.get("commodity_name", pd.Series(dtype="string")).dropna().astype(str))) if g is not None else []
        old_p = sorted(set(g.get("p_var", pd.Series(dtype="string")).dropna().astype(str))) if g is not None else []
        old_e = sorted(set(g.get("exp_var", pd.Series(dtype="string")).dropna().astype(str))) if g is not None else []
        new_seen = not new.empty
        old_present = g is not None
        status = "observed_and_in_old_mapping" if new_seen and old_present else "observed_not_in_old_mapping" if new_seen else "in_old_mapping_not_observed"
        rows.append({
            "commodity_code": code,
            "commodity_name_1392_1403": new.iloc[0]["commodity_name"] if new_seen else "",
            "observed_in_1392_1403": int(new_seen),
            "old_mapping_present": int(old_present),
            "old_group": ";".join(old_groups),
            "old_price_variable": ";".join(old_p),
            "old_expenditure_variable": ";".join(old_e),
            "old_commodity_name": " | ".join(old_names),
            "crosswalk_status": status,
            "source_file": "mapexcel.xlsx from Google Drive; reference crosswalk only; no old grouping applied",
        })
    return pd.DataFrame(rows)


def write_parquet_batch(path: Path, df: pd.DataFrame, writer: pq.ParquetWriter | None) -> pq.ParquetWriter:
    table = pa.Table.from_pandas(df, preserve_index=False)
    if writer is None:
        writer = pq.ParquetWriter(path, table.schema, compression="zstd", version="2.6")
    else:
        table = table.select(writer.schema.names)
        table = table.cast(writer.schema, safe=False)
    writer.write_table(table, row_group_size=100_000)
    return writer


def write_csv_gzip_batch(path: Path, df: pd.DataFrame, first: bool) -> None:
    df.to_csv(path, index=False, mode="wt" if first else "at", header=first, compression={"method": "gzip", "compresslevel": 1})


def profile_rows(all_sample: pd.DataFrame, panel_b: pd.DataFrame, annual_audit: pd.DataFrame, top_codes: list[str]) -> tuple[pd.DataFrame, str]:
    output: list[dict[str, Any]] = []
    all_groups = {"All_Cross_Section": all_sample}
    panel_usable = panel_b[panel_b["food_matched"].eq(1)].copy()
    all_groups["Panel_B"] = panel_usable
    metrics = ["household_size", "head_age", "food_exp_observed_total", "n_food_items_positive", "n_food_items_purchased"]
    categorical = ["urban_rural", "province_farsi", "head_sex", "head_education"]
    for period, year in [("Annual", y) for y in YEARS] + [("Pooled", None)]:
        frames = {}
        for label, df in all_groups.items():
            frames[label] = df if year is None else df[df["year"].eq(year)]
        a = frames["All_Cross_Section"]
        b = frames["Panel_B"]
        for metric in ["household_count"]:
            av, bv = len(a), len(b)
            output.append({"period": period, "year": year, "metric": metric, "category": "", "all_n": len(a), "all_value": av, "panelB_n": len(b), "panelB_value": bv, "difference_panelB_minus_all": bv-av, "standardized_difference": np.nan})
        for metric in metrics:
            av = pd.to_numeric(a[metric], errors="coerce").dropna()
            bv = pd.to_numeric(b[metric], errors="coerce").dropna()
            if len(av) and len(bv):
                denom = math.sqrt((float(av.var(ddof=1) or 0) + float(bv.var(ddof=1) or 0)) / 2)
                smd = (float(bv.mean()) - float(av.mean())) / denom if denom > 0 else np.nan
                output.append({"period": period, "year": year, "metric": metric, "category": "mean", "all_n": len(av), "all_value": float(av.mean()), "panelB_n": len(bv), "panelB_value": float(bv.mean()), "difference_panelB_minus_all": float(bv.mean()-av.mean()), "standardized_difference": smd})
            for label, group in (("All_Cross_Section", a), ("Panel_B", b)):
                output.append({"period": period, "year": year, "metric": metric + "_median", "category": label, "all_n": len(group), "all_value": float(pd.to_numeric(group[metric], errors="coerce").median()) if len(group) else np.nan, "panelB_n": len(group), "panelB_value": np.nan, "difference_panelB_minus_all": np.nan, "standardized_difference": np.nan})
        for metric in categorical:
            # Education codes/labels are preserved, but pooled education contrasts are not interpreted.
            if metric == "head_education" and period == "Pooled":
                continue
            av = a[metric].astype("string").fillna("<missing>").value_counts(normalize=True, dropna=False)
            bv = b[metric].astype("string").fillna("<missing>").value_counts(normalize=True, dropna=False)
            for value in sorted(set(av.index) | set(bv.index)):
                pa_ = float(av.get(value, 0.0)); pb_ = float(bv.get(value, 0.0))
                output.append({"period": period, "year": year, "metric": metric, "category": value, "all_n": len(a), "all_value": pa_, "panelB_n": len(b), "panelB_value": pb_, "difference_panelB_minus_all": pb_-pa_, "standardized_difference": np.nan})
        chosen = annual_audit[
            annual_audit["commodity_code"].isin(top_codes)
            & annual_audit["sample"].isin(["All_Cross_Section", "Panel_B"])
        ]
        if year is not None:
            chosen = chosen[chosen["year"].eq(year)]
        for _, r in chosen.iterrows():
            output.append({"period": period, "year": year, "metric": "commodity_purchase_rate", "category": r["commodity_code"] + " | " + str(r["commodity_name"]), "all_n": r["n_sample_households"] if r["sample"] == "All_Cross_Section" else np.nan, "all_value": r["purchase_rate"] if r["sample"] == "All_Cross_Section" else np.nan, "panelB_n": r["n_sample_households"] if r["sample"] == "Panel_B" else np.nan, "panelB_value": r["purchase_rate"] if r["sample"] == "Panel_B" else np.nan, "difference_panelB_minus_all": np.nan, "standardized_difference": np.nan})
    profile = pd.DataFrame(output)
    # Complete the top-item all vs Panel B rows with a stable merge for report use.
    comp = annual_audit[annual_audit["commodity_code"].isin(top_codes)].pivot_table(
        index=["year", "commodity_code", "commodity_name"], columns="sample", values=["purchase_rate", "food_expenditure_share"], aggfunc="first"
    )
    comp.columns = ["_".join(str(v) for v in col if v) for col in comp.columns]
    comp = comp.reset_index()
    lines = [
        "# مقایسهٔ توصیفی Panel B و نمونهٔ مقطعی کامل",
        "",
        "نمونهٔ All Cross-Section شامل خانوارهای تکمیل‌شده با حداقل یک ردیف خوراکی است و Panel B زیرمجموعهٔ آن است؛ دو نمونه مستقل نیستند. همهٔ مخارج اسمی‌اند و برای تورم تعدیل نشده‌اند. متغیر تحصیلات به‌صورت کد/برچسب سالانه حفظ شده و به علت تغییر کدگذاری، مقایسهٔ تجمیعی آن تفسیر نمی‌شود.",
        "",
        "## تعداد household-yearها",
        "",
        "| سال | All Sample | Panel B با دادهٔ غذایی | سهم Panel B از All |",
        "|---:|---:|---:|---:|",
    ]
    for year in YEARS:
        na = len(all_sample[all_sample.year.eq(year)])
        nb = len(panel_usable[panel_usable.year.eq(year)])
        lines.append(f"| {year} | {na:,} | {nb:,} | {nb/na:.1%} |" if na else f"| {year} | 0 | 0 | — |")
    lines += [
        "",
        "## تفاوت‌های جمعیت‌شناختی و مخارج درون‌سال",
        "",
        "در `panelB_vs_all_sample_profile.csv` توزیع سالانهٔ شهری/روستایی، استان، جنس و تحصیلات سرپرست آمده است. برای اندازهٔ خانوار، سن سرپرست، کل مخارج غذایی مشاهده‌شده و شمار اقلام مثبت نیز میانگین، میانه و standardized difference ثبت شده است. standardized difference فقط توصیفی است و به دلیل هم‌پوشانی Panel B با All، آزمون استقلال نمونه نیست.",
        "",
        "## اقلام برجسته برای تشخیص",
        "",
        "بیست قلم بالای فهرست برای نمایش صرفاً بر اساس مجموع مخارج اسمی ثبت‌شده در All Sample رتبه‌بندی شده‌اند؛ این رتبه‌بندی گروه‌بندی یا انتخاب نهایی کالا نیست.",
        "",
        "| سال | کد کالا | نرخ خرید All | نرخ خرید Panel B | سهم مخارج All | سهم مخارج Panel B |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in comp.iterrows():
        lines.append("| {year} | {code} | {pa} | {pb} | {sa} | {sb} |".format(
            year=int(r.year), code=r.commodity_code,
            pa="—" if pd.isna(r.get("purchase_rate_All_Cross_Section")) else f"{r['purchase_rate_All_Cross_Section']:.1%}",
            pb="—" if pd.isna(r.get("purchase_rate_Panel_B")) else f"{r['purchase_rate_Panel_B']:.1%}",
            sa="—" if pd.isna(r.get("food_expenditure_share_All_Cross_Section")) else f"{r['food_expenditure_share_All_Cross_Section']:.1%}",
            sb="—" if pd.isna(r.get("food_expenditure_share_Panel_B")) else f"{r['food_expenditure_share_Panel_B']:.1%}",
        ))
    lines += ["", "این جدول فقط تفاوت توصیفی را نشان می‌دهد؛ قیمت گروهی یا مدل تقاضا محاسبه نشده است."]
    return profile, "\n".join(lines) + "\n"


def write_dictionaries(available_data: pd.DataFrame | None = None) -> None:
    rows = []
    common_years = ";".join(map(str, YEARS))
    definitions = [
        ("address_raw", "Address_Raw; Address", "رشتهٔ خام Address خانوار در Access؛ کلید اصلی بدون تغییر", "رشته؛ صفر ابتدایی در صورت وجود حفظ می‌شود", "تبدیل به string؛ هیچ بخش جغرافیایی به کلید دائمی تبدیل نمی‌شود", "Address به‌تنهایی شناسهٔ جهانی خانوار نیست."),
        ("year", "Year; پوشهٔ سالانه", "سال شمسی مشاهده", "۱۳۹۲ تا ۱۴۰۳", "عدد سال به int16", "فقط این بازه در خروجی‌های تحلیلی حاضر است."),
        ("frame", "Raw_Table / دورهٔ طراحی", "شناسهٔ دورهٔ طراحی نمونه‌گیری", "Frame_1392_1396 یا Frame_1397_1403", "بر اساس سال طراحی؛ هیچ پیوند ۱۳۹۶→۱۳۹۷ ساخته نشده", "در panel_id استفاده می‌شود."),
        ("panel_id", "Frame + Address_Raw", "شناسهٔ scoped برای Address در همان دورهٔ طراحی", "frame:address_raw", "الحاق رشته‌ای دقیق", "به‌عنوان شناسهٔ دائمی خارج از همان frame اثبات نشده است."),
        ("cohort", "panel_candidates_1392_1403.parquet: Cohort", "سه‌موج معتبر ممیزی‌شده", "1392_1394…1401_1403", "فقط برای Panel B پر می‌شود", "برای householdهای خارج از B خالی است."),
        ("wave", "panel_candidates_1392_1403.parquet: year position", "موقعیت موج در cohort", "1/2/3", "فقط برای Panel B پر می‌شود", "برای householdهای خارج از B خالی است."),
        ("panel_B", "panel_candidates_1392_1403.parquet: Sample_B", "پرچم نمونهٔ اصلی پنلی", "1 فقط Address یکسان و Takmil=1 در سه موج همان cohort", "پرچم ممیزی قبلی؛ مرز frame ممنوع", "Level 1/2 به جای آن انتخاب نشده‌اند."),
        ("panel_level1", "panel_candidates_1392_1403.parquet: Sample_Level_1", "پرچم اعتبارسنجی Level 1", "0/1", "کپی از ممیزی قبلی", "فقط تشخیصی."),
        ("panel_level2", "panel_candidates_1392_1403.parquet: Sample_Level_2", "پرچم اعتبارسنجی Level 2", "0/1", "کپی از ممیزی قبلی", "فقط تشخیصی."),
        ("urban_rural", "household_information: Urban_Rural; Raw_Table", "طبقهٔ شهری/روستایی HBSIR", "Urban/Rural", "برچسب HBSIR نگه داشته شده؛ با نوع جدول Access کنترل می‌شود", "urban_rural_match_check اختلاف احتمالی را ثبت می‌کند."),
        ("province", "household_information: Province / Province_Farsi", "استان بر اساس طبقه‌بندی HBSIR", "نام انگلیسی و فارسی HBSIR", "بدون بازنگاشت بین‌سالی", "نام گزارش‌شده حفظ شده است."),
        ("county", "household_information: County / County_Farsi", "شهرستان HBSIR در صورت موجود بودن", "نام انگلیسی و فارسی HBSIR", "بدون تجمیع شهرستان", "قابلیت مقایسهٔ بین‌سالی جداگانه ارزیابی شود."),
        ("season", "household_information: Season / Season_Number; raw Fasl", "فصل مصاحبه", "کد و برچسب HBSIR؛ Fasl خام جدا", "برچسب HBSIR و کد خام حفظ شده", "هیچ فصل جدیدی ساخته نشده است."),
        ("interview_month", "household_information: Month; raw MahMorajeh", "ماه مصاحبه", "ماه HBSIR؛ کد خام جدا", "ماه HBSIR و MahMorajeh خام کنار هم نگه داشته شده‌اند", "تبدیل ماه HBSIR سالانه در metadata قبلی مستند است."),
        ("weight", "1392–1395: HBSIR external weight table; 1396–1403: household_information.WEIGHT", "وزن خانوار HBSIR", "وزن عددی؛ منبع متغیر قبل/بعد ۱۳۹۶", "HBSIR Weight؛ weight_raw، access_weight_raw و weight_source نگه داشته می‌شود", "وزن خام Access از ۱۳۹۶ تا ۱۴۰۳ با HBSIR منطبق است؛ وزن‌های ۱۳۹۲–۱۳۹۵ از فایل خارجی HBSIR هستند."),
        ("cluster_psu", "—", "PSU/خوشهٔ قابل اتکا در همهٔ سال‌ها", "در schema harmonized قابل اتکا در تمام سال‌ها موجود نیست", "تعریف/استخراج نشده", "از prefix آدرس به‌عنوان PSU استفاده نشده است."),
        ("household_size", "household_information: Household_Size", "اندازهٔ خانوار HBSIR", "تعداد اعضای ثبت‌شده", "مقدار استاندارد HBSIR حفظ شده؛ تعداد اعضای جدول اعضا جدا آمده", "اختلاف را خودکار اصلاح نمی‌کنیم."),
        ("head_age", "1392–1403: members_properties.DYCOL05 → Age; DYCOL03=Head", "سن سرپرست", "سن عددی HBSIR", "ردیف سرپرست با Relationship=Head؛ فقط یک ردیف یکتا پذیرفته می‌شود", "مقادیر گمشده حفظ می‌شوند."),
        ("head_sex", "1392–1403: members_properties.DYCOL04 → Sex; DYCOL03=Head", "جنس سرپرست", "برچسب HBSIR", "نگاشت HBSIR؛ بدون بازنویسی جنس", "مقادیر گمشده حفظ می‌شوند."),
        ("head_education", "1392–1403: members_properties.DYCOL08 → Education_Level; DYCOL03=Head", "تحصیلات سرپرست", "کد/برچسب سالانهٔ HBSIR", "بازکدگذاری بین‌سالی انجام نشده", "کدگذاری HBSIR در ۱۳۹۳ و ۱۳۹۷ تغییر کرده؛ مقایسهٔ تجمیعی تفسیر نشود."),
        ("head_is_literate", "1392–1403: members_properties.DYCOL06 → Is_Literate; DYCOL03=Head", "باسواد بودن سرپرست", "Boolean HBSIR", "بدون پرکردن missing", "کدهای اصل در گزارش HBSIR موجود است."),
        ("head_is_student", "1392–1403: members_properties.DYCOL07 → Is_Student; DYCOL03=Head", "دانشجو بودن سرپرست", "Boolean HBSIR", "بدون پرکردن missing", "کدهای اصل در گزارش HBSIR موجود است."),
        ("head_marital_status", "1392–1403: members_properties.DYCOL10 → Marital_Status; DYCOL03=Head", "وضع تأهل سرپرست", "برچسب HBSIR", "برچسب حفظ شده؛ مقایسهٔ بین‌سالی جداگانه بازبینی شود", "بدون تجمیع خودسرانه."),
        ("head_activity_status", "1392–1403: members_properties.DYCOL09 → Activity_Status; DYCOL03=Head", "وضعیت فعالیت سرپرست", "برچسب HBSIR", "برچسب حفظ شده؛ مقایسهٔ بین‌سالی جداگانه بازبینی شود", "بدون تجمیع خودسرانه."),
        ("takmil", "Takmil", "تکمیل پرسشنامهٔ خانوار اصلی", "1=بله، 2=خیر در پرسشنامه همان سال", "کد خام متنی با حذف فاصلهٔ پیرامونی؛ تأیید مصاحبه فقط مقدار دقیق 1", "شماره سؤال تا ۱۳۹۶ Q19 و از ۱۳۹۷ Q18 است."),
        ("jaygozin", "Jaygozin", "تکمیل پرسشنامهٔ خانوار جایگزین", "1=بله، 2=خیر در پرسشنامه همان سال", "کد خام متنی با حذف فاصلهٔ پیرامونی؛ تأیید مصاحبه فقط مقدار دقیق 1", "شماره سؤال تا ۱۳۹۶ Q20 و از ۱۳۹۷ Q19 است."),
        ("respondent_kind", "Takmil + Jaygozin", "نوع پاسخ‌دهنده بر اساس دو کد خام", "Original/Substitute/Conflicting/No completed/Ambiguous", "1 دقیق در Takmil یا Jaygozin وضعیت تکمیل است؛ تعارض صریح جدا می‌ماند", "برای All Sample فقط affirmative exact code پذیرفته شد."),
        ("food_exp_observed_total", "food: Expenditure", "جمع ارزش مخارج/تهیهٔ غذایی ثبت‌شده", "واحد پول همان فایل HBSIR؛ اسمی", "جمع Expenditure تمام روش‌های تهیه، بدون تبدیل قیمت یا تعدیل تورم", "شامل non-market valueهای ثبت‌شده است؛ خرید نقدی جدا در itemwide موجود است."),
        ("n_food_items_positive", "food: Commodity_Code + Expenditure", "تعداد کدهای کالایی با Expenditure مثبت ثبت‌شده", "تعداد کد یکتا", "تجمیع همهٔ روش‌های تهیه در خانوار-سال-کد", "با n_food_items_purchased که فقط روش‌های خرید است متفاوت است."),
    ]
    extra_definitions = [
        ("urban_rural_raw_table", "Access: Raw_Table", "طبقهٔ شهری/روستایی برگرفته از نام جدول Access", "نام جدول با پیشوند U=Urban و R=Rural", "طبقه‌بندی خام جدول Access؛ برای کنترل با Urban_Rural هارمون‌شده حفظ شده", "فقط کنترل کیفیت است و جای متغیر جغرافیایی HBSIR را نمی‌گیرد."),
        ("urban_rural_match_check", "Raw_Table + HBSIR Urban_Rural", "برابری طبقهٔ شهری/روستایی Access و HBSIR", "1=برابر؛ 0=مغایر یا HBSIR missing", "مقایسهٔ exact پس از طبقه‌بندی U/R جدول Access", "پرچم تشخیصی؛ هیچ ردیفی با آن حذف نشده است."),
        ("province_farsi", "HBSIR id_information.yaml / Province_Farsi", "نام فارسی استان در طبقه‌بندی HBSIR", "برچسب HBSIR", "بدون تجمیع یا بازنگاشت بین‌سالی", "مقادیر خام حفظ شده‌اند."),
        ("county_farsi", "HBSIR id_information.yaml / County_Farsi", "نام فارسی شهرستان در طبقه‌بندی HBSIR", "برچسب HBSIR یا missing", "بدون تجمیع شهرستان", "مقایسه‌پذیری مرزهای شهرستانی باید جداگانه بررسی شود."),
        ("season_number", "Access household_information.FASL", "کد فصل خام پرسشنامه", "کد عددی سالانه", "کد خام HBSIR/Access حفظ شده", "از برچسب season جدا است."),
        ("fasl_raw", "Access: Fasl", "مقدار خام فصل در فایل Access", "کد متنی خام", "تبدیل تحلیلی انجام نشده", "برای بررسی تطبیق با Season_Number نگه داشته شده است."),
        ("mah_morajeh_raw", "Access: MahMorajeh", "ماه مراجعهٔ خام در فایل Access", "کد متنی خام", "بدون اصلاح یا بازکدگذاری", "از interview_month تعدیل‌شدهٔ HBSIR جداست."),
        ("weight_raw", "household_information.WEIGHT (1396–1403)", "فیلد وزن خام خانوار در منبع HBSIR", "عدد وزن؛ پیش از 1396 در فایل خانوار موجود نیست", "مقدار خام نگه داشته شده؛ برای سال‌های پیش از 1396 missing است", "weight استاندارد HBSIR در سال‌های قبل از 1396 از فایل وزن خارجی می‌آید."),
        ("access_weight_raw", "Access household table: weight/Weight (1396–1403)", "فیلد وزن در فایل خام Access", "عدد وزن؛ پیش از 1396 در فایل خانوار Access موجود نیست", "نام ستون case-insensitive خوانده و با نام استاندارد جدا از وزن HBSIR حفظ شده", "برای 1396–1403 با وزن HBSIR تطبیق داده شد؛ پیش از 1396 وزن استاندارد از فایل خارجی HBSIR است."),
        ("access_weight_match_check", "Access weight/Weight vs HBSIR Weight", "تطبیق وزن خام Access با وزن استاندارد HBSIR", "1=منطبق؛ 0=مغایر؛ missing=Access weight unavailable", "مقایسهٔ عددی با tolerance نسبی 1e-10", "در 1396–1403 بررسی می‌شود؛ در 1392–1395 وزن HBSIR از فایل خارجی است."),
        ("weight_source", "household_information.WEIGHT / HBSIR external weight table", "منبع وزن استاندارد HBSIR", "برچسب منبع سالانه", "کپی از منبع مستندشده در pipeline HBSIR", "در هر سال از خود ستون استفاده شود؛ وزن‌های قبل/بعد 1396 منبع متفاوت دارند."),
        ("n_members_file", "members_properties rows by exact ID", "شمار ردیف‌های عضو در فایل HBSIR", "عدد صحیح", "تعداد رکوردهای عضو برای household ID؛ بدون حذف عضو", "ممکن است با Household_Size استاندارد اختلاف داشته باشد؛ اصلاح خودکار نمی‌شود."),
        ("household_type", "household_information.NOEKHN", "نوع خانوار در طبقه‌بندی HBSIR", "برچسب دسته‌ای HBSIR", "کد به برچسب HBSIR تبدیل شده", "تعریف کدها از metadata HBSIR است."),
        ("main_household_hbsir", "household_information.TAKMIL", "پرچم خانوار اصلی در HBSIR", "Boolean استاندارد HBSIR", "تبدیل کد survey به Boolean در HBSIR", "از Takmil خام Access در تعریف All Sample جدا نگه داشته شده است."),
        ("alternative_household_hbsir", "household_information.JAYGOZIN", "پرچم خانوار جایگزین در HBSIR", "Boolean استاندارد HBSIR", "تبدیل کد survey به Boolean در HBSIR", "از Jaygozin خام Access در تعریف All Sample جدا نگه داشته شده است."),
        ("head_member_rows", "members_properties.Relationship=Head", "تعداد ردیف‌های سرپرست خانوار در فایل اعضا", "عدد صحیح", "شمار دقیق ردیف‌هایی که Relationship برابر Head است", "ویژگی‌های سرپرست تنها وقتی دقیقاً یک ردیف Head وجود دارد متصل می‌شود."),
        ("head_member_number", "members_properties.DYCOL01 where Relationship=Head", "شماره عضو سرپرست", "شناسه عضو درون خانوار", "از ردیف یکتای Head کپی شده", "شناسهٔ فردی دائمی تلقی نمی‌شود."),
        ("head_relationship", "members_properties.DYCOL03 where head row", "برچسب رابطهٔ عضو سرپرست", "برچسب HBSIR؛ معمولاً Head", "ردیف سرپرست یکتا", "برای کنترل اتصال حفظ شده است."),
        ("head_demographics_matched", "members_properties.DYCOL03", "وجود دقیقاً یک رکورد سرپرست برای خانوار", "1=یک ردیف Head؛ 0=صفر/چند ردیف یا missing", "پرچم کیفیت اتصال", "عدم اتصال demographic باعث حذف household-year نشده است."),
        ("member_table_matched", "members_properties.ID", "وجود حداقل یک رکورد عضو با شناسهٔ خانوار", "1=matched؛ 0=بدون رکورد عضو", "تطبیق با شناسهٔ دقیق HBSIR ID", "پرچم کیفیت اتصال؛ شرط ورود نمونه نیست."),
        ("completed_interview", "Access: Takmil / Jaygozin", "وجود مصاحبهٔ تکمیل‌شده برای خانوار مشاهده‌شده", "1 اگر Takmil=1 یا Jaygozin=1؛ در غیر این صورت 0", "فقط کد دقیق 1 تأیید مثبت است", "شماره سؤال Takmil تا 1396 برابر Q19 و از 1397 برابر Q18؛ Jaygozin به‌ترتیب Q20 و Q19."),
        ("household_table_matched", "household_information.ID", "اتصال household به جدول استاندارد HBSIR", "1=matched با Address دقیق؛ 0=unmatched", "تطبیق exact string آدرس خام Access با ID HBSIR", "هیچ تطبیق جغرافیایی/تقریبی اعمال نشده است."),
        ("food_matched", "food.ID", "وجود حداقل یک ردیف غذایی HBSIR", "1=یک یا چند ردیف؛ 0=بدون ردیف غذا", "تطبیق exact string Address با ID", "در Panel B مقدار 0 به معنی دادهٔ مفقود است، نه مخارج صفر."),
        ("n_food_rows", "food.ID rows", "تعداد ردیف‌های غذایی خام خانوار-سال", "عدد صحیح", "شمار ردیف‌های source؛ قبل از تجمیع", "یک قلم می‌تواند چند ردیف یا روش تهیه داشته باشد."),
        ("n_food_items_purchased", "food.Commodity_Code + Provision_Method + Expenditure", "تعداد کدهای کالایی با خرید/مخارج خرید مثبت", "تعداد کد یکتا در household-year", "روش‌های خرید ثبت‌شده جداگانه جمع می‌شوند؛ شمار کد با جمع خرید مثبت >0", "غیرخریدها در این شمار وارد نمی‌شوند."),
        ("n_food_rows_uncoded", "food.Commodity_Code", "تعداد ردیف‌های غذا با کد کالا missing یا نامعتبر", "عدد صحیح", "شمار ردیف‌های بدون کد استاندارد پنج‌رقمی", "این ردیف‌ها از total observed expenditure حذف نمی‌شوند."),
        ("food_exp_uncoded", "food.Expenditure where Commodity_Code missing", "مخارج ردیف‌های غذایی فاقد کد کالا", "مبلغ HBSIR اسمی", "جمع Expenditure ردیف‌های فاقد Commodity_Code", "برای reconcile مخارج کل نگه داشته شده؛ گروه کالایی به آن تخصیص داده نشده است."),
        ("raw_table_name", "Access: Raw_Table", "نام دقیق جدول خانوار در Access", "رشتهٔ نام جدول U/R", "بدون تغییر حفظ شده", "برای ممیزی طبقهٔ شهری/روستایی و provenance است."),
    ]
    definitions.extend(extra_definitions)
    for name, raw, meaning, coding, transform, notes in definitions:
        if name.startswith("head_") and name not in {"head_is_literate", "head_is_student", "head_marital_status", "head_activity_status"}:
            raw = raw.replace("members_properties:", "1392–1403: members_properties.")
        rows.append({"standard_name": name, "raw_name_by_year": raw, "meaning": meaning, "coding": coding, "years_available": common_years, "transformation": transform, "notes": notes})
    food_rows = [
        {"standard_name": "amount_raw", "raw_name_by_year": "food: Kilos_Raw, Grams_Raw", "meaning": "مقدار خام مشاهده‌شدهٔ منبع cleaned به گرم-equivalent", "coding": "Kilos_Raw×1000 + Grams_Raw", "years_available": common_years, "transformation": "محاسبه از دو جزء خام؛ اگر هر دو گمشده‌اند missing می‌ماند", "notes": "Kilos_Raw و Grams_Raw نیز جدا حفظ شده‌اند."},
        {"standard_name": "amount_standardized", "raw_name_by_year": "food: Amount / Amount_Source", "meaning": "مقدار استاندارد HBSIR به kg-equivalent", "coding": "Kilos + Grams/1000؛ در fallback از Expenditure/Price", "years_available": common_years, "transformation": "مقدار HBSIR بدون اصلاح؛ source flag نگه داشته شده", "notes": "fallback در amount_fallback_flag مشخص است؛ missing/zero با هم یکی نشده‌اند."},
        {"standard_name": "price_raw", "raw_name_by_year": "food: Price_Raw", "meaning": "فیلد قیمت ثبت‌شده در منبع cleaned HBSIR", "coding": "واحد HBSIR؛ صفر/منفی/missing حفظ می‌شود", "years_available": common_years, "transformation": "بدون جایگزینی یا winsorization", "notes": "در همه سال‌ها استخراج مستقل Access نیست؛ برای ۱۴۰۲ اعتبارسنجی مستقیم وجود دارد."},
        {"standard_name": "price_hbsir", "raw_name_by_year": "food: Price", "meaning": "قیمت HBSIR پس از قواعد استانداردسازی", "coding": "صفر می‌تواند به missing تبدیل شود", "years_available": common_years, "transformation": "مقدار normalized HBSIR؛ کنار Price_Raw نگه داشته شده", "notes": "هیچ شاخص قیمت گروهی ساخته نشده است."},
        {"standard_name": "unit_value", "raw_name_by_year": "derived from Price_Raw", "meaning": "Price_Raw معتبر مثبت در سطح ردیف کالا", "coding": "Price_Raw اگر finite و >0؛ وگرنه missing", "years_available": common_years, "transformation": "محاسبهٔ quotient جدید نمی‌شود", "notes": "wide uv برای خریدها از میانگین قیمت خام با وزن مقدار ساخته می‌شود؛ بدون خرید missing است."},
        {"standard_name": "expenditure_raw", "raw_name_by_year": "food: Expenditure", "meaning": "ارزش Expenditure ردیف غذایی HBSIR", "coding": "مبلغ ثبت‌شده در HBSIR", "years_available": common_years, "transformation": "بدون تعدیل تورم؛ zero/missing تفکیک", "notes": "itemwide exp شامل همهٔ provision methods است؛ exp_purchase جداست."},
    ]
    dictionary = pd.DataFrame(rows)
    if available_data is not None:
        years_by_value = {}
        for col in dictionary["standard_name"].astype(str):
            if col not in available_data:
                years_by_value[col] = "not in output schema"
                continue
            present = available_data.groupby("year", sort=True)[col].apply(lambda s: s.notna().any())
            years_by_value[col] = ";".join(str(int(y)) for y, ok in present.items() if bool(ok)) or "no nonmissing values"
        dictionary["years_available"] = dictionary["standard_name"].map(years_by_value)
        dictionary["notes"] = dictionary["notes"].astype("string") + "; years_available lists years with at least one nonmissing value in household_year_all."
    pd.DataFrame(dictionary).to_csv(META / "household_analysis_variable_dictionary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(food_rows).to_csv(META / "food_item_variable_dictionary_1392_1403.csv", index=False, encoding="utf-8-sig")


STRING_HH_COLUMNS = [
    "address_raw", "panel_id", "frame", "cohort", "urban_rural", "urban_rural_raw_table", "province", "province_farsi",
    "county", "county_farsi", "season", "mah_morajeh_raw", "fasl_raw", "weight_source", "household_type", "head_relationship",
    "head_sex", "head_education", "head_marital_status", "head_activity_status", "takmil", "jaygozin", "respondent_kind", "raw_table_name",
]
NUMERIC_HH_COLUMNS = [
    "interview_month", "season_number", "weight", "weight_raw", "access_weight_raw", "household_size", "head_member_number", "head_age",
    "n_members_file", "head_member_rows", "n_food_rows", "food_exp_observed_total", "n_food_items_positive",
    "n_food_items_purchased", "n_food_rows_uncoded", "food_exp_uncoded",
]
FLAG_HH_COLUMNS = [
    "panel_B", "panel_level1", "panel_level2", "completed_interview", "household_table_matched", "head_demographics_matched",
    "member_table_matched", "food_matched", "urban_rural_match_check", "main_household_hbsir", "alternative_household_hbsir",
    "head_is_literate", "head_is_student", "access_weight_match_check",
]
HH_COLUMNS = [
    "address_raw", "panel_id", "year", "frame", "cohort", "wave", "panel_B", "panel_level1", "panel_level2",
    "urban_rural", "urban_rural_raw_table", "urban_rural_match_check", "province", "province_farsi", "county", "county_farsi",
    "season", "season_number", "fasl_raw", "interview_month", "mah_morajeh_raw", "weight", "weight_raw", "access_weight_raw", "access_weight_match_check", "weight_source",
    "household_size", "n_members_file", "household_type", "main_household_hbsir", "alternative_household_hbsir",
    "head_member_rows", "head_demographics_matched", "member_table_matched", "head_member_number", "head_relationship",
    "head_age", "head_sex", "head_education", "head_is_literate", "head_is_student", "head_marital_status", "head_activity_status",
    "takmil", "jaygozin", "respondent_kind", "completed_interview", "household_table_matched", "food_matched", "n_food_rows",
    "food_exp_observed_total", "n_food_items_positive", "n_food_items_purchased", "n_food_rows_uncoded", "food_exp_uncoded", "raw_table_name",
]


def prepare_household_output(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in HH_COLUMNS:
        if col not in out:
            out[col] = pd.NA
    out = out[HH_COLUMNS]
    for col in STRING_HH_COLUMNS:
        if col in out:
            out[col] = out[col].astype("string")
    for col in NUMERIC_HH_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    for col in FLAG_HH_COLUMNS:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int8")
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype("int16")
    out["wave"] = pd.to_numeric(out["wave"], errors="coerce").astype("Int8")
    return out


def build_grouping_summary(annual: pd.DataFrame, dictionary: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    old_groups = crosswalk.set_index("commodity_code")["old_group"].to_dict()
    rows = []
    for _, drow in dictionary.iterrows():
        code = drow["commodity_code"]
        all_rows = annual[(annual["commodity_code"] == code) & (annual["sample"] == "All_Cross_Section")].sort_values("year")
        b_rows = annual[(annual["commodity_code"] == code) & (annual["sample"] == "Panel_B")].sort_values("year")
        years = all_rows["year"].astype(int).tolist()

        def mean(col: str, frame: pd.DataFrame) -> float:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna() if col in frame else pd.Series(dtype="float64")
            return float(vals.mean()) if len(vals) else np.nan

        def minv(col: str, frame: pd.DataFrame) -> float:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna() if col in frame else pd.Series(dtype="float64")
            return float(vals.min()) if len(vals) else np.nan

        def maxv(col: str, frame: pd.DataFrame) -> float:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna() if col in frame else pd.Series(dtype="float64")
            return float(vals.max()) if len(vals) else np.nan

        medians_all = {str(int(r.year)): float(r.median_unit_value) for r in all_rows.itertuples() if pd.notna(r.median_unit_value)}
        medians_b = {str(int(r.year)): float(r.median_unit_value) for r in b_rows.itertuples() if pd.notna(r.median_unit_value)}
        ratios = []
        for r in all_rows.itertuples():
            if pd.notna(r.p10_unit_value) and pd.notna(r.p90_unit_value) and float(r.p10_unit_value) > 0:
                ratios.append(float(r.p90_unit_value) / float(r.p10_unit_value))
        price_support_years = int(pd.to_numeric(all_rows["n_price_valid_between_buyers"], errors="coerce").fillna(0).ge(30).sum())
        dispersion_years = sum(ratio > 10 for ratio in ratios)
        gap = bool(years and len(years) != (max(years) - min(years) + 1))
        code_instability = bool(int(drow.name_changed_across_years) or int(drow.category_changed_across_years) or gap)
        fallback_rate = mean("amount_fallback_record_rate", all_rows)
        unit_problem = bool((pd.notna(fallback_rate) and fallback_rate >= 0.10) or all_rows["unit_value_not_comparable_flag"].fillna(0).astype(bool).any())
        poor_price = bool(mean("price_valid_rate_between_buyers", all_rows) < 0.60 or (len(all_rows) and price_support_years < math.ceil(len(all_rows) / 2)))
        low_purchase = bool(mean("purchase_rate", all_rows) < 0.05 or minv("purchase_rate", all_rows) < 0.01)
        unstable_uv = bool(len(ratios) >= 2 and dispersion_years >= math.ceil(len(ratios) / 2))
        rows.append({
            "commodity_code": code,
            "commodity_name": drow.commodity_name,
            "years_present": ";".join(map(str, years)),
            "purchase_rate_mean_all": mean("purchase_rate", all_rows),
            "purchase_rate_min_all": minv("purchase_rate", all_rows),
            "purchase_rate_max_all": maxv("purchase_rate", all_rows),
            "purchase_rate_mean_panelB": mean("purchase_rate", b_rows),
            "purchase_rate_min_panelB": minv("purchase_rate", b_rows),
            "purchase_rate_max_panelB": maxv("purchase_rate", b_rows),
            "food_expenditure_share_all": mean("food_expenditure_share", all_rows),
            "food_expenditure_share_panelB": mean("food_expenditure_share", b_rows),
            "valid_price_rate_all": mean("price_valid_rate_between_buyers", all_rows),
            "valid_price_rate_panelB": mean("price_valid_rate_between_buyers", b_rows),
            "valid_quantity_rate_all": mean("quantity_valid_rate_between_buyers", all_rows),
            "valid_quantity_rate_panelB": mean("quantity_valid_rate_between_buyers", b_rows),
            "urban_coverage": mean("urban_coverage", all_rows),
            "rural_coverage": mean("rural_coverage", all_rows),
            "unit_value_median_by_year_summary": json.dumps({"all": medians_all, "panelB": medians_b}, ensure_ascii=False, sort_keys=True),
            "unit_value_instability_flag": int(unstable_uv),
            "low_purchase_flag": int(low_purchase),
            "poor_price_support_flag": int(poor_price),
            "code_instability_flag": int(code_instability),
            "unit_problem_flag": int(unit_problem),
            "old_group_if_any": old_groups.get(code, ""),
            "notes": "Rates are annual sample-denominator summaries over years_present; no code is excluded. unit_value_instability_flag means p90/p10 > 10 in at least half of supported years; it can reflect quality/geographic dispersion, not a proven unit mismatch. unit_problem_flag also uses Price_Source heterogeneity as a review trigger, not proof of incompatible units.",
        })
    return pd.DataFrame(rows)


def report_text(
    dictionary: pd.DataFrame,
    annual: pd.DataFrame,
    grouping: pd.DataFrame,
    crosswalk: pd.DataFrame,
    all_sample: pd.DataFrame,
    panel_b: pd.DataFrame,
    flow: pd.DataFrame,
    manifest: pd.DataFrame,
) -> str:
    b_ids = panel_b["panel_id"].nunique()
    b_rows = len(panel_b)
    b_food = int(panel_b["food_matched"].sum())
    n_codes = len(dictionary)
    all_year = dictionary["years_observed"].astype("string").str.split(";").map(lambda x: len(x) if isinstance(x, list) else 0)
    all12 = int(all_year.eq(len(YEARS)).sum())
    new_codes = set(dictionary["commodity_code"].astype(str))
    covered = int(crosswalk.loc[crosswalk["commodity_code"].isin(new_codes), "old_mapping_present"].sum())
    absent_old = int((crosswalk["observed_in_1392_1403"].eq(0) & crosswalk["old_mapping_present"].eq(1)).sum())
    low = grouping[grouping.low_purchase_flag.eq(1)].sort_values("purchase_rate_mean_all").head(20)
    poor = grouping[grouping.poor_price_support_flag.eq(1)].sort_values("valid_price_rate_all").head(20)
    total_low = int(grouping.low_purchase_flag.sum())
    total_poor = int(grouping.poor_price_support_flag.sum())
    old_source_groups = sorted(set(pd.read_csv(OLD_MAPPING_SOURCE, dtype="string")["group"].dropna().astype(str)))
    old_name = "mapexcel.xlsx (Drive)"
    lines = [
        "# گزارش ساخت دیتاست پایه و ممیزی کالا، ۱۳۹۲–۱۴۰۳",
        "",
        "این مرحله خروجی پایه برای pooled cross-section نمونهٔ Panel B، CRE/Mundlak همان Household-Yearها، و pooled cross-section همهٔ خانوارهای قابل استفاده را فراهم می‌کند. هیچ QUAIDS/AID، گروه‌بندی نهایی کالا یا شاخص قیمت گروهی ساخته نشده است؛ پرچم‌های ممیزی هیچ کالایی را حذف نمی‌کنند.",
        "",
        "## اصلاح گزارش پنل: ۵۲ یا ۳٬۸۰۸؟",
        "",
        "با بازتولید مستقیم از فایل ردیفی `middlewave_absence_returns.parquet` و جدول `middlewave_nonresponse_summary.csv`، جدول خلاصه ۵۲ ردیف گروهی دارد، اما تعداد خانوارها با جمع N برابر ۳٬۸۰۸ است. تعداد ردیف فایل ردیفی نیز ۳٬۸۰۸ است: ۱٬۳۴۱ در Frame_1392_1396 و ۲٬۴۶۷ در Frame_1397_1403. گزارش پنل اصلاح شد؛ آزمون خودکارِ برابری sum(N) با تعداد ردیف household file در `tests/test_middlewave_count.py` اضافه شد و گذشت.",
        "",
        "## تعریف و اندازهٔ نمونه‌ها",
        "",
        f"Panel B دقیقاً از Address خام یکسان، همان design frame/cohort سه‌موجی و Takmil=1 در هر سه سال ساخته شده است. شمار پنل‌ها {b_ids:,} و تعداد household-yearهای نگه‌داشته‌شده {b_rows:,} است (benchmark {PANEL_B_HH_YEAR_BENCHMARK:,}). از این تعداد، {b_food:,} household-year دارای حداقل یک ردیف food است؛ برای householdهای بدون food table مقدار صفر ساختگی ثبت نشده و `food_matched=0` باقی می‌ماند. Level 1/2 فقط پرچم تشخیصی‌اند.",
        "",
        "All Cross-Section Sample شامل Takmil=1 یا Jaygozin=1 و حداقل یک ردیف food است. رکوردهای ناقص/مبهم بدون کد تأییدی ۱ حذف می‌شوند؛ رکوردهای جانشین با Jaygozin=1 می‌توانند وارد شوند. اگر هر دو کد ۱ باشند، `respondent_kind` تعارض را نگه می‌دارد. خانوار با food rows دارای مقدار مبلغی missing از نمونه حذف نشده است؛ دادهٔ آن همراه پرچم‌های missing در طولی حفظ می‌شود. وزن اصلی `weight` از HBSIR گرفته شده: وزن‌های ۱۳۹۲–۱۳۹۵ از فایل خارجی و ۱۳۹۶–۱۴۰۳ از فیلد وزن خانوار. فیلد خام Access در ۱۳۹۶–۱۴۰۳ برای همهٔ خانوارها با وزن HBSIR منطبق بود؛ `weight_raw`, `access_weight_raw`, و `weight_source` نیز نگه داشته شده‌اند.",
        "",
        "| سال | All Sample | Panel B identified | Panel B food-matched |",
        "|---:|---:|---:|---:|",
    ]
    for y in YEARS:
        lines.append(f"| {y} | {int(all_sample.year.eq(y).sum()):,} | {int(panel_b.year.eq(y).sum()):,} | {int(((panel_b.year.eq(y)) & panel_b.food_matched.eq(1)).sum()):,} |")
    lines += [
        "",
        "## جریان تطبیق و یکتایی",
        "",
        "شمار هر مرحله و تفاوت آن با مرحلهٔ قبل در `analysis_sample_flow.csv` ثبت شده است: raw Access → interview complete → HBSIR household match → food match. تطبیق demographic جدا گزارش می‌شود و missing بودن سرپرست باعث حذف household-year نمی‌شود. تطبیق وزن خام Access با وزن HBSIR در `analysis_weight_reconciliation_1392_1403.csv` آمده است. Household-year files روی `(address_raw, year)` یکتا هستند؛ Panel B روی `(panel_id, year)` یکتا است و هر panel_id سه سال دارد.",
        "",
        "در `food_item_long_all_1392_1403.parquet` ردیف‌های source HBSIR حفظ شده‌اند؛ grain عمداً household-year-code-method را یکتا فرض نمی‌کند، چون یک کالا ممکن است چند روش تهیه/چند ردیف داشته باشد. در itemwide مخارج و مقدار استاندارد در household-year-code و روی همهٔ روش‌ها جمع می‌شوند؛ exp_purchase فقط روش خرید را جمع می‌زند. uv تنها از خریدهای دارای Price_Raw مثبت ساخته می‌شود و اگر چند قیمت باشد، با مقدار معتبر وزن می‌گیرد؛ بدون خرید/قیمت معتبر missing می‌ماند.",
        "",
        "## کدهای کالا و پشتیبانی قیمت/مقدار",
        "",
        f"در ۱۲ سال {n_codes:,} commodity code در food خام مشاهده شده؛ {all12:,} کد در هر ۱۲ سال حضور دارند. خلاصهٔ سالانه برای All و Panel B در `commodity_year_audit_1392_1403.csv` و خلاصهٔ تصمیم گروه‌بندی در `commodity_grouping_summary.csv` است. {total_low:,} کد low purchase و {total_poor:,} کد poor price support بر اساس آستانه‌های زیر flag شده‌اند؛ هیچ‌یک حذف نشده‌اند.",
        "",
        "آستانه‌ها: `low_purchase_flag=1` اگر میانگین نرخ خرید سالانه <۵٪ یا حداقل یک سال <۱٪ باشد. `poor_price_support_flag=1` اگر میانگین نرخ قیمت معتبر بین خریداران <۶۰٪ باشد یا کمتر از نیمی از سال‌های مشاهده‌شده ۳۰ قیمت خانوار معتبر داشته باشند. `unit_value_instability_flag=1` اگر نسبت p90/p10 داخل سال >۱۰ در دست‌کم نیمی از سال‌های دارای قیمت کافی باشد؛ این پراکندگی می‌تواند تفاوت کیفیت/مکان باشد و اثبات اختلاف واحد نیست. `unit_problem_flag=1` اگر سهم Amount fallback ≥۱۰٪ یا `Price_Source` بین ردیف‌ها متنوع باشد؛ این پرچم trigger برای بازبینی است و به‌تنهایی اختلاف واحد را اثبات نمی‌کند. `code_instability_flag` تغییر نام/طبقه یا gap در سال‌های مشاهده را ثبت می‌کند.",
        "",
        "### نمونهٔ کالاهای با خرید کم",
        "",
    ]
    lines += [f"- `{r.commodity_code}` — {r.commodity_name}: میانگین نرخ خرید {r.purchase_rate_mean_all:.1%}" for r in low.itertuples()]
    lines += ["", "### نمونهٔ کالاهای با پشتیبانی قیمت ضعیف", ""]
    lines += [f"- `{r.commodity_code}` — {r.commodity_name}: نرخ قیمت معتبر بین خریداران {r.valid_price_rate_all:.1%}" for r in poor.itertuples()]
    lines += [
        "",
        "## mapping قدیمی",
        "",
        f"در Drive فایل `mapexcel.xlsx` پیدا شد؛ شامل {len(pd.read_csv(OLD_MAPPING_SOURCE))} ردیف و گروه‌های {', '.join(old_source_groups)} است. فایل دقیق با نام `mapexcel_plus_groups7_8_9_group11_updated.xlsx` در Drive/مخزن پیدا نشد؛ بنابراین crosswalk فعلی فقط به نسخهٔ موجود `mapexcel.xlsx` محدود است و گروه‌های ۷ تا ۱۱ آن نسخه را پوشش نمی‌دهد. از این mapping هیچ گروهی به دادهٔ جدید تحمیل نشده است. {covered:,} از {n_codes:,} کد دورهٔ جدید در این نسخهٔ مرجع پیدا شدند؛ {n_codes-covered:,} کد جدید در آن نیستند و {absent_old:,} کد مرجع در دورهٔ جدید مشاهده نشدند. برای crosswalk کاملِ عنوان‌گذاری‌شده، نسخهٔ به‌روزشده لازم است.",
        "",
        "## تفاوت Panel B و All Sample",
        "",
        "گزارش توصیفی سالانه/تجمیعی در `panelB_vs_all_sample_profile.md` و جدول قابل پردازش در `panelB_vs_all_sample_profile.csv` است. مقایسه روی household-yearهای غذایی matched انجام می‌شود؛ All Sample شامل Panel B است. تحصیلات سرپرست بدون harmonization بین‌سالی حفظ شده است؛ pooled education contrast عمداً تولید نشده. مخارج اسمی‌اند و مقایسهٔ pooled آن‌ها اثر تورم را جدا نمی‌کند.",
        "",
        "## فایل‌های خروجی و محدودیت قیمت",
        "",
        "Household-year All و Panel B، food long و itemwideهای دو نمونه ساخته شده‌اند. itemwide شامل `exp_c`, `exp_purchase_c`, `uv_c`, `q_c`, `buy_c` برای هر commodity code است. در سالی که یک کد در food survey اصلاً حضور ندارد، ستونش missing است؛ برای کد موجود با عدم خرید، مخارج صفر و uv missing است. All sample بر اساس completed interview + food-table match ساخته شده؛ Panel B identified محفوظ است و food-missing ردیف‌ها پرچم دارند.",
        "",
        "`amount_raw` از Kilos_Raw و Grams_Raw به گرم-equivalent محاسبه شده و اجزای خام نیز جدا نگه داشته شده‌اند. `amount_standardized` همان مقدار HBSIR است (kg-equivalent؛ fallback Expenditure/Price با flag). `price_raw` از `Price_Raw` منبع cleaned HBSIR و `price_hbsir` نسخهٔ normalized است. خرید، non-market acquisition، صفر قیمت، missing price، مقدار نامعتبر و fallback جدا هستند. این داده‌ها برای تصمیم روش قیمت آماده‌اند، نه برای شاخص قیمت نهایی.",
        "",
        "هیچ کالا بر اساس پرچم حذف نشده؛ QUAIDS/AID، گروه‌بندی نهایی، `exp_system` و price index ساخته نشده‌اند. فایل‌های group-level نهایی `demand_panelB_1392_1403` و `demand_all_1392_1403` عمداً تولید نشده‌اند تا mapping توسط پژوهشگر تأیید شود.",
        "برای تصمیم‌گیری پژوهشگر دربارهٔ گروه‌بندی، زیرساخت داده و ممیزی ۱۲ساله آماده است: کدهای کم‌خرید، پشتیبانی ضعیف قیمت، ناپایداری کد/نام، مقدار fallback و پراکندگی unit value به تفکیک سال ثبت شده‌اند. فایل mapping به‌روزشدهٔ مقالهٔ قبلی در مخزن/Drive موجود نبود؛ crosswalk فعلی صرفاً بر `mapexcel.xlsx` در دسترس تکیه دارد و تأیید mapping به‌روزشده مرحلهٔ بعدی پژوهشگر است.",
        "",
        "### Manifest خروجی",
        "",
        "| فایل | ردیف | بایت |",
        "|---|---:|---:|",
    ]
    for r in manifest.itertuples():
        lines.append(f"| `{r.file}` | {int(r.rows):,} | {int(r.bytes):,} |")
    lines.append("")
    return "\n".join(lines)


def add_rows(manifest: list[dict[str, Any]], path: Path, rows: int) -> None:
    manifest.append({"file": str(path.relative_to(ROOT)), "rows": rows, "bytes": path.stat().st_size if path.exists() else 0})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    all_codes, codes_by_year = commodity_preflight()
    candidate_keys = load_candidate_keys()
    records, flow = load_household_years(candidate_keys)
    weight_rows = []
    for year, group in records.groupby("year", sort=True):
        access_w = number(group["access_weight_raw"])
        hbsir_w = number(group["weight"])
        both = access_w.notna() & hbsir_w.notna()
        match = np.isclose(access_w[both], hbsir_w[both], rtol=1e-10, atol=1e-12)
        weight_rows.append({
            "year": int(year),
            "n_access_weight_nonmissing": int(access_w.notna().sum()),
            "n_hbsir_weight_nonmissing": int(hbsir_w.notna().sum()),
            "n_rows_compared": int(both.sum()),
            "n_exact_weight_matches": int(match.sum()),
            "n_weight_mismatches": int((~match).sum()),
            "match_rate": float(match.mean()) if len(match) else np.nan,
            "weight_source": ";".join(sorted(group["weight_source"].dropna().astype(str).unique())),
            "notes": "1392–1395 use external HBSIR weights; raw Access comparison is available from 1396 onward.",
        })
    all_sample_base = records[
        records["completed_interview"].eq(1) & records["household_table_matched"].eq(1) & records["food_matched"].eq(1)
    ].copy()
    panel_b_base = records[records["panel_B"].eq(1)].copy()
    if all_sample_base.duplicated(["address_raw", "year"]).any():
        raise AssertionError("All Sample has duplicate (address_raw, year)")
    if panel_b_base.duplicated(["panel_id", "year"]).any():
        raise AssertionError("Panel B has duplicate (panel_id, year)")
    if panel_b_base["panel_id"].nunique() != PANEL_B_BENCHMARK or len(panel_b_base) != PANEL_B_HH_YEAR_BENCHMARK:
        raise AssertionError("Panel B row count changed from audited candidate sample")
    panel_b_food_keys = set(panel_b_base.loc[panel_b_base.food_matched.eq(1), "panel_id"].astype(str) + ":" + panel_b_base.loc[panel_b_base.food_matched.eq(1), "year"].astype(str))
    all_keys = set(all_sample_base["panel_id"].astype(str) + ":" + all_sample_base["year"].astype(str))
    if not panel_b_food_keys.issubset(all_keys):
        raise AssertionError("food-matched Panel B household-years are not a subset of All Sample")

    item_long_path = OUT / "food_item_long_all_1392_1403.parquet"
    itemwide_all_path = OUT / "itemwide_all_1392_1403.parquet"
    itemwide_b_path = OUT / "itemwide_panelB_1392_1403.parquet"
    csv_all_path = OUT / "itemwide_all_1392_1403.csv.gz"
    csv_b_path = OUT / "itemwide_panelB_1392_1403.csv.gz"
    planned_outputs = (
        item_long_path,
        itemwide_all_path,
        itemwide_b_path,
        csv_all_path,
        csv_b_path,
        OUT / "household_year_all_1392_1403.parquet",
        OUT / "household_year_panelB_1392_1403.parquet",
        AUDIT / "analysis_sample_flow.csv",
        AUDIT / "analysis_weight_reconciliation_1392_1403.csv",
        AUDIT / "commodity_year_audit_1392_1403.csv",
        AUDIT / "commodity_grouping_summary.csv",
        AUDIT / "old_mapping_crosswalk_1392_1403.csv",
        AUDIT / "panelB_vs_all_sample_profile.md",
        AUDIT / "panelB_vs_all_sample_profile.csv",
        AUDIT / "analysis_dataset_manifest.csv",
        AUDIT / "analysis_dataset_and_commodity_audit_report.md",
        META / "commodity_dictionary_1392_1403.csv",
        META / "household_analysis_variable_dictionary.csv",
        META / "food_item_variable_dictionary_1392_1403.csv",
    )
    existing = [str(path.relative_to(ROOT)) for path in planned_outputs if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing analysis outputs: " + ", ".join(existing)
        )
    pd.DataFrame(weight_rows).to_csv(AUDIT / "analysis_weight_reconciliation_1392_1403.csv", index=False, encoding="utf-8-sig")
    long_writer = wide_all_writer = wide_b_writer = None
    itemwide_all_first = itemwide_b_first = True
    annual_audit_rows: list[dict[str, Any]] = []
    commodity_info: dict[str, dict[str, Any]] = {}
    all_final_parts: list[pd.DataFrame] = []
    b_final_parts: list[pd.DataFrame] = []
    all_wide_rows = b_wide_rows = long_rows = 0
    try:
        for year in YEARS:
            full_food = pd.read_parquet(ROOT / "yearly" / str(year) / "food.parquet")
            update_commodity_dictionary(commodity_info, full_food, year)
            all_y = all_sample_base[all_sample_base["year"].eq(year)].copy()
            b_y = panel_b_base[panel_b_base["year"].eq(year)].copy()
            sample_meta = all_y[["address_raw", "panel_id", "frame", "cohort", "wave", "panel_B", "urban_rural", "province", "weight"]].copy()
            full_food["address_raw"] = full_food["ID"].astype("string")
            food_sample = full_food.merge(sample_meta, on="address_raw", how="inner", validate="many_to_one")
            expected_ids = set(all_y["address_raw"].astype(str))
            if not set(food_sample["address_raw"].astype(str)).issubset(expected_ids):
                raise AssertionError(f"food join produced non-sample household in {year}")
            long = make_food_long(full_food, sample_meta, year)
            long_writer = write_parquet_batch(item_long_path, long, long_writer)
            long_rows += len(long)

            metrics = household_food_metrics(food_sample)
            all_y = all_y.drop(columns=["n_food_rows", "food_exp_observed_total", "n_food_items_positive", "n_food_items_purchased", "n_food_rows_uncoded", "food_exp_uncoded"], errors="ignore").merge(metrics, on="address_raw", how="left", validate="one_to_one")
            b_y = b_y.drop(columns=["n_food_rows", "food_exp_observed_total", "n_food_items_positive", "n_food_items_purchased", "n_food_rows_uncoded", "food_exp_uncoded"], errors="ignore").merge(metrics, on="address_raw", how="left", validate="one_to_one")
            all_y = prepare_household_output(all_y)
            b_y = prepare_household_output(b_y)
            all_final_parts.append(all_y)
            b_final_parts.append(b_y)

            annual_codes = sorted(codes_by_year[year])
            rows_a, agg_a = item_audit_rows(food_sample, all_y, annual_codes, "All_Cross_Section", year)
            b_food = food_sample[food_sample["panel_B"].eq(1)].copy()
            b_matched = b_y[b_y["food_matched"].eq(1)].copy()
            rows_b, agg_b = item_audit_rows(b_food, b_matched, annual_codes, "Panel_B", year)
            annual_audit_rows.extend(rows_a)
            annual_audit_rows.extend(rows_b)

            wide_a = make_itemwide(all_y, agg_a, all_codes, codes_by_year[year])
            wide_b = make_itemwide(b_y, agg_b, all_codes, codes_by_year[year])
            if wide_a.duplicated(["address_raw", "year"]).any() or wide_b.duplicated(["panel_id", "year"]).any():
                raise AssertionError(f"itemwide key duplicated in {year}")
            wide_all_writer = write_parquet_batch(itemwide_all_path, wide_a, wide_all_writer)
            wide_b_writer = write_parquet_batch(itemwide_b_path, wide_b, wide_b_writer)
            write_csv_gzip_batch(csv_all_path, wide_a, itemwide_all_first)
            write_csv_gzip_batch(csv_b_path, wide_b, itemwide_b_first)
            itemwide_all_first = itemwide_b_first = False
            all_wide_rows += len(wide_a)
            b_wide_rows += len(wide_b)
            flow.loc[(flow["sample"].eq("All_Cross_Section")) & flow.year.eq(year) & flow.stage.eq("final_household_year_all"), "item_level_rows"] = len(long)
            flow.loc[(flow["sample"].eq("Panel_B")) & flow.year.eq(year) & flow.stage.eq("food_table_matched"), "item_level_rows"] = len(b_food)
            print(f"built food year {year}: all_hh={len(all_y):,} panelB={len(b_y):,} food_rows={len(long):,} codes={len(annual_codes):,}", flush=True)
    finally:
        for writer in (long_writer, wide_all_writer, wide_b_writer):
            if writer is not None:
                writer.close()

    all_final = pd.concat(all_final_parts, ignore_index=True, sort=False)
    b_final = pd.concat(b_final_parts, ignore_index=True, sort=False)
    if all_final.duplicated(["address_raw", "year"]).any() or b_final.duplicated(["panel_id", "year"]).any():
        raise AssertionError("final household-year files violate uniqueness keys")
    panel_counts = b_final.groupby("panel_id")["year"].nunique()
    if len(panel_counts) != PANEL_B_BENCHMARK or not panel_counts.eq(3).all() or len(b_final) != PANEL_B_HH_YEAR_BENCHMARK:
        raise AssertionError("final Panel B must preserve 46,347 households × three years")
    all_final.to_parquet(OUT / "household_year_all_1392_1403.parquet", index=False, compression="zstd")
    b_final.to_parquet(OUT / "household_year_panelB_1392_1403.parquet", index=False, compression="zstd")
    write_dictionaries(all_final)

    # The remaining food-stage counts are household counts separately from item rows.
    for year in YEARS:
        fpath = ROOT / "yearly" / str(year) / "food.parquet"
        if not fpath.exists():
            raise FileNotFoundError(fpath)
    flow["n_lost_from_previous_stage"] = pd.to_numeric(flow["n_lost_from_previous_stage"], errors="coerce")
    flow.to_csv(AUDIT / "analysis_sample_flow.csv", index=False, encoding="utf-8-sig")

    annual_audit = pd.DataFrame(annual_audit_rows)
    annual_audit["_code_sort"] = pd.to_numeric(annual_audit["commodity_code"], errors="coerce")
    annual_audit = annual_audit.sort_values(["year", "_code_sort", "sample"]).drop(columns="_code_sort").reset_index(drop=True)
    annual_audit.to_csv(AUDIT / "commodity_year_audit_1392_1403.csv", index=False, encoding="utf-8-sig")
    dictionary = build_commodity_dictionary(commodity_info)
    dictionary.to_csv(META / "commodity_dictionary_1392_1403.csv", index=False, encoding="utf-8-sig")
    crosswalk = create_old_crosswalk(dictionary)
    crosswalk.to_csv(AUDIT / "old_mapping_crosswalk_1392_1403.csv", index=False, encoding="utf-8-sig")
    grouping = build_grouping_summary(annual_audit, dictionary, crosswalk)
    grouping.to_csv(AUDIT / "commodity_grouping_summary.csv", index=False, encoding="utf-8-sig")
    total_spend = annual_audit[annual_audit["sample"].eq("All_Cross_Section")].groupby("commodity_code")["expenditure_sum_reported_all_provisions"].sum().sort_values(ascending=False)
    top_codes = total_spend.head(20).index.astype(str).tolist()
    profile, profile_md = profile_rows(all_final, b_final, annual_audit, top_codes)
    profile.to_csv(AUDIT / "panelB_vs_all_sample_profile.csv", index=False, encoding="utf-8-sig")
    (AUDIT / "panelB_vs_all_sample_profile.md").write_text(profile_md, encoding="utf-8")

    # Final round-trip checks for the long and wide files.
    long_meta = pq.read_metadata(item_long_path)
    all_wide_meta = pq.read_metadata(itemwide_all_path)
    b_wide_meta = pq.read_metadata(itemwide_b_path)
    if long_meta.num_rows != long_rows or all_wide_meta.num_rows != len(all_final) or b_wide_meta.num_rows != len(b_final):
        raise AssertionError("Parquet row counts do not match the in-memory output counts")
    required_long = {"address_raw", "panel_id", "year", "commodity_code", "commodity_name", "provision_method", "amount_raw", "amount_standardized", "price_raw", "expenditure_raw", "unit_value", "urban_rural", "province", "weight", "panel_B"}
    if not required_long.issubset(set(pq.read_schema(item_long_path).names)):
        raise AssertionError("food long is missing required columns")
    duplicate_source_grain = 0
    # No uniqueness assumption: this is a reported diagnostic only.
    for year in (1392, 1403):
        f = pd.read_parquet(ROOT / "yearly" / str(year) / "food.parquet", columns=["ID", "Commodity_Code", "Provision_Method"])
        codes = clean_code_series(f["Commodity_Code"])
        key = pd.DataFrame({"ID": f["ID"].astype("string"), "code": codes, "method": f["Provision_Method"].astype("string")})
        duplicate_source_grain += int(key.duplicated().sum())

    manifest_rows = []
    add_rows(manifest_rows, OUT / "household_year_all_1392_1403.parquet", len(all_final))
    add_rows(manifest_rows, OUT / "household_year_panelB_1392_1403.parquet", len(b_final))
    add_rows(manifest_rows, item_long_path, long_rows)
    add_rows(manifest_rows, itemwide_all_path, all_wide_rows)
    add_rows(manifest_rows, itemwide_b_path, b_wide_rows)
    add_rows(manifest_rows, csv_all_path, all_wide_rows)
    add_rows(manifest_rows, csv_b_path, b_wide_rows)
    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(AUDIT / "analysis_dataset_manifest.csv", index=False, encoding="utf-8-sig")
    (AUDIT / "analysis_dataset_and_commodity_audit_report.md").write_text(
        report_text(dictionary, annual_audit, grouping, crosswalk, all_final, b_final, flow, manifest), encoding="utf-8"
    )
    print(json.dumps({
        "panel_B_ids": b_final.panel_id.nunique(),
        "panel_B_household_years": len(b_final),
        "panel_B_food_matched": int(b_final.food_matched.sum()),
        "all_sample_household_years": len(all_final),
        "food_long_rows": long_rows,
        "commodity_codes": len(dictionary),
        "commodity_codes_all_12_years": int(dictionary.years_observed.astype("string").str.split(";").map(len).eq(12).sum()),
        "duplicate_source_address_year_code_method_diagnostic_1392_and_1403": duplicate_source_grain,
        "itemwide_csv_gz": [csv_all_path.stat().st_size, csv_b_path.stat().st_size],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
