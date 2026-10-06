from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from common import ROOT, config, path


def archive_signature(path_: Path) -> str:
    with path_.open("rb") as f:
        head = f.read(16)
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "ZIP"
    if head.startswith(b"Rar!\x1a\x07\x00"):
        return "RAR4"
    if head.startswith(b"Rar!\x1a\x07\x01\x00"):
        return "RAR5"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    return "unrecognized"


def sha256(path_: Path) -> str:
    value = hashlib.sha256()
    with path_.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def fetch(url: str, dest: Path) -> dict:
    temp = dest.with_suffix(dest.suffix + ".part")
    response = requests.get(url, stream=True, timeout=(30, 180), allow_redirects=True)
    chain = [h.url for h in response.history] + [response.url]
    result = {
        "requested_url": url,
        "http_status": response.status_code,
        "effective_url": response.url,
        "redirect_chain": json.dumps(chain, ensure_ascii=False),
        "content_type": response.headers.get("content-type"),
        "content_length_header": response.headers.get("content-length"),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
        "error": "",
    }
    if not response.ok:
        result["error"] = f"HTTP {response.status_code}"
        response.close()
        return result
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with temp.open("wb") as f:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)
                count += len(chunk)
    response.close()
    kind = archive_signature(temp)
    result["downloaded_bytes"] = count
    result["archive_signature"] = kind
    if kind == "unrecognized":
        result["error"] = "Response body did not have a recognized archive signature"
        temp.unlink(missing_ok=True)
        return result
    temp.replace(dest)
    result["sha256"] = sha256(dest)
    return result


def main() -> int:
    cfg = config()
    meta_path = ROOT / cfg["sources"]["hbsir_raw_metadata"]
    sources = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    years = range(cfg["project"]["first_year"], cfg["project"]["last_year"] + 1)
    rows: list[dict] = []
    for year in years:
        files = sources.get(year, sources.get(str(year), {})).get("files", [])
        if not files:
            rows.append({"Year": year, "Status": "missing_source_metadata", "Downloaded_At_UTC": datetime.now(timezone.utc).isoformat()})
            continue
        info = files[0]
        filename = info["name"]
        dest = path("raw") / str(year) / filename
        attempts = []
        official_url = info.get(cfg["sources"]["official_archive_field"])
        if official_url:
            direct = fetch(official_url, dest)
            direct["source_kind"] = "official_url"
            attempts.append(direct)
            if not direct.get("sha256"):
                dest.unlink(missing_ok=True)
        for mirror in cfg["sources"]["mirrors"]:
            if any(a.get("sha256") for a in attempts):
                break
            mirror_url = f"{mirror['base_url']}/{year}/{filename}"
            result = fetch(mirror_url, dest)
            result["source_kind"] = f"hbsir_documented_mirror:{mirror['name']}"
            attempts.append(result)
            if not result.get("sha256"):
                dest.unlink(missing_ok=True)
        success = next((a for a in reversed(attempts) if a.get("sha256")), None)
        row = {
            "Year": year,
            "Official_URL": official_url,
            "Status": "retrieved_official" if success and success["source_kind"] == "official_url" else ("retrieved_documented_mirror" if success else "failed"),
            "Source": success["source_kind"] if success else "",
            "Downloaded_At_UTC": datetime.now(timezone.utc).isoformat(),
            "File_Name": filename if success else "",
            "File_Size_Bytes": success.get("downloaded_bytes", "") if success else "",
            "SHA256": success.get("sha256", "") if success else "",
            "Archive_Signature": success.get("archive_signature", "") if success else "",
            "Actual_URL": success.get("effective_url", "") if success else "",
            "Redirect_Chain": success.get("redirect_chain", "") if success else "",
            "Content_Type": success.get("content_type", "") if success else "",
            "ETag": success.get("etag", "") if success else "",
            "Last_Modified": success.get("last_modified", "") if success else "",
            "Official_HTTP_Status": attempts[0].get("http_status", "") if attempts else "",
            "Official_Error": attempts[0].get("error", "") if attempts else "",
            "Attempt_Log_JSON": json.dumps(attempts, ensure_ascii=False),
        }
        rows.append(row)
        print(f"{year}: {row['Status']} {row.get('File_Size_Bytes','')} {row.get('SHA256','')}")
    out = ROOT / "metadata/raw_sources.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row})
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    failures = [r for r in rows if r.get("Status") == "failed"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
