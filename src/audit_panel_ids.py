from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from common import append_issues, config, path


def load_ids(year: int) -> set[str]:
    frame = pd.read_parquet(path("yearly") / str(year) / "household.parquet", columns=["ID"])
    return set(frame["ID"].dropna().astype("uint64").astype(str))


def main() -> int:
    cfg = config()
    start, end = cfg["project"]["first_year"], cfg["project"]["last_year"]
    years = list(range(start, end + 1))
    ids_by_year = {year: load_ids(year) for year in years}
    appearances: dict[str, list[int]] = {}
    for year, ids in ids_by_year.items():
        for household_id in ids:
            appearances.setdefault(household_id, []).append(year)

    history = []
    three_waves = []
    for household_id, present in appearances.items():
        present = sorted(present)
        runs: list[list[int]] = []
        for year in present:
            if not runs or year != runs[-1][-1] + 1:
                runs.append([year])
            else:
                runs[-1].append(year)
        consecutive_links = sum(max(0, len(run) - 1) for run in runs)
        max_run = max(map(len, runs))
        history.append({
            "ID": int(household_id),
            "First_Year": present[0],
            "Last_Year": present[-1],
            "Number_of_Observed_Years": len(present),
            "Years_Present": ";".join(map(str, present)),
            "Consecutive_Years": consecutive_links,
            "Consecutive_Year_Pairs": ";".join(f"{a}-{b}" for run in runs for a, b in zip(run, run[1:])),
            "Maximum_Consecutive_Run": max_run,
            "Run_Year_Sequences": ";".join("-".join(map(str, run)) for run in runs),
        })
        for i in range(len(present) - 2):
            if present[i + 1] == present[i] + 1 and present[i + 2] == present[i] + 2:
                three_waves.append({
                    "ID": int(household_id),
                    "start_year": present[i],
                    "middle_year": present[i + 1],
                    "end_year": present[i + 2],
                    "cohort": f"{present[i]}-{present[i + 2]}",
                })

    audit = path("audit")
    audit.mkdir(parents=True, exist_ok=True)
    history_df = pd.DataFrame(history).sort_values("ID")
    history_df.to_parquet(audit / "panel_household_history.parquet", index=False)
    pd.DataFrame(three_waves, columns=["ID", "start_year", "middle_year", "end_year", "cohort"]).sort_values(
        ["start_year", "ID"]
    ).to_parquet(audit / "three_wave_panels.parquet", index=False)

    bins = {
        "one_year": int(history_df["Number_of_Observed_Years"].eq(1).sum()),
        "two_years": int(history_df["Number_of_Observed_Years"].eq(2).sum()),
        "three_years": int(history_df["Number_of_Observed_Years"].eq(3).sum()),
        "more_than_three_years": int(history_df["Number_of_Observed_Years"].gt(3).sum()),
    }
    pd.DataFrame([{"Observed_Year_Bin": key, "Household_ID_Count": value} for key, value in bins.items()]).to_csv(
        audit / "panel_length_distribution.csv", index=False, encoding="utf-8-sig"
    )

    rows = []
    for year in years:
        current = ids_by_year[year]
        row = {"Year": year, "Households_t": len(current)}
        for lag in (1, 2):
            later_year = year + lag
            later = ids_by_year.get(later_year, set())
            if later_year not in ids_by_year:
                row.update({
                    f"Common_t_tplus{lag}": pd.NA,
                    f"Share_of_HH_in_t_also_in_tplus{lag}": pd.NA,
                    f"Share_of_HH_in_tplus{lag}_also_in_t": pd.NA,
                    f"Jaccard_t_tplus{lag}": pd.NA,
                })
                continue
            common = current & later
            union = current | later
            row.update({
                f"Common_t_tplus{lag}": len(common),
                f"Share_of_HH_in_t_also_in_tplus{lag}": len(common) / len(current) if current else pd.NA,
                f"Share_of_HH_in_tplus{lag}_also_in_t": len(common) / len(later) if later else pd.NA,
                f"Jaccard_t_tplus{lag}": len(common) / len(union) if union else pd.NA,
            })
        rows.append(row)
    pd.DataFrame(rows).to_csv(audit / "panel_overlap_by_year.csv", index=False, encoding="utf-8-sig")

    issue_rows = []
    for year in years:
        frame = pd.read_parquet(path("yearly") / str(year) / "household.parquet", columns=["ID"])
        duplicate_rows = int(frame["ID"].duplicated(keep=False).sum())
        duplicate_ids = int(frame.loc[frame["ID"].duplicated(keep=False), "ID"].nunique())
        if duplicate_rows:
            issue_rows.append({"Year": year, "Scope": "household.ID", "Issue": "duplicate_household_id_within_year", "Severity": "warning", "Details": f"{duplicate_ids} IDs occur in {duplicate_rows} rows; rows retained."})
    over3 = int(history_df["Number_of_Observed_Years"].gt(3).sum())
    if over3:
        issue_rows.append({"Year": "all", "Scope": "panel.ID", "Issue": "id_present_more_than_three_years", "Severity": "warning", "Details": f"{over3} IDs appear in more than three survey years; reuse/ID comparability must be reviewed, not treated as confirmed family continuity."})
    issue_rows.append({"Year": "all", "Scope": "panel.ID", "Issue": "cross_year_identity_not_verified", "Severity": "caution", "Details": "IDs are descriptive address/sample identifiers. Repeated IDs do not by themselves establish the same household; HBSIR design documentation indicates frame/rotation baselines change in 1392 and 1397."})
    append_issues(issue_rows)
    summary = {
        "unique_ids_all_years": len(history_df),
        "length_bins": bins,
        "three_wave_rows": len(three_waves),
        "ids_over_three_years": over3,
    }
    (audit / "panel_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
