from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc

from common import ROOT, append_issues, path


YEAR = 1402
MDB_RELATIVE = Path("intermediate/extracted/1402/HB1402_14030707.mdb")
EXTRA_RAW_FIELDS = [
    "TakmilDescA",
    "TakmilDescB",
    "TakmilDescC",
    "JaygozinDescA",
    "JaygozinDescB",
    "BlkAbdJaygozin",
    "RadifJaygozin",
]
TABLES = {
    "household": ["R1402Data", "U1402Data"],
    "members": ["R1402P1", "U1402P1"],
    "housing": ["R1402P2", "U1402P2"],
    "food": ["R1402P3S01", "U1402P3S01"],
    "income_wage": ["R1402P4S01", "U1402P4S01"],
    "income_self_employed": ["R1402P4S02", "U1402P4S02"],
    "income_other": ["R1402P4S03", "U1402P4S03"],
    "income_subsidy": ["R1402P4S04", "U1402P4S04"],
    "tobacco_separate_from_hbsir_food": ["R1402P3S02", "U1402P3S02"],
}
STANDARD_FILES = {
    "household": "household.parquet",
    "members": "members.parquet",
    "housing": "housing.parquet",
    "food": "food.parquet",
    "income_wage": "income_wage.parquet",
    "income_self_employed": "income_self_employed.parquet",
    "income_other": "income_other.parquet",
    "income_subsidy": "income_subsidy.parquet",
}


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quote(name: str) -> str:
    return "[" + name.replace("]", "]]" ) + "]"


def to_text(value: object) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result if result else None


def read_scalar_column(cursor: pyodbc.Cursor, table: str, column: str) -> Counter:
    cursor.execute(f"SELECT {quote(column)} FROM {quote(table)}")
    values = Counter()
    for row in cursor:
        value = to_text(row[0])
        values["<NULL>" if value is None else value] += 1
    return values


def main() -> int:
    mdb = ROOT / MDB_RELATIVE
    if not mdb.is_file():
        raise FileNotFoundError(
            f"Expected locally extracted raw Access database at {mdb}. "
            "Extract the nested 1402 archive from raw/1402/data.rar first."
        )
    drivers = pyodbc.drivers()
    if "MDBTools" not in drivers:
        raise RuntimeError(
            "MDBTools ODBC driver is unavailable. Install/configure MDBTools and set "
            "ODBCSYSINI/ODBCINSTINI/LD_LIBRARY_PATH as documented in README.md."
        )

    connection = pyodbc.connect(f"DRIVER={{MDBTools}};DBQ={mdb};")
    cursor = connection.cursor()
    tables = {str(row[2]) for row in cursor.tables() if str(row[3]).upper() == "TABLE"}
    table_count_rows: list[dict] = []
    table_count_by_name: dict[str, int] = {}
    for concept, raw_tables in TABLES.items():
        observed = 0
        for raw_table in raw_tables:
            if raw_table not in tables:
                raise KeyError(f"Expected raw Access table is missing: {raw_table}")
            cursor.execute(f"SELECT COUNT(*) FROM {quote(raw_table)}")
            count = int(cursor.fetchone()[0])
            observed += count
            table_count_by_name[raw_table] = count
            table_count_rows.append({"Year": YEAR, "Concept": concept, "Raw_Table": raw_table, "Raw_Rows": count})
        if concept in STANDARD_FILES:
            output = pd.read_parquet(path("yearly") / str(YEAR) / STANDARD_FILES[concept])
            standardized = len(output)
            match = observed == standardized
            table_count_rows.append({
                "Year": YEAR,
                "Concept": concept,
                "Raw_Table": "R+U source-table sum",
                "Raw_Rows": observed,
                "Standardized_Table": STANDARD_FILES[concept],
                "Standardized_Rows": standardized,
                "Counts_Match": match,
            })
            if not match:
                raise AssertionError(
                    f"{concept}: raw R/U row count {observed} != standardized row count {standardized}"
                )
        else:
            table_count_rows.append({
                "Year": YEAR,
                "Concept": concept,
                "Raw_Table": "R+U source-table sum",
                "Raw_Rows": observed,
                "Standardized_Table": "not included in HBSIR food table",
                "Standardized_Rows": 0,
                "Counts_Match": "separate source domain",
            })

    # Preserve official raw sample-design detail omitted from HBSIR household output.
    # Existing HBSIR-standardized columns remain as-is; added fields retain raw values.
    households: list[pd.DataFrame] = []
    raw_design_counts: dict[str, dict[str, int]] = {
        field: {"nonmissing": 0, "rows": 0} for field in EXTRA_RAW_FIELDS
    }
    raw_key_count = 0
    for raw_table in TABLES["household"]:
        columns = ["Address", "Weight", "NoeKhn", "Takmil", "Jaygozin", "Fasl", *EXTRA_RAW_FIELDS]
        sql = ", ".join(quote(column) for column in columns)
        cursor.execute(f"SELECT {sql} FROM {quote(raw_table)}")
        raw = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
        raw_key_count += len(raw)
        raw["ID"] = pd.to_numeric(raw["Address"], errors="coerce").astype("UInt64")
        for field in EXTRA_RAW_FIELDS:
            raw_design_counts[field]["nonmissing"] += int(raw[field].map(to_text).notna().sum())
            raw_design_counts[field]["rows"] += int(len(raw))
        households.append(raw)
    raw_households = pd.concat(households, ignore_index=True)
    hh_path = path("yearly") / str(YEAR) / "household.parquet"
    hh = pd.read_parquet(hh_path)
    if raw_households["ID"].duplicated().any():
        raise AssertionError("Raw Access household Address is not unique within 1402.")
    raw_index = raw_households.set_index("ID")
    if len(hh) != hh["ID"].nunique() or set(hh["ID"].astype("UInt64")) != set(raw_index.index):
        raise AssertionError("Raw Access Address set does not exactly match HBSIR household IDs.")

    raw_weight = raw_index.loc[hh["ID"].astype("UInt64"), "Weight"].astype(float).to_numpy()
    hbsir_weight = pd.to_numeric(hh["HBSIR_Weight"], errors="coerce").to_numpy(dtype=float)
    weight_mismatch = int((~np.isclose(raw_weight, hbsir_weight, rtol=1e-12, atol=1e-10, equal_nan=True)).sum())
    if weight_mismatch:
        raise AssertionError(f"Raw Access Weight mismatches HBSIR_Weight in {weight_mismatch} households.")

    aligned = raw_index.loc[hh["ID"].astype("UInt64")]
    raw_fasl = pd.to_numeric(aligned["Fasl"], errors="coerce").to_numpy()
    season = pd.to_numeric(hh["Season_Number"], errors="coerce").to_numpy()
    season_mismatch = int((~np.isclose(raw_fasl, season, equal_nan=True)).sum())
    if season_mismatch:
        raise AssertionError(f"Raw Access Fasl mismatches Season_Number in {season_mismatch} households.")

    for source, standard, true_code in [
        ("NoeKhn", "Household_Type", {"1": "Normal", "2": "Group"}),
        ("Takmil", "Main_Household", None),
        ("Jaygozin", "Alternative_Household", None),
    ]:
        source_values = aligned[source].map(to_text)
        if standard == "Household_Type":
            expected = source_values.map(true_code)
            actual = hh[standard].astype("string").reset_index(drop=True)
            mismatch = int((expected.reset_index(drop=True) != actual).sum())
        else:
            expected = source_values.map(lambda value: value == "1").astype("boolean")
            actual = hh[standard].astype("boolean").reset_index(drop=True)
            mismatch = int((expected.reset_index(drop=True) != actual).fillna(False).sum())
        if mismatch:
            raise AssertionError(f"Raw Access {source} mismatches HBSIR {standard} in {mismatch} households.")

    added_columns = []
    for field in EXTRA_RAW_FIELDS:
        output_name = f"Raw_{field}"
        hh[output_name] = aligned[field].map(to_text).to_numpy()
        added_columns.append(output_name)
    hh.to_parquet(hh_path, index=False, compression="zstd")

    subsidy_raw = Counter()
    for raw_table in TABLES["income_subsidy"]:
        subsidy_raw.update(read_scalar_column(cursor, raw_table, "Dycol01"))
    subsidy_out = pd.read_parquet(path("yearly") / str(YEAR) / "income_subsidy.parquet")
    standardized_member1 = int(pd.to_numeric(subsidy_out["Member_Number"], errors="coerce").eq(1).sum())
    raw_member1_count = sum(
        count for code, count in subsidy_raw.items()
        if code != "<NULL>" and code.isdigit() and int(code) == 1
    )
    raw_member323_count = sum(
        count for code, count in subsidy_raw.items()
        if code != "<NULL>" and code.isdigit() and int(code) == 323
    )
    expected_member1 = int(raw_member1_count + raw_member323_count)

    selfemp_raw = Counter()
    for raw_table in TABLES["income_self_employed"]:
        selfemp_raw.update(read_scalar_column(cursor, raw_table, "DYCOL05"))
    selfemp_out = pd.read_parquet(path("yearly") / str(YEAR) / "income_self_employed.parquet")
    selfemp_codes = {
        "raw_code_counts": {k: v for k, v in sorted(selfemp_raw.items())},
        "standardized_label_counts": {
            str(k): int(v) for k, v in selfemp_out["Employment_Type"].value_counts(dropna=False).items()
        },
    }
    subsidy_recode_matches = standardized_member1 == expected_member1

    food_columns: dict[str, list[str]] = {}
    for raw_table in TABLES["food"]:
        cursor.execute(f"SELECT * FROM {quote(raw_table)} WHERE 1=0")
        food_columns[raw_table] = [str(item[0]) for item in cursor.description]
    food_raw_dycol07 = "present" if any(any(c.casefold() == "dycol07" for c in cols) for cols in food_columns.values()) else "absent"
    connection.close()

    # Update dictionary only for the raw fields absent from the HBSIR standard schema.
    dictionary_path = path("metadata") / "variable_dictionary.csv"
    dictionary = pd.read_csv(dictionary_path, encoding="utf-8-sig", dtype=str).fillna("")
    extras = []
    for field in EXTRA_RAW_FIELDS:
        if not dictionary["Column_Standardized"].eq(f"Raw_{field}").any():
            extras.append({
                "Year_Range": "1402",
                "Table_Raw": "household_information",
                "Column_Raw": field,
                "Table_HBSIR": "household_information",
                "Column_Standardized": f"Raw_{field}",
                "Transformation_Type": "retained raw source field; no recoding",
                "Description": "Read directly from original 1402 Access household table; HBSIR normalized output omits this design/replacement detail.",
            })
    if extras:
        dictionary = pd.concat([dictionary, pd.DataFrame(extras)], ignore_index=True)
        dictionary.to_csv(dictionary_path, index=False, encoding="utf-8-sig")

    metadata_path = path("yearly") / str(YEAR) / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["direct_raw_access_validation"] = {
        "database_relative_path": MDB_RELATIVE.as_posix(),
        "database_sha256": sha256(mdb),
        "method": "MDBTools ODBC read of original Access database nested in unchanged official-archive mirror bytes",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "household_raw_columns_added": added_columns,
        "household_rows_key_matched": int(len(hh)),
        "weight_value_mismatches": weight_mismatch,
        "season_value_mismatches": season_mismatch,
        "subsidy_DYCOL01_323_count": raw_member323_count,
        "subsidy_DYCOL01_1_count": raw_member1_count,
        "subsidy_member_1_after_HBSIR_recode_count": standardized_member1,
        "subsidy_member_1_expected_count_after_HBSIR_recode": expected_member1,
        "subsidy_323_recode_count_matches": subsidy_recode_matches,
        "self_employed_DYCOL05": selfemp_codes,
        "food_DYCOL07_raw_field_presence": food_raw_dycol07,
        "note": "Direct raw-to-HBSIR row counts and selected household mapping/code checks; years 1390-1401 and 1403 remain standardized from documented HBSIR cleaned mirrors.",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    year_dir = path("yearly") / str(YEAR)
    checksum_rows = []
    for file in sorted(year_dir.iterdir()):
        if file.is_file() and file.name not in {"checksums.sha256"}:
            checksum_rows.append(f"{sha256(file)}  {file.name}")
    (year_dir / "checksums.sha256").write_text("\n".join(checksum_rows) + "\n", encoding="utf-8")

    audit = path("audit")
    audit.mkdir(parents=True, exist_ok=True)
    counts_path = audit / "direct_1402_access_table_counts.csv"
    pd.DataFrame(table_count_rows).to_csv(counts_path, index=False, encoding="utf-8-sig")
    summary = {
        "year": YEAR,
        "source_archive": "raw/1402/data.rar",
        "archive_sha256": sha256(path("raw") / "1402/data.rar"),
        "access_database_sha256": sha256(mdb),
        "access_tables_available": len(tables),
        "raw_standardized_table_count_checks": {
            row["Concept"]: row.get("Counts_Match")
            for row in table_count_rows
            if row["Concept"] in STANDARD_FILES and row["Raw_Table"] == "R+U source-table sum"
        },
        "household_address_unique_rows": raw_key_count,
        "household_addresses_match_standardized_ids": True,
        "weight_value_mismatches": weight_mismatch,
        "season_value_mismatches": season_mismatch,
        "raw_household_design_fields_added": added_columns,
        "raw_household_design_field_nonmissing_counts": raw_design_counts,
        "subsidy_323_count": raw_member323_count,
        "subsidy_1_raw_count": raw_member1_count,
        "subsidy_raw_code_counts": dict(sorted(subsidy_raw.items())),
        "subsidy_recode_matches": subsidy_recode_matches,
        "self_employment_type_codes": selfemp_codes,
        "food_DYCOL07_presence_in_original_Access": food_raw_dycol07,
        "separate_tobacco_source_rows": sum(table_count_by_name[n] for n in TABLES["tobacco_separate_from_hbsir_food"]),
        "privacy": "This file contains aggregate counts only; household-level source fields are retained only in yearly/1402/household.parquet.",
    }
    summary_path = audit / "direct_1402_access_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    issues = []
    if not subsidy_recode_matches:
        issues.append({"Year": YEAR, "Scope": "income_subsidy.DYCOL01", "Issue": "raw_HBSIR_323_recode_count_mismatch", "Severity": "warning", "Details": f"Raw numeric-code 323 count={raw_member323_count}; raw numeric-code 1 count={raw_member1_count}; standardized Member_Number=1 count={standardized_member1}."})
    if food_raw_dycol07 == "absent":
        issues.append({"Year": YEAR, "Scope": "food.DYCOL07", "Issue": "dropped_field_not_present_in_1402_access_schema", "Severity": "information", "Details": "HBSIR metadata declares DYCOL07 dropped across the series; this column was absent from the 1402 P3S01 Access schema, so there is no 1402 record count to report."})
    append_issues(issues)
    print(f"Direct raw Access validation written: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
