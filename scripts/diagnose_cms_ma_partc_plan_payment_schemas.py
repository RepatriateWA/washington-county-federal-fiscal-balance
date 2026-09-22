from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

ACQUISITION_MANIFEST = (
    ROOT
    / "data"
    / "raw"
    / "cms"
    / "medicare_advantage"
    / "validation"
    / "source_acquisition"
    / "cms_ma_partc_source_acquisition_manifest.csv"
)


def clean(value) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return " ".join(str(value).strip().split())


def resolve_path(value: str) -> Path:
    p = Path(clean(value))
    return p if p.is_absolute() else ROOT / p


def find_partc_county_workbooks(zf: zipfile.ZipFile) -> list[str]:
    """
    Identify candidate Part C county-level workbooks without assuming
    one exact historical filename.
    """
    candidates = []

    for info in zf.infolist():
        if info.is_dir():
            continue

        name = Path(info.filename).name
        lower = name.casefold()

        if Path(name).suffix.lower() not in {".xls", ".xlsx"}:
            continue

        compact = re.sub(r"[^a-z0-9]+", "", lower)

        has_partc = "partc" in compact
        has_county = "county" in compact

        if has_partc and has_county:
            candidates.append(info.filename)

    return candidates


def locate_header(payload: bytes, extension: str):
    engine = "xlrd" if extension == ".xls" else "openpyxl"

    book = pd.ExcelFile(io.BytesIO(payload), engine=engine)

    required_signals = {
        "county",
        "plan type",
    }

    payment_signals = {
        "average ab pm/pm payment",
        "average a/b pm/pm payment",
        "average rebate pm/pm payment",
        "average part c risk score",
    }

    candidates = []

    for sheet in book.sheet_names:
        preview = pd.read_excel(
            io.BytesIO(payload),
            sheet_name=sheet,
            header=None,
            nrows=40,
            engine=engine,
        )

        for idx, row in preview.iterrows():
            values = [clean(x) for x in row.tolist()]
            keys = {x.casefold() for x in values if x}

            base_score = len(keys & required_signals)
            payment_score = len(keys & payment_signals)

            # We want a row that looks like the actual county payment table,
            # not title text or explanatory prose.
            if base_score >= 1 and payment_score >= 2:
                candidates.append(
                    (
                        base_score + payment_score,
                        sheet,
                        int(idx),
                        values,
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (-x[0], x[1], x[2])
    )

    return candidates[0]


def normalize_header_for_signature(header: list[str]) -> tuple[str, ...]:
    """
    Preserve semantic wording and order, but normalize trivial whitespace
    and capitalization so equivalent physical headers group together.
    """
    result = []

    for value in header:
        value = clean(value)

        if not value:
            continue

        result.append(value.casefold())

    return tuple(result)


def main():
    if not ACQUISITION_MANIFEST.exists():
        raise FileNotFoundError(
            f"Acquisition manifest not found: {ACQUISITION_MANIFEST}"
        )

    manifest = pd.read_csv(
        ACQUISITION_MANIFEST,
        dtype=str,
    ).fillna("")

    pp = manifest[
        manifest["source_type"] == "PLAN_PAYMENT"
    ].copy()

    print("=" * 110)
    print("CMS MEDICARE ADVANTAGE PART C PLAN PAYMENT SCHEMA DIAGNOSTIC")
    print("=" * 110)
    print()
    print(f"Plan Payment manifest rows: {len(pp)}")
    print()

    if len(pp) != 11:
        raise RuntimeError(
            f"Expected 11 Plan Payment rows for CY2014-CY2024; "
            f"found {len(pp)}"
        )

    records = []

    for _, row in pp.sort_values("payment_year").iterrows():
        payment_year = clean(row["payment_year"])

        if payment_year.endswith(".0"):
            payment_year = payment_year[:-2]

        path = resolve_path(row["local_path"])

        print("=" * 110)
        print(f"PAYMENT YEAR: {payment_year}")
        print(f"ARCHIVE     : {path}")
        print("=" * 110)

        if not path.exists():
            print("ERROR: archive missing")
            print()
            continue

        with zipfile.ZipFile(path) as zf:
            candidates = find_partc_county_workbooks(zf)

            print(
                f"Part C county workbook candidates: {len(candidates)}"
            )

            for candidate in candidates:
                print(f"  {candidate}")

            if len(candidates) != 1:
                print(
                    "RESULT: REVIEW — expected exactly one "
                    "Part C county workbook."
                )
                print()

                records.append(
                    {
                        "payment_year": payment_year,
                        "status": "REVIEW",
                        "member": "",
                        "sheet": "",
                        "header_row": "",
                        "column_count": "",
                        "signature": "",
                    }
                )

                continue

            member = candidates[0]
            payload = zf.read(member)
            extension = Path(member).suffix.lower()

        result = locate_header(payload, extension)

        if result is None:
            print("RESULT: REVIEW — logical header not located.")
            print()

            records.append(
                {
                    "payment_year": payment_year,
                    "status": "REVIEW",
                    "member": member,
                    "sheet": "",
                    "header_row": "",
                    "column_count": "",
                    "signature": "",
                }
            )

            continue

        _, sheet, header_index, header = result

        # Remove only trailing blank physical cells.
        while header and not clean(header[-1]):
            header.pop()

        signature = normalize_header_for_signature(header)

        print(f"Selected workbook : {member}")
        print(f"Selected sheet    : {sheet!r}")
        print(f"Physical header row: {header_index + 1}")
        print(f"Physical columns  : {len(header)}")
        print()

        for colno, value in enumerate(header, start=1):
            rendered = value if value else "<BLANK>"
            print(f"  COL {colno:02d}: {rendered!r}")

        print()
        print("RESULT: OBSERVED")
        print()

        records.append(
            {
                "payment_year": payment_year,
                "status": "OBSERVED",
                "member": member,
                "sheet": sheet,
                "header_row": header_index + 1,
                "column_count": len(header),
                "signature": signature,
            }
        )

    print("=" * 110)
    print("CROSS-YEAR LOGICAL HEADER SUMMARY")
    print("=" * 110)
    print()

    observed = [
        x for x in records
        if x["status"] == "OBSERVED"
    ]

    signatures = Counter(
        x["signature"]
        for x in observed
    )

    print(f"Years observed             : {len(observed)}")
    print(f"Distinct exact signatures  : {len(signatures)}")
    print()

    signature_ids = {
        signature: i
        for i, signature in enumerate(
            signatures.keys(),
            start=1,
        )
    }

    for record in observed:
        sid = signature_ids[record["signature"]]

        print(
            f"CY{record['payment_year']}: "
            f"signature={sid} | "
            f"header_row={record['header_row']} | "
            f"columns={record['column_count']}"
        )

    print()
    print("SIGNATURE DEFINITIONS")
    print("-" * 110)

    for signature, sid in signature_ids.items():
        years = [
            x["payment_year"]
            for x in observed
            if x["signature"] == signature
        ]

        print()
        print(f"SIGNATURE {sid}")
        print(f"Years: {', '.join(years)}")

        for colno, value in enumerate(signature, start=1):
            print(f"  {colno:02d}. {value}")

    review_count = sum(
        1 for x in records
        if x["status"] != "OBSERVED"
    )

    print()
    print("=" * 110)
    print("DIAGNOSTIC RESULT")
    print("=" * 110)
    print(f"Expected years : 11")
    print(f"Observed years : {len(observed)}")
    print(f"Review years   : {review_count}")
    print()
    print(
        "No source artifacts were modified. "
        "No database writes were performed."
    )


if __name__ == "__main__":
    main()