from __future__ import annotations

import csv
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = ROOT / "data" / "interim" / "opm"

OUTPUT_FILE = (
    OUTPUT_DIR
    / "opm_fedscope_september_employment_source_registry_2015_2024.csv"
)

INDEX_URL = "https://www.opm.gov/data/datasets/Index.aspx"

YEARS = set(range(2015, 2025))

PATTERN = re.compile(
    r"FedScope\s+Employment\s+Cube\s*"
    r"\(\s*September\s+(\d{4})\s*\)",
    re.IGNORECASE,
)


def absolute_opm_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href

    if not href.startswith("/"):
        href = "/" + href

    return "https://www.opm.gov" + href


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 88)
    print("OPM FEDSCOPE SEPTEMBER EMPLOYMENT SOURCE DISCOVERY")
    print("=" * 88)
    print(f"Official index: {INDEX_URL}")
    print()

    response = requests.get(
        INDEX_URL,
        timeout=120,
        headers={
            "User-Agent":
                "WCFFBP/1.0 "
                "(Washington County Federal Fiscal Balance Project)"
        },
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    records: dict[int, dict[str, str]] = {}

    for row in soup.find_all("tr"):
        text = " ".join(row.stripped_strings)

        match = PATTERN.search(text)

        if not match:
            continue

        year = int(match.group(1))

        if year not in YEARS:
            continue

        links = []

        for anchor in row.find_all("a", href=True):
            href = anchor["href"].strip()

            if "/data/datasets/Files/" not in href:
                continue

            links.append(
                {
                    "text": " ".join(anchor.stripped_strings),
                    "url": absolute_opm_url(href),
                }
            )

        print("-" * 88)
        print(f"YEAR: {year}")
        print(f"ROW:  {text}")

        for link in links:
            print(
                f"LINK: {link['text']!r} -> {link['url']}"
            )

        records[year] = {
            "snapshot": f"{year}-09",
            "year": str(year),
            "dataset_title":
                f"FedScope Employment Cube (September {year})",
            "index_url": INDEX_URL,
            "row_text": text,
            "file_links": " | ".join(
                link["url"] for link in links
            ),
            "status": (
                "FOUND"
                if links
                else "FOUND_NO_FILE_LINKS"
            ),
        }

    print()
    print("=" * 88)
    print("DISCOVERY SUMMARY")
    print("=" * 88)

    missing = []

    for year in sorted(YEARS):
        record = records.get(year)

        if record is None:
            missing.append(year)
            print(f"{year}-09  MISSING")
        else:
            print(
                f"{year}-09  "
                f"{record['status']}  "
                f"links="
                f"{len(record['file_links'].split(' | ')) if record['file_links'] else 0}"
            )

    fieldnames = [
        "snapshot",
        "year",
        "dataset_title",
        "index_url",
        "row_text",
        "file_links",
        "status",
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for year in sorted(YEARS):
            if year in records:
                writer.writerow(records[year])
            else:
                writer.writerow(
                    {
                        "snapshot": f"{year}-09",
                        "year": str(year),
                        "dataset_title":
                            f"FedScope Employment Cube "
                            f"(September {year})",
                        "index_url": INDEX_URL,
                        "row_text": "",
                        "file_links": "",
                        "status": "MISSING",
                    }
                )

    print()
    print(f"Registry written: {OUTPUT_FILE}")

    if missing:
        print()
        print(
            "WARNING: Missing September snapshots: "
            + ", ".join(str(y) for y in missing)
        )
        print(
            "Do NOT infer or substitute another quarter."
        )
    else:
        print()
        print(
            "PASS: All September 2015-2024 "
            "dataset records discovered."
        )


if __name__ == "__main__":
    main()