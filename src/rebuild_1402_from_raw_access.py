from __future__ import annotations

from collections import Counter
from pathlib import Path

import hbsir
import numpy as np
import pandas as pd

from common import ROOT, config, path


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
MDB = Path("intermediate/extracted/1402/HB1402_14030707.mdb")


def canonical_value(value: object) -> str:
    if pd.isna(value):
        return "<NA>"
    if isinstance(value, (bool, np.bool_)):
        return "1" if bool(value) else "0"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return "<NA>"
        return format(float(value), ".17g")
    return str(value)


def row_multiset(frame: pd.DataFrame, columns: list[str]) -> Counter:
    selected = frame[columns].reset_index(drop=True)
    return Counter(
        tuple(canonical_value(value) for value in row)
        for row in selected.itertuples(index=False, name=None)
    )


def main() -> int:
    mdb_path = ROOT / MDB
    if not mdb_path.is_file():
        raise FileNotFoundError(
            f"Expected raw Access database {mdb_path}; first extract the nested RAR from raw/1402/data.rar."
        )
    if "MDBTools" not in __import__("pyodbc").drivers():
        raise RuntimeError("MDBTools ODBC driver is unavailable; see README.md for the local runtime setup.")

    cfg = config()
    work = path("intermediate") / "1402_raw_rebuild"
    unpacked = work / "unpacked"
    extracted = work / "extracted"
    cleaned = work / "cleaned"
    for folder in (unpacked, extracted, cleaned, work / "external", work / "cache", work / "maps"):
        folder.mkdir(parents=True, exist_ok=True)
    year_unpack = unpacked / "1402"
    year_unpack.mkdir(parents=True, exist_ok=True)
    db_link = year_unpack / mdb_path.name
    if not db_link.exists():
        db_link.symlink_to(mdb_path.resolve())

    defaults = hbsir.api.defaults
    defaults.dir.original = path("raw")
    defaults.dir.unpacked = unpacked
    defaults.dir.extracted = extracted
    defaults.dir.cleaned = cleaned
    defaults.dir.external = work / "external"
    defaults.dir.cached = work / "cache"
    defaults.dir.maps = work / "maps"

    # This invokes the installed, unmodified HBSIR/BSSIR raw-extract and cleaning pipeline.
    # The pre-existing unpack directory points at the exact MDB already extracted from the
    # unchanged archive, avoiding suffix-based re-unpacking of its ZIP container.
    hbsir.setup(
        years=1402,
        table_names=list(TABLES),
        replace=False,
        method="create_from_raw",
        download_source="mirror",
    )

    result_rows = []
    for hbsir_table, project_file in TABLES.items():
        direct = hbsir.load_table(
            hbsir_table,
            years=1402,
            form="normalized",
            on_missing="error",
            save_downloaded=False,
            save_created=False,
            recreate=False,
        )
        project = pd.read_parquet(path("yearly") / "1402" / f"{project_file}.parquet")
        project = project.copy()
        if hbsir_table == "household_information" and "HBSIR_Weight" in project:
            project["Weight"] = project["HBSIR_Weight"]

        shared = [column for column in direct.columns if column in project.columns]
        if not shared:
            raise AssertionError(f"No shared normalized columns for {hbsir_table}.")
        direct_rows = row_multiset(direct, shared)
        project_rows = row_multiset(project, shared)
        raw_only = sum((direct_rows - project_rows).values())
        mirror_only = sum((project_rows - direct_rows).values())
        result_rows.append({
            "Year": 1402,
            "HBSIR_Table": hbsir_table,
            "Project_Table": f"yearly/1402/{project_file}.parquet",
            "Raw_HBSIR_Rows": len(direct),
            "Project_Rows": len(project),
            "Shared_Normalized_Columns": ";".join(shared),
            "Shared_Column_Count": len(shared),
            "Raw_Rows_Not_Matched": raw_only,
            "Project_Rows_Not_Matched": mirror_only,
            "Full_Multiset_Match_On_Shared_Columns": raw_only == 0 and mirror_only == 0,
        })
    output = path("audit") / "direct_1402_raw_to_hbsir_value_check.csv"
    pd.DataFrame(result_rows).to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Direct raw-to-HBSIR comparison written: {output}")
    print(pd.DataFrame(result_rows)[["HBSIR_Table", "Raw_HBSIR_Rows", "Project_Rows", "Raw_Rows_Not_Matched", "Project_Rows_Not_Matched"]].to_string(index=False))
    return 0 if all(row["Full_Multiset_Match_On_Shared_Columns"] for row in result_rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
