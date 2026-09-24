#!/usr/bin/env python3
"""
acquire_cms_partd_landscape.py

Acquire and preserve the official CMS CY2006-CY2025 Landscape Files archive.

Read/write boundary
-------------------
- Downloads one official CMS ZIP.
- Never modifies an existing downloaded archive unless --force is supplied.
- Writes a provenance manifest and SHA-256.
- Does not interpret Landscape semantics, classify plans, reconstruct payments,
  touch PostgreSQL, or authorize ledger inclusion.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "https://www.cms.gov/files/zip/cy2006-cy2025-landscape-files.zip"
DEFAULT_ROOT = Path("data/raw/cms/medicare_partd/landscape")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--force", action="store_true")
    a = p.parse_args()

    a.output_root.mkdir(parents=True, exist_ok=True)
    dest = a.output_root / "cy2006-cy2025-landscape-files.zip"
    manifest_csv = a.output_root / "cms_partd_landscape_acquisition_manifest.csv"
    manifest_json = a.output_root / "cms_partd_landscape_acquisition_manifest.json"

    if dest.exists() and not a.force:
        print(f"Archive already exists; preserving unchanged: {dest}")
        digest = sha256_file(dest)
        retrieved = None
        disposition = "PRESERVED_EXISTING"
    else:
        tmp = dest.with_suffix(dest.suffix + ".partial")
        if tmp.exists():
            tmp.unlink()
        req = urllib.request.Request(
            a.url,
            headers={"User-Agent": "WCFFBP CMS source acquisition/1.0"}
        )
        print(f"Downloading official CMS archive:\n  {a.url}")
        try:
            with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as out:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise RuntimeError("Downloaded object is not a valid ZIP archive.")

        if dest.exists():
            dest.unlink()
        tmp.replace(dest)
        digest = sha256_file(dest)
        retrieved = datetime.now(timezone.utc).isoformat()
        disposition = "DOWNLOADED_OFFICIAL"

    with zipfile.ZipFile(dest) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        bad = z.testzip()

    row = {
        "source_url": a.url,
        "retrieved_utc": retrieved or "",
        "local_path": str(dest),
        "bytes": dest.stat().st_size,
        "sha256": digest,
        "zip_member_count": len(members),
        "zip_test_first_bad_member": bad or "",
        "disposition": disposition,
    }
    with manifest_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    manifest_json.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")

    print("\nCMS MEDICARE PART D LANDSCAPE ACQUISITION")
    print("=" * 68)
    for k, v in row.items():
        print(f"{k}: {v}")
    print("\nCHECKS")
    print("-" * 68)
    checks = [
        ("archive exists", dest.exists()),
        ("archive is ZIP", zipfile.is_zipfile(dest)),
        ("ZIP integrity", bad is None),
        ("nonempty archive", dest.stat().st_size > 0),
        ("SHA-256 recorded", len(digest) == 64),
    ]
    for label, ok in checks:
        print(f"{label}: {'PASS' if ok else 'FAIL'}")
    overall = all(ok for _, ok in checks)
    print(f"\nOVERALL: {'PASS' if overall else 'FAIL'}")
    print(f"Manifest: {manifest_csv}")
    return 0 if overall else 1

if __name__ == "__main__":
    sys.exit(main())
