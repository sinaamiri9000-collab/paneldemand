from __future__ import annotations

import csv
import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import hbsir
import numpy as np
import pandas as pd

from common import ROOT, config, path, write_json


TABLES = {
    "household_information": "household.parquet",
    "members_properties": "members.parquet",
    "food": "food.parquet",
    "employment_income": "income_wage.parquet",
    "self_employed_income": "income_self_employed.parquet",
    "other_income": "income_other.parquet",
    "subsidy": "income_subsidy.parquet",
    "house_specifications": "housing.parquet",
}


def sha256(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def set_hbsir_paths() -> None:
    base = path("intermediate")
    d = hbsir.api.defaults.dir
    d.original = path("raw")
    d.unpacked = base / "unpacked"
    d.extracted = base / "extracted"
    d.cleaned = base / "cleaned"
    d.external = base / "external"
    d.cached = base / "cache"
    d.maps = base / "maps"
    for p in (d.unpacked, d.extracted, d.cleaned, d.external, d.cached, d.maps):
        p.mkdir(parents=True, exist_ok=True)


def load_hbsir(name: str, year: int, form: str) -> pd.DataFrame:
    return hbsir.api.load_table(
        name,
        years=year,
        form=form,
        on_missing="download",
        save_downloaded=True,
        save_created=True,
        recreate=False,
    )


def merge_source_columns(cleaned: pd.DataFrame, normalized: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    raw = cleaned.copy()
    norm = normalized.copy()
    keys = [c for c in ["ID", "Commodity_Code", "Provision_Method", "Expenditure"] if c in raw and c in norm]
    if not keys:
        return norm, len(norm)

    def keys_for(frame: pd.DataFrame) -> pd.Series:
        parts = [frame[k].astype("string").fillna("<NULL>") for k in keys]
        key = parts[0]
        for part in parts[1:]:
            key = key + "\x1f" + part
        return key

    raw["__match_key"] = keys_for(raw)
    norm["__match_key"] = keys_for(norm)
    raw["__occurrence"] = raw.groupby("__match_key", sort=False, dropna=False).cumcount()
    norm["__occurrence"] = norm.groupby("__match_key", sort=False, dropna=False).cumcount()
    carry = [c for c in ["Kilos", "Grams", "Price"] if c in raw.columns]
    renames = {"Kilos": "Kilos_Raw", "Grams": "Grams_Raw", "Price": "Price_Raw"}
    raw_part = raw[["__match_key", "__occurrence", *carry]].rename(columns=renames)
    raw_part["__raw_row_matched"] = True
    merged = norm.merge(raw_part, on=["__match_key", "__occurrence"], how="left", validate="one_to_one", sort=False)
    unmatched = int(merged["__raw_row_matched"].isna().sum())
    merged.drop(columns=["__match_key", "__occurrence", "__raw_row_matched"], inplace=True)
    return merged, unmatched


def add_food_labels(food: pd.DataFrame) -> pd.DataFrame:
    result = hbsir.api.add_classification(
        food,
        target="Commodity_Code",
        name="original",
        aspects="farsi_name",
        levels=[1, 2, 3, 4],
    )
    renames = {
        "farsi_name_1": "HBSIR_Category_Level_1",
        "farsi_name_2": "HBSIR_Category_Level_2",
        "farsi_name_3": "HBSIR_Category_Level_3",
        "farsi_name_4": "Commodity_Name",
    }
    return result.rename(columns=renames)


def add_household_source_weight(cleaned: pd.DataFrame, normalized: pd.DataFrame) -> pd.DataFrame:
    raw = cleaned[[c for c in ["ID", "Weight"] if c in cleaned.columns]].copy()
    raw = raw.rename(columns={"Weight": "Weight_Raw"})
    norm = normalized.copy()
    if "Weight" in norm.columns:
        norm.rename(columns={"Weight": "HBSIR_Weight"}, inplace=True)
    if "Weight_Raw" not in raw:
        norm["Weight_Raw"] = pd.NA
        norm["Weight"] = norm.get("HBSIR_Weight")
        year = int(norm["Year"].iloc[0]) if len(norm) else 0
        norm["Weight_Source"] = (
            "HBSIR_external_weight_table_pre_1396"
            if year < 1396
            else "HBSIR_normalized_weight_source_unavailable_in_clean_table"
        )
        return norm
    raw["__occurrence"] = raw.groupby("ID", sort=False, dropna=False).cumcount()
    norm["__occurrence"] = norm.groupby("ID", sort=False, dropna=False).cumcount()
    norm = norm.merge(raw, on=["ID", "__occurrence"], how="left", validate="one_to_one", sort=False)
    norm.drop(columns="__occurrence", inplace=True)
    # Keep the documented HBSIR Weight column as the analysis-ready field, while
    # retaining the source-table Weight separately whenever that field exists.
    norm["Weight"] = norm["HBSIR_Weight"]
    year = int(norm["Year"].iloc[0]) if len(norm) else 0
    norm["Weight_Source"] = (
        "HBSIR_external_weight_table_pre_1396"
        if year < 1396
        else "survey_weight_field_in_HBSIR_cleaned_household_table"
    )
    return norm


def read_raw_manifest() -> dict[int, dict]:
    file = ROOT / "metadata/raw_sources.csv"
    if not file.exists():
        return {}
    return {int(row["Year"]): row for row in csv.DictReader(file.open(encoding="utf-8-sig"))}


def clean_cache_provenance(year: int, table: str) -> dict:
    file = path("intermediate") / "cleaned" / f"{year}_{table}.parquet"
    mirrors = config()["sources"]["mirrors"]
    base = mirrors[0]["base_url"].rsplit("/1_original", 1)[0] + "/4_cleaned"
    if not file.exists():
        return {"table": table, "file": file.name, "status": "not_cached"}
    return {
        "table": table,
        "file": file.name,
        "source_url": f"{base}/{file.name}",
        "source_kind": "HBSIR maintained cleaned-table mirror",
        "size_bytes": file.stat().st_size,
        "sha256": sha256(file),
    }


def as_year(table: pd.DataFrame, year: int) -> pd.DataFrame:
    result = table.copy()
    if "Year" not in result.columns:
        result.insert(0, "Year", year)
    ordered = [c for c in ["Year", "ID", "Member_Number"] if c in result.columns]
    remaining = [c for c in result.columns if c not in ordered]
    result = result[ordered + remaining]
    return result


def main() -> int:
    set_hbsir_paths()
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    raw_manifest = read_raw_manifest()
    issues: list[dict] = []
    cleaned_sources: list[dict] = []
    for year in range(start, end + 1):
        out_dir = path("yearly") / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)
        statuses: dict[str, dict] = {}
        frames: dict[str, pd.DataFrame] = {}
        cleaned_tables: dict[str, pd.DataFrame] = {}
        for table in TABLES:
            try:
                cleaned = load_hbsir(table, year, "cleaned")
                cleaned_tables[table] = cleaned
                normalized = load_hbsir(table, year, "normalized")
                frames[table] = as_year(normalized, year)
                statuses[table] = {"status": "processed", "cleaned_rows": len(cleaned), "normalized_rows": len(normalized), "columns": list(normalized.columns)}
                cleaned_sources.append({"Year": year, **clean_cache_provenance(year, table)})
            except Exception as exc:
                statuses[table] = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:500]}
                issues.append({"Year": year, "Scope": table, "Issue": "hbsir_table_failure", "Severity": "blocking_for_table", "Details": f"{type(exc).__name__}: {str(exc)[:500]}"})

        if "household_information" not in frames and "household_information" in cleaned_tables:
            hh = cleaned_tables["household_information"].copy()
            hh.insert(0, "Year", year)
            if "Season_Number" in hh:
                try:
                    from hbsir.schema_functions.standard_tables import season_name
                    hh = season_name(hh)
                except Exception as exc:
                    issues.append({"Year": year, "Scope": "household_information.Season", "Issue": "season_name_fallback_failed", "Severity": "warning", "Details": type(exc).__name__})
            hh["HBSIR_Weight"] = pd.NA
            frames["household_information"] = hh
            statuses["household_information"]["fallback"] = "cleaned table with HBSIR season_name; normalized weight table unavailable"

        if "household_information" in frames:
            hh = frames["household_information"].copy()
            cleaned = cleaned_tables.get("household_information")
            if cleaned is not None:
                try:
                    hh = add_household_source_weight(cleaned, hh)
                except Exception as exc:
                    issues.append({"Year": year, "Scope": "household_information.Weight", "Issue": "raw_weight_alignment_failed", "Severity": "warning", "Details": type(exc).__name__})
            for name, kwargs in [
                ("Urban_Rural", {}),
                ("Province", {"aspects": ["name", "farsi_name"], "column_names": ["Province", "Province_Farsi"]}),
                ("County", {"aspects": ["name", "farsi_name"], "column_names": ["County", "County_Farsi"]}),
            ]:
                try:
                    hh = hbsir.api.add_attribute(hh, name=name, **kwargs)
                except Exception as exc:
                    issues.append({"Year": year, "Scope": f"household_information.{name}", "Issue": "attribute_decode_failed", "Severity": "warning", "Details": f"{type(exc).__name__}: {str(exc)[:300]}"})
            frames["household_information"] = hh

        if "household_information" in frames and "members_properties" in frames:
            hh = frames["household_information"].copy()
            member_counts = (
                frames["members_properties"].groupby("ID", dropna=False)
                .size().rename("Household_Size").reset_index()
            )
            hh = hh.merge(member_counts, on="ID", how="left", validate="one_to_one", sort=False)
            frames["household_information"] = hh

        if "food" in frames:
            food = frames["food"].copy()
            clean_food = cleaned_tables.get("food")
            if clean_food is not None:
                food, unmatched = merge_source_columns(clean_food, food)
                if unmatched:
                    issues.append({"Year": year, "Scope": "food", "Issue": "raw_food_source_alignment", "Severity": "warning", "Details": f"{unmatched} normalized rows have missing raw Kilos; key-based alignment used."})
            try:
                food = add_food_labels(food)
            except Exception as exc:
                issues.append({"Year": year, "Scope": "food.commodity_classification", "Issue": "classification_failed", "Severity": "warning", "Details": f"{type(exc).__name__}: {str(exc)[:300]}"})
            if "Amount" in food:
                observed = pd.Series(False, index=food.index)
                for column in ("Kilos_Raw", "Grams_Raw"):
                    if column in food:
                        observed |= food[column].notna()
                raw_price = pd.to_numeric(food.get("Price_Raw"), errors="coerce") if "Price_Raw" in food else pd.Series(np.nan, index=food.index)
                fallback = (~observed) & food["Amount"].notna() & raw_price.gt(0)
                food["Amount_Source"] = np.select([observed, fallback], ["HBSIR_Kilos_Grams", "HBSIR_Expenditure_divided_by_Price"], default="missing")
            if "Price_Raw" in food:
                food["Price_Source"] = "survey_price_field_in_HBSIR_cleaned_table; raw_access_not_decoded"
            frames["food"] = food

        outputs: dict[str, dict] = {}
        for table, outfile in TABLES.items():
            frame = frames.get(table)
            if frame is None:
                outputs[outfile] = {"status": "not_created", "reason": statuses.get(table, {}).get("error", "table unavailable")}
                continue
            target = out_dir / outfile
            frame = as_year(frame, year)
            frame.to_parquet(target, index=False)
            outputs[outfile] = {"status": "created", "rows": len(frame), "columns": list(frame.columns), "size_bytes": target.stat().st_size, "sha256": sha256(target)}

        raw = raw_manifest.get(year, {})
        metadata = {
            "year": year,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "raw_archive": {k: raw.get(k, "") for k in ["Status", "Source", "Official_URL", "Actual_URL", "File_Name", "File_Size_Bytes", "SHA256", "Archive_Signature"]},
            "hbsir": cfg["hbsir"],
            "standardization_method": "HBSIR-maintained cleaned parquet mirror downloaded into the local cache, followed by HBSIR load_table(form='normalized'); no HBSIR code edits.",
            "raw_archive_warning": "The original archive bytes are preserved and hashed. Official endpoints returned HTTP 503, so the documented HBSIR mirror supplied each archive. The normalized tables were built from HBSIR cleaned-table mirrors, not independently re-extracted from the preserved Access archive.",
            "weight_definition": "Weight is the HBSIR normalized weight. HBSIR documents externally supplied weight tables before 1396 and household-table weights from 1396 onward; Weight_Raw is retained when present in the HBSIR cleaned input.",
            "food_source_definition": "Kilos_Raw, Grams_Raw, and Price_Raw are carried from the HBSIR cleaned table (not independently decoded from the preserved Access archive). Amount is the HBSIR normalized field, with Amount_Source identifying its derivation.",
            "tables": statuses,
            "outputs": outputs,
            "limitations": ["Raw Access archive is preserved separately. HBSIR pre-cleaned tables are used because this runtime lacks an Access ODBC driver; direct raw-to-cleaned extraction has not been independently reproduced."],
        }
        write_json(out_dir / "metadata.json", metadata)
        checksums = []
        for file in sorted(out_dir.iterdir()):
            if file.is_file() and file.name != "checksums.sha256":
                checksums.append(f"{sha256(file)}  {file.name}")
        (out_dir / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
        print(f"{year}: " + ", ".join(f"{name}={value.get('rows','NA')}" for name, value in outputs.items() if value["status"] == "created"), flush=True)

    issue_path = path("audit") / "issues_log.csv"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(issues, columns=["Year", "Scope", "Issue", "Severity", "Details"]).to_csv(issue_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(cleaned_sources).to_csv(ROOT / "metadata/hbsir_cleaned_sources.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
