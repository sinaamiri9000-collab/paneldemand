from __future__ import annotations

import csv
import hashlib
import json
import zipfile
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT, append_issues, config, path
from download_raw import archive_signature


def sha256(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    cfg = config()
    rows = list(csv.DictReader((path("metadata") / "raw_sources.csv").open(encoding="utf-8-sig")))
    audit_rows = []
    issues = []
    unrar_candidates = [ROOT / ".local/rar/usr/lib/unrar"]
    unrar_path = next((str(item) for item in unrar_candidates if item.is_file()), shutil.which("unrar"))
    for row in rows:
        year = int(row["Year"])
        file = path("raw") / str(year) / row.get("File_Name", "data.rar")
        exists = file.exists()
        actual_size = file.stat().st_size if exists else 0
        actual_hash = sha256(file) if exists else ""
        signature = archive_signature(file) if exists else "missing"
        size_match = str(actual_size) == str(row.get("File_Size_Bytes", ""))
        hash_match = actual_hash == row.get("SHA256", "")
        signature_match = signature == row.get("Archive_Signature", "")
        integrity = "not_attempted_RAR_reader_unavailable"
        if signature == "ZIP" and exists:
            try:
                with zipfile.ZipFile(file) as archive:
                    bad = archive.testzip()
                    integrity = "passed" if bad is None else f"failed_member:{bad}"
            except Exception as exc:
                integrity = f"failed:{type(exc).__name__}:{str(exc)[:200]}"
        elif signature.startswith("RAR") and exists and unrar_path:
            try:
                checked = subprocess.run(
                    [unrar_path, "t", "-idq", str(file)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=600,
                    check=False,
                )
                integrity = "RAR_test_passed" if checked.returncode == 0 else f"RAR_test_failed:{checked.returncode}:{checked.stdout[-200:]}"
            except Exception as exc:
                integrity = f"RAR_test_failed:{type(exc).__name__}:{str(exc)[:200]}"
        result = "passed" if exists and size_match and hash_match and signature_match else "failed_manifest_verification"
        if result != "passed" or integrity.startswith("failed") or integrity.startswith("RAR_test_failed"):
            issues.append({"Year": year, "Scope": "raw.archive", "Issue": "archive_manifest_mismatch", "Severity": "blocking", "Details": f"exists={exists}; size_match={size_match}; hash_match={hash_match}; signature_match={signature_match}."})
        if row.get("Official_HTTP_Status") == "503":
            issues.append({"Year": year, "Scope": "raw.archive", "Issue": "official_endpoint_unavailable_documented_mirror_used", "Severity": "source_limitation", "Details": f"Official endpoint returned HTTP 503; obtained from {row.get('Source')}."})
        audit_rows.append({
            "Year": year,
            "Official_URL": row.get("Official_URL", ""),
            "Official_HTTP_Status": row.get("Official_HTTP_Status", ""),
            "Source": row.get("Source", ""),
            "Actual_URL": row.get("Actual_URL", ""),
            "Local_File": str(file.relative_to(file.parents[1])) if exists else "",
            "File_Size_Bytes": actual_size,
            "SHA256": actual_hash,
            "Archive_Signature": signature,
            "Size_Matches_Manifest": size_match,
            "SHA256_Matches_Manifest": hash_match,
            "Signature_Matches_Manifest": signature_match,
            "Archive_Integrity_Check": integrity,
            "Status": result,
        })

    audit_dir = path("audit")
    audit_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    pd.DataFrame(audit_rows).to_csv(audit_dir / "raw_archive_integrity.csv", index=False, encoding="utf-8-sig")
    summary = {
        "years": len(audit_rows),
        "manifest_checks_passed": sum(row["Status"] == "passed" for row in audit_rows),
        "official_http_503": sum(str(row["Official_HTTP_Status"]) == "503" for row in audit_rows),
        "zip_integrity_passed": sum(row["Archive_Integrity_Check"] == "passed" for row in audit_rows),
        "rar_integrity_passed": sum(row["Archive_Integrity_Check"] == "RAR_test_passed" for row in audit_rows),
        "rar_integrity_not_attempted": sum(row["Archive_Integrity_Check"] == "not_attempted_RAR_reader_unavailable" for row in audit_rows),
        "unrar_path": unrar_path or "not_found",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (audit_dir / "raw_archive_integrity_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_issues(issues)
    return 0 if summary["manifest_checks_passed"] == len(audit_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
