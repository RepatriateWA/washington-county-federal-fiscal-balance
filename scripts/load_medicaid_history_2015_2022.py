from __future__ import annotations

import subprocess
import sys
from pathlib import Path


FILES = {
    2015: Path(
        "data/raw/cms/medicaid_mbes/2015/extracted/"
        "FY 2015 NET EXPENDITURES.xlsx"
    ),
    2016: Path(
        "data/raw/cms/medicaid_mbes/2016/extracted/"
        "FY 2016 FMR NET EXPENDITURES.xlsx"
    ),
    2017: Path(
        "data/raw/cms/medicaid_mbes/2017/extracted/"
        "FY 2017 FMR NET EXPENDITURES.xlsx"
    ),
    2018: Path(
        "data/raw/cms/medicaid_mbes/2018/extracted/"
        "FY 2018 FMR NET EXPENDITURES.xlsx"
    ),
    2019: Path(
        "data/raw/cms/medicaid_mbes/2019/extracted/"
        "FY 2019 FMR NET EXPENDITURES.xlsx"
    ),
    2020: Path(
        "data/raw/cms/medicaid_mbes/2020/extracted/"
        "FY 2020 FMR NET EXPENDITURES.xlsx"
    ),
    2021: Path(
        "data/raw/cms/medicaid_mbes/2021/extracted/"
        "FY 2021 FMR NET EXPENDITURES.xlsx"
    ),
    2022: Path(
        "data/raw/cms/medicaid_mbes/2022/extracted/"
        "FY 2022 FMR NET EXPENDITURES.xlsx"
    ),
}


def run_command(command: list[str]) -> None:
    print()
    print("=" * 100)
    print("RUNNING:")
    print(" ".join(command))
    print("=" * 100)

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: "
            + " ".join(command)
        )


def main() -> int:
    for fiscal_year, source_file in FILES.items():
        if not source_file.exists():
            raise FileNotFoundError(
                f"Missing FY{fiscal_year} source workbook: {source_file}"
            )

        run_command(
            [
                sys.executable,
                "-m",
                "etl.loaders.load_medicaid_mbes_raw",
                "--source-file",
                str(source_file),
                "--fiscal-year",
                str(fiscal_year),
            ]
        )

        run_command(
            [
                sys.executable,
                "-m",
                "scripts.validate_medicaid_mbes_raw",
                "--fiscal-year",
                str(fiscal_year),
            ]
        )

        run_command(
            [
                sys.executable,
                "-m",
                "etl.loaders.load_medicaid_curated",
                "--fiscal-year",
                str(fiscal_year),
            ]
        )

    print()
    print("=" * 100)
    print("MEDICAID HISTORY LOAD COMPLETE: FY2015–FY2022")
    print("=" * 100)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())