from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def config() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def path(key: str) -> Path:
    return ROOT / config()["paths"][key]


def write_json(path_: Path, value: Any) -> None:
    path_.parent.mkdir(parents=True, exist_ok=True)
    path_.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def append_issues(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    target = path("audit") / "issues_log.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = ["Year", "Scope", "Issue", "Severity", "Details"]
    new = pd.DataFrame(rows, columns=columns)
    if target.exists() and target.stat().st_size:
        old = pd.read_csv(target, encoding="utf-8-sig", dtype=str)
        combined = pd.concat([old, new.astype(str)], ignore_index=True)
    else:
        combined = new
    combined.drop_duplicates(subset=columns, keep="first", inplace=True)
    combined.to_csv(target, index=False, encoding="utf-8-sig")
