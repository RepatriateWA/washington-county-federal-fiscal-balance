from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


DISCOVERY_CSV = Path(
    "data/raw/cms/medicare_rds/discovery/"
    "program_statistics_partd_enrollment_v0_1/"
    "cms_partd_enrollment_distributions_v0_1.csv"
)

OUTDIR = Path(
    "data/raw/cms/medicare_rds/"
    "program_statistics_partd_enrollment"
)

MANIFEST = OUTDIR / "cms_partd_enrollment_acquisition_manifest_v0_1.csv"
MEMBERS = OUTDIR / "cms_partd_enrollment_zip_members_v0_1.csv"
REPORT = OUTDIR / "cms_partd_enrollment_acquisition_report_v0_1.txt"

REQUIRED_YEARS = list(range(2015, 2024))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def year_from_temporal(value: str) -> int | None:
    value = (value or "").strip()

    if len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])

    return None


def safe_filename(url: str, year: int) -> str:
    name = Path(urlparse(url).path).name

    # URL path may contain percent-encoded characters.  Use a stable,
    # simple local filename instead of depending on CMS naming.
    suffix = ".zip" if name.lower().endswith(".zip") else ".bin"

    return f"cms_program_statistics_partd_enrollment_{year}{suffix}"


def download(url: str, destination: Path) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "WCFFBP-CMS-RDS-Acquisition/0.1 "
                "(Washington County Federal Fiscal Balance Project)"
            )
        },
    )

    h = hashlib.sha256()
    total = 0

    temp = destination.with_suffix(destination.suffix + ".part")

    if temp.exists():
        temp.unlink()

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            with temp.open("wb") as f:
                while True:
                    block = response.read(1024 * 1024)

                    if not block:
                        break

                    f.write(block)
                    h.update(block)
                    total += len(block)

        temp.replace(destination)

    except Exception:
        if temp.exists():
            temp.unlink()
        raise

    return total, h.hexdigest()


def main() -> None:
    print("=" * 100)
    print("CMS PROGRAM STATISTICS PART D / RDS ACQUISITION v0.1")
    print("=" * 100)
    print()
    print("RAW SOURCE ACQUISITION")
    print("No database writes.")
    print("No source transformation.")
    print("No RDS geographic interpretation.")
    print()

    if not DISCOVERY_CSV.exists():
        print(f"FAIL: discovery manifest not found:")
        print(f"  {DISCOVERY_CSV}")
        raise SystemExit(1)

    OUTDIR.mkdir(parents=True, exist_ok=True)

    with DISCOVERY_CSV.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as f:
        discovery = list(csv.DictReader(f))

    by_year: dict[int, list[dict[str, str]]] = {}

    for row in discovery:
        year = year_from_temporal(row.get("temporal", ""))

        if year is None:
            continue

        if year in REQUIRED_YEARS:
            by_year.setdefault(year, []).append(row)

    manifest_rows: list[dict[str, str]] = []
    member_rows: list[dict[str, str]] = []

    print("=" * 100)
    print("SOURCE RESOLUTION")
    print("=" * 100)

    resolution_ok = True

    for year in REQUIRED_YEARS:
        rows = by_year.get(year, [])

        usable = [
            row
            for row in rows
            if (row.get("download_url") or "").strip()
        ]

        print(
            f"{year}: discovery_rows={len(rows)} | "
            f"downloadable={len(usable)}"
        )

        if len(usable) != 1:
            resolution_ok = False

    print()

    if not resolution_ok:
        print(
            "FAIL: each required year must resolve to exactly one "
            "CMS downloadURL."
        )
        print("No downloads performed.")
        raise SystemExit(1)

    print("=" * 100)
    print("ACQUISITION")
    print("=" * 100)

    acquisition_ok = True

    for year in REQUIRED_YEARS:
        row = [
            x
            for x in by_year[year]
            if (x.get("download_url") or "").strip()
        ][0]

        url = row["download_url"].strip()

        year_dir = OUTDIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        destination = year_dir / safe_filename(url, year)

        retrieved_utc = datetime.now(timezone.utc).isoformat()

        status = "UNKNOWN"
        byte_count = ""
        digest = ""
        zip_status = ""
        zip_member_count = ""
        error = ""

        try:
            if destination.exists():
                # Preserve already-acquired immutable raw bytes.
                byte_count = str(destination.stat().st_size)
                digest = sha256_file(destination)
                status = "PRESENT_EXISTING"
            else:
                nbytes, digest = download(url, destination)
                byte_count = str(nbytes)
                status = "DOWNLOADED"

            try:
                with zipfile.ZipFile(destination) as zf:
                    bad_member = zf.testzip()
                    names = zf.namelist()

                    zip_member_count = str(len(names))

                    if bad_member is None:
                        zip_status = "PASS"
                    else:
                        zip_status = f"FAIL:{bad_member}"
                        acquisition_ok = False

                    for member in zf.infolist():
                        member_rows.append(
                            {
                                "year": str(year),
                                "local_zip": str(destination),
                                "member_name": member.filename,
                                "uncompressed_bytes": str(member.file_size),
                                "compressed_bytes": str(member.compress_size),
                                "crc": str(member.CRC),
                            }
                        )

            except zipfile.BadZipFile as exc:
                zip_status = "FAIL:BAD_ZIP"
                error = repr(exc)
                acquisition_ok = False

        except Exception as exc:
            status = "ERROR"
            error = repr(exc)
            acquisition_ok = False

        manifest_rows.append(
            {
                "year": str(year),
                "temporal": row.get("temporal", ""),
                "dataset_title": row.get("dataset_title", ""),
                "dataset_identifier": row.get("dataset_identifier", ""),
                "dataset_modified": row.get("dataset_modified", ""),
                "format": row.get("format", ""),
                "media_type": row.get("media_type", ""),
                "source_download_url": url,
                "retrieved_utc": retrieved_utc,
                "local_path": str(destination),
                "status": status,
                "bytes": byte_count,
                "sha256": digest,
                "zip_integrity": zip_status,
                "zip_member_count": zip_member_count,
                "error": error,
            }
        )

        print(
            f"{year} | {status:16} | "
            f"bytes={byte_count or '-':>10} | "
            f"ZIP={zip_status or '-':12} | "
            f"members={zip_member_count or '-':>3}"
        )

    manifest_fields = [
        "year",
        "temporal",
        "dataset_title",
        "dataset_identifier",
        "dataset_modified",
        "format",
        "media_type",
        "source_download_url",
        "retrieved_utc",
        "local_path",
        "status",
        "bytes",
        "sha256",
        "zip_integrity",
        "zip_member_count",
        "error",
    ]

    with MANIFEST.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=manifest_fields,
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    member_fields = [
        "year",
        "local_zip",
        "member_name",
        "uncompressed_bytes",
        "compressed_bytes",
        "crc",
    ]

    with MEMBERS.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=member_fields,
        )
        writer.writeheader()
        writer.writerows(member_rows)

    successful_years = {
        int(row["year"])
        for row in manifest_rows
        if (
            row["status"] in {"DOWNLOADED", "PRESENT_EXISTING"}
            and row["zip_integrity"] == "PASS"
        )
    }

    checks = [
        (
            "CY2015-CY2023 resolved uniquely",
            resolution_ok,
            f"{len(REQUIRED_YEARS)}/9 required years",
        ),
        (
            "CY2015-CY2023 source files acquired",
            successful_years == set(REQUIRED_YEARS),
            f"{len(successful_years)}/9 years",
        ),
        (
            "All acquired files pass ZIP integrity",
            all(
                row["zip_integrity"] == "PASS"
                for row in manifest_rows
            ),
            (
                f"{sum(row['zip_integrity'] == 'PASS' for row in manifest_rows)}"
                "/9 files"
            ),
        ),
        (
            "SHA-256 recorded for every acquired source",
            all(
                len(row["sha256"]) == 64
                for row in manifest_rows
            ),
            (
                f"{sum(len(row['sha256']) == 64 for row in manifest_rows)}"
                "/9 files"
            ),
        ),
        (
            "ZIP members inventoried",
            len(member_rows) > 0,
            f"{len(member_rows)} members",
        ),
    ]

    print()
    print("=" * 100)
    print("CHECKS")
    print("=" * 100)

    for label, passed, detail in checks:
        print(
            f"{'PASS' if passed else 'FAIL':4} | "
            f"{label} | {detail}"
        )

    overall = acquisition_ok and all(
        passed
        for _, passed, _ in checks
    )

    report_lines = [
        "CMS PROGRAM STATISTICS PART D / RDS ACQUISITION v0.1",
        "=" * 78,
        "",
        "Scope: CY2015-CY2023",
        "",
        "This acquisition preserves the exact CMS ZIP distributions",
        "identified by the previously preserved CMS catalog discovery.",
        "",
        "No files were transformed or interpreted.",
        "No Washington RDS dollars were reconstructed.",
        "",
        "CHECKS",
        "-" * 78,
    ]

    for label, passed, detail in checks:
        report_lines.append(
            f"{'PASS' if passed else 'FAIL'} | {label} | {detail}"
        )

    report_lines.extend(
        [
            "",
            "BOUNDARY",
            "-" * 78,
            (
                "CY2024 is not included because the CMS catalog discovery "
                "did not expose a CY2024 distribution for this dataset."
            ),
            (
                "Acquisition does not establish that any ZIP member is "
                "MDCR ENROLL D 3 or that its geography is suitable for "
                "WCFFBP allocation."
            ),
            (
                "The next stage must profile ZIP contents and identify "
                "the exact D3 table and its published geographic grain."
            ),
        ]
    )

    REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print(
        "OVERALL ACQUISITION: "
        + ("PASS" if overall else "FAIL")
    )
    print("=" * 100)

    print()
    print("Evidence written:")
    print(f"  {MANIFEST}")
    print(f"  {MEMBERS}")
    print(f"  {REPORT}")

    print()
    print("Boundary:")
    print("  CY2015-CY2023 acquired.")
    print("  CY2024 remains unavailable in current catalog discovery.")
    print("  No D3 interpretation has yet been performed.")

    if not overall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
