from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pandas as pd


ROOT = Path("data/raw/cms/medicare_advantage")

SOURCE_DIRS = {
    "CPSC": ROOT / "enrollment",
    "SCC_SCP": ROOT / "enrollment_controls",
    "SNP": ROOT / "snp",
    "PLAN_PAYMENT": ROOT / "plan_payment",
}

OUTPUT_DIR = ROOT / "validation" / "source_inventory"

INVENTORY_CSV = (
    OUTPUT_DIR / "cms_ma_partc_required_source_inventory.csv"
)

SUMMARY_TXT = (
    OUTPUT_DIR / "cms_ma_partc_source_inventory_summary.txt"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def zip_status(path: Path) -> str:
    if not path.exists():
        return "NOT_PRESENT"

    if not zipfile.is_zipfile(path):
        return "PRESENT_NOT_ZIP"

    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()

            if bad is not None:
                return f"ZIP_BAD_MEMBER:{bad}"

        return "ZIP_VALID"

    except Exception as exc:
        return f"ZIP_ERROR:{type(exc).__name__}"


def required_ffy(year: int, month: int) -> int:
    """
    Federal fiscal year mapping.

    Jan-Sep belong to the calendar year's FFY.
    Oct-Dec belong to the following FFY.
    """
    return year if month <= 9 else year + 1


def build_monthly_inventory(
    months: pd.PeriodIndex,
) -> list[dict]:
    rows: list[dict] = []

    for period in months:
        year = period.year
        month = period.month

        for source_type, base in (
            ("CPSC", SOURCE_DIRS["CPSC"]),
            ("SCC_SCP", SOURCE_DIRS["SCC_SCP"]),
            ("SNP", SOURCE_DIRS["SNP"]),
        ):
            folder = base / str(year) / f"{month:02d}"

            files = []

            if folder.exists():
                files = sorted(
                    p
                    for p in folder.iterdir()
                    if p.is_file()
                )

            zip_files = [
                p
                for p in files
                if p.suffix.lower() == ".zip"
            ]

            if len(zip_files) == 0:
                rows.append(
                    {
                        "source_grain": "MONTHLY",
                        "period": str(period),
                        "year": year,
                        "month": month,
                        "payment_year": "",
                        "source_type": source_type,
                        "required_for_ffy": required_ffy(
                            year,
                            month,
                        ),
                        "local_status": "NOT_PRESENT",
                        "local_path": "",
                        "filename": "",
                        "bytes": "",
                        "sha256": "",
                        "zip_status": "",
                        "file_count_in_folder": len(files),
                        "notes": "",
                    }
                )

            else:
                for path in zip_files:
                    rows.append(
                        {
                            "source_grain": "MONTHLY",
                            "period": str(period),
                            "year": year,
                            "month": month,
                            "payment_year": "",
                            "source_type": source_type,
                            "required_for_ffy": required_ffy(
                                year,
                                month,
                            ),
                            "local_status": "PRESENT",
                            "local_path": str(path),
                            "filename": path.name,
                            "bytes": path.stat().st_size,
                            "sha256": sha256(path),
                            "zip_status": zip_status(path),
                            "file_count_in_folder": len(files),
                            "notes": (
                                "MULTIPLE_ZIPS"
                                if len(zip_files) > 1
                                else ""
                            ),
                        }
                    )

    return rows


def build_plan_payment_inventory() -> list[dict]:
    rows: list[dict] = []

    for year in range(2014, 2025):
        folder = (
            SOURCE_DIRS["PLAN_PAYMENT"]
            / str(year)
        )

        files = []

        if folder.exists():
            files = sorted(
                p
                for p in folder.iterdir()
                if p.is_file()
            )

        zip_files = [
            p
            for p in files
            if p.suffix.lower() == ".zip"
        ]

        if len(zip_files) == 0:
            rows.append(
                {
                    "source_grain": "ANNUAL",
                    "period": "",
                    "year": year,
                    "month": "",
                    "payment_year": year,
                    "source_type": "PLAN_PAYMENT",
                    "required_for_ffy": "",
                    "local_status": "NOT_PRESENT",
                    "local_path": "",
                    "filename": "",
                    "bytes": "",
                    "sha256": "",
                    "zip_status": "",
                    "file_count_in_folder": len(files),
                    "notes": "",
                }
            )

        else:
            for path in zip_files:
                rows.append(
                    {
                        "source_grain": "ANNUAL",
                        "period": "",
                        "year": year,
                        "month": "",
                        "payment_year": year,
                        "source_type": "PLAN_PAYMENT",
                        "required_for_ffy": "",
                        "local_status": "PRESENT",
                        "local_path": str(path),
                        "filename": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                        "zip_status": zip_status(path),
                        "file_count_in_folder": len(files),
                        "notes": (
                            "MULTIPLE_ZIPS"
                            if len(zip_files) > 1
                            else ""
                        ),
                    }
                )

    return rows


def main() -> None:
    months = pd.period_range(
        start="2014-10",
        end="2024-09",
        freq="M",
    )

    monthly_rows = build_monthly_inventory(months)
    annual_rows = build_plan_payment_inventory()

    inventory = pd.DataFrame(
        monthly_rows + annual_rows
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory.to_csv(
        INVENTORY_CSV,
        index=False,
    )

    monthly = inventory[
        inventory["source_grain"].eq("MONTHLY")
    ].copy()

    annual = inventory[
        inventory["source_grain"].eq("ANNUAL")
    ].copy()

    summary_rows = []

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        source = monthly[
            monthly["source_type"].eq(source_type)
        ]

        required_periods = source["period"].nunique()

        present_periods = source.loc[
            source["local_status"].eq("PRESENT"),
            "period",
        ].nunique()

        summary_rows.append(
            {
                "source_type": source_type,
                "required": required_periods,
                "present": present_periods,
                "missing": (
                    required_periods
                    - present_periods
                ),
            }
        )

    annual_present = annual.loc[
        annual["local_status"].eq("PRESENT"),
        "payment_year",
    ].nunique()

    monthly_required = len(months) * 3

    monthly_present = (
        monthly.loc[
            monthly["local_status"].eq("PRESENT"),
            ["period", "source_type"],
        ]
        .drop_duplicates()
        .shape[0]
    )

    zip_exceptions = inventory[
        inventory["local_status"].eq("PRESENT")
        & ~inventory["zip_status"].eq("ZIP_VALID")
    ]

    multiple_zip = inventory[
        inventory["notes"].eq("MULTIPLE_ZIPS")
    ]

    lines = []

    lines.append("=" * 80)
    lines.append(
        "CMS MEDICARE ADVANTAGE PART C — REQUIRED SOURCE INVENTORY"
    )
    lines.append("=" * 80)
    lines.append("")
    lines.append("SCOPE")
    lines.append(
        "Required reconstruction window: October 2014 through September 2024"
    )
    lines.append(
        f"Required monthly periods: {len(months)}"
    )
    lines.append(
        "Required monthly source families: CPSC, SCC/SCP, SNP"
    )
    lines.append(
        f"Required monthly source slots: {monthly_required}"
    )
    lines.append(
        "Required annual Plan Payment years: 11 (CY2014-CY2024)"
    )
    lines.append("")

    lines.append("MONTHLY LOCAL INVENTORY")

    for row in summary_rows:
        lines.append(
            f"{row['source_type']:<8} "
            f"required={row['required']:>3}  "
            f"present={row['present']:>3}  "
            f"missing={row['missing']:>3}"
        )

    lines.append("")
    lines.append("PLAN PAYMENT LOCAL INVENTORY")
    lines.append("Required years: 11")
    lines.append(
        f"Present years:  {annual_present}"
    )
    lines.append(
        f"Missing years:  {11 - annual_present}"
    )

    lines.append("")
    lines.append("PRESENT MONTHLY PERIODS")

    for source_type in (
        "CPSC",
        "SCC_SCP",
        "SNP",
    ):
        periods = sorted(
            monthly.loc[
                monthly["source_type"].eq(source_type)
                & monthly["local_status"].eq("PRESENT"),
                "period",
            ].unique()
        )

        period_text = (
            ", ".join(periods)
            if periods
            else "NONE"
        )

        lines.append(
            f"{source_type:<8}: {period_text}"
        )

    lines.append("")
    lines.append("PRESENT PLAN PAYMENT YEARS")

    years = sorted(
        annual.loc[
            annual["local_status"].eq("PRESENT"),
            "payment_year",
        ].unique()
    )

    lines.append(
        ", ".join(str(int(y)) for y in years)
        if years
        else "NONE"
    )

    lines.append("")
    lines.append("ZIP INTEGRITY EXCEPTIONS")

    if len(zip_exceptions) == 0:
        lines.append("NONE")
    else:
        for _, row in zip_exceptions.iterrows():
            identifier = (
                row["period"]
                if row["source_grain"] == "MONTHLY"
                else str(row["payment_year"])
            )

            lines.append(
                f"{identifier} | "
                f"{row['source_type']} | "
                f"{row['filename']} | "
                f"{row['zip_status']}"
            )

    lines.append("")
    lines.append("DUPLICATE/MULTIPLE-ZIP FOLDERS")

    if len(multiple_zip) == 0:
        lines.append("NONE")
    else:
        for _, row in multiple_zip.iterrows():
            identifier = (
                row["period"]
                if row["source_grain"] == "MONTHLY"
                else str(row["payment_year"])
            )

            lines.append(
                f"{identifier} | "
                f"{row['source_type']} | "
                f"{row['filename']}"
            )

    lines.append("")
    lines.append("REQUIRED-SLOT ACCOUNTING")
    lines.append(
        f"Monthly source slots required: {monthly_required}"
    )
    lines.append(
        f"Monthly source slots present:  {monthly_present}"
    )
    lines.append(
        "Monthly source slots missing:  "
        f"{monthly_required - monthly_present}"
    )
    lines.append(
        "Annual payment slots required: 11"
    )
    lines.append(
        f"Annual payment slots present:  {annual_present}"
    )
    lines.append(
        "Annual payment slots missing:  "
        f"{11 - annual_present}"
    )

    lines.append("")
    lines.append("STATUS INTERPRETATION")
    lines.append(
        "PRESENT means a ZIP artifact exists in the expected local repository "
        "location."
    )
    lines.append(
        "NOT_PRESENT means the required artifact is not currently found "
        "locally."
    )
    lines.append(
        "NOT_PRESENT does NOT mean CMS does not publish or retain the source."
    )
    lines.append(
        "CMS availability and official source discovery are separate "
        "subsequent validation steps."
    )
    lines.append("")
    lines.append(
        "This inventory performs no network access, downloads, or database writes."
    )

    summary_text = "\n".join(lines) + "\n"

    SUMMARY_TXT.write_text(
        summary_text,
        encoding="utf-8",
    )

    print(summary_text)

    print("Evidence written to:")
    print(f"  {OUTPUT_DIR}")
    print()
    print("Files:")
    print(f"  {INVENTORY_CSV.name}")
    print(f"  {SUMMARY_TXT.name}")


if __name__ == "__main__":
    main()
