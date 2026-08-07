"""Load citation-backed DEFC classifications into PostgreSQL."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from etl.common.db import get_connection


SOURCE_FILE = Path(
    "data/reference/extraordinary_funding/"
    "defc_classification.csv"
)

VALID_FUNDING_FAMILIES = {
    "COVID",
    "IIJA",
    "OTHER_DISASTER",
    "WILDFIRE_SUPPRESSION",
    "OTHER_EMERGENCY",
    "NOT_DESIGNATED",
    "UNSPECIFIED_NON_COVID",
    "ORDINARY",
    "UNRESOLVED",
}

VALID_CONFIDENCE_VALUES = {
    "HIGH",
    "MEDIUM",
    "LOW",
    "UNRESOLVED",
    "HIGH_NON_COVID",
}


@dataclass(frozen=True)
class ClassificationRow:
    """One validated DEFC reference row."""

    defc_code: str
    official_description: str
    public_law_reference: str | None
    funding_family: str
    extraordinary_flag: bool | None
    covid_flag: bool
    iija_flag: bool
    confidence: str
    classification_source: str
    citation: str
    notes: str | None


def clean_required(
    value: str | None,
    *,
    field_name: str,
    row_number: int,
) -> str:
    """Clean one required text field."""

    cleaned = (value or "").strip()

    if not cleaned:
        raise ValueError(
            f"Row {row_number}: {field_name} is required."
        )

    return cleaned


def clean_optional(
    value: str | None,
) -> str | None:
    """Clean one optional text field."""

    cleaned = (value or "").strip()

    return cleaned or None


def parse_boolean(
    value: str | None,
    *,
    field_name: str,
    row_number: int,
    nullable: bool = False,
) -> bool | None:
    """Parse TRUE, FALSE, or an allowed unresolved value."""

    cleaned = (value or "").strip().upper()

    if cleaned == "TRUE":
        return True

    if cleaned == "FALSE":
        return False

    if nullable and cleaned in {
        "",
        "NULL",
        "NONE",
        "UNRESOLVED",
    }:
        return None

    expected = (
        "TRUE, FALSE, or UNRESOLVED"
        if nullable
        else "TRUE or FALSE"
    )

    raise ValueError(
        f"Row {row_number}: {field_name} must be {expected}; "
        f"found {value!r}."
    )


def read_source_rows() -> list[ClassificationRow]:
    """Read and validate the classification CSV."""

    if not SOURCE_FILE.is_file():
        raise FileNotFoundError(
            f"Classification file not found: {SOURCE_FILE}"
        )

    rows: list[ClassificationRow] = []
    observed_codes: set[str] = set()

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "defc_code",
            "official_description",
            "public_law_reference",
            "funding_family",
            "extraordinary_flag",
            "covid_flag",
            "iija_flag",
            "confidence",
            "classification_source",
            "citation",
            "notes",
        }

        actual_columns = set(
            reader.fieldnames or []
        )

        missing_columns = (
            required_columns - actual_columns
        )

        if missing_columns:
            raise ValueError(
                "Classification CSV is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row_number, raw in enumerate(
            reader,
            start=2,
        ):
            code = clean_required(
                raw.get("defc_code"),
                field_name="defc_code",
                row_number=row_number,
            ).upper()

            if code in observed_codes:
                raise ValueError(
                    f"Row {row_number}: duplicate DEFC code {code!r}."
                )

            observed_codes.add(code)

            funding_family = clean_required(
                raw.get("funding_family"),
                field_name="funding_family",
                row_number=row_number,
            ).upper()

            if funding_family not in VALID_FUNDING_FAMILIES:
                raise ValueError(
                    f"Row {row_number}: invalid funding_family "
                    f"{funding_family!r}."
                )

            confidence = clean_required(
                raw.get("confidence"),
                field_name="confidence",
                row_number=row_number,
            ).upper()

            if confidence not in VALID_CONFIDENCE_VALUES:
                raise ValueError(
                    f"Row {row_number}: invalid confidence "
                    f"{confidence!r}."
                )

            covid_flag = parse_boolean(
                raw.get("covid_flag"),
                field_name="covid_flag",
                row_number=row_number,
            )

            iija_flag = parse_boolean(
                raw.get("iija_flag"),
                field_name="iija_flag",
                row_number=row_number,
            )

            extraordinary_flag = parse_boolean(
                raw.get("extraordinary_flag"),
                field_name="extraordinary_flag",
                row_number=row_number,
                nullable=True,
            )

            if covid_flag and funding_family != "COVID":
                raise ValueError(
                    f"Row {row_number}: covid_flag requires "
                    "funding_family COVID."
                )

            if iija_flag and funding_family != "IIJA":
                raise ValueError(
                    f"Row {row_number}: iija_flag requires "
                    "funding_family IIJA."
                )

            if covid_flag and iija_flag:
                raise ValueError(
                    f"Row {row_number}: a DEFC code cannot be both "
                    "COVID and IIJA."
                )

            rows.append(
                ClassificationRow(
                    defc_code=code,
                    official_description=clean_required(
                        raw.get("official_description"),
                        field_name="official_description",
                        row_number=row_number,
                    ),
                    public_law_reference=clean_optional(
                        raw.get("public_law_reference")
                    ),
                    funding_family=funding_family,
                    extraordinary_flag=extraordinary_flag,
                    covid_flag=bool(covid_flag),
                    iija_flag=bool(iija_flag),
                    confidence=confidence,
                    classification_source=clean_required(
                        raw.get("classification_source"),
                        field_name="classification_source",
                        row_number=row_number,
                    ),
                    citation=clean_required(
                        raw.get("citation"),
                        field_name="citation",
                        row_number=row_number,
                    ),
                    notes=clean_optional(
                        raw.get("notes")
                    ),
                )
            )

    if not rows:
        raise ValueError(
            "Classification CSV contains no data rows."
        )

    return rows


def load_rows(
    rows: list[ClassificationRow],
) -> tuple[int, int, int]:
    """Upsert validated rows and return insertion statistics."""

    conn = get_connection()

    inserted = 0
    updated = 0
    unchanged = 0

    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    SELECT
                        official_description,
                        public_law_reference,
                        funding_family,
                        extraordinary_flag,
                        covid_flag,
                        iija_flag,
                        confidence,
                        classification_source,
                        citation,
                        notes
                    FROM reference.extraordinary_funding_code
                    WHERE defc_code = %s;
                    """,
                    (row.defc_code,),
                )

                existing = cur.fetchone()

                proposed = (
                    row.official_description,
                    row.public_law_reference,
                    row.funding_family,
                    row.extraordinary_flag,
                    row.covid_flag,
                    row.iija_flag,
                    row.confidence,
                    row.classification_source,
                    row.citation,
                    row.notes,
                )

                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO
                            reference.extraordinary_funding_code (
                                defc_code,
                                official_description,
                                public_law_reference,
                                funding_family,
                                extraordinary_flag,
                                covid_flag,
                                iija_flag,
                                confidence,
                                classification_source,
                                citation,
                                notes
                            )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        );
                        """,
                        (
                            row.defc_code,
                            *proposed,
                        ),
                    )

                    inserted += 1

                elif existing == proposed:
                    unchanged += 1

                else:
                    cur.execute(
                        """
                        UPDATE reference.extraordinary_funding_code
                        SET
                            official_description = %s,
                            public_law_reference = %s,
                            funding_family = %s,
                            extraordinary_flag = %s,
                            covid_flag = %s,
                            iija_flag = %s,
                            confidence = %s,
                            classification_source = %s,
                            citation = %s,
                            notes = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE defc_code = %s;
                        """,
                        (
                            *proposed,
                            row.defc_code,
                        ),
                    )

                    updated += 1

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return inserted, updated, unchanged


def main() -> None:
    print("=" * 72)
    print("ETL-005A.10 — Load Extraordinary Funding Codes")
    print("=" * 72)
    print(f"Source file: {SOURCE_FILE}")

    rows = read_source_rows()

    print(f"Validated source rows: {len(rows):,}")

    inserted, updated, unchanged = load_rows(
        rows
    )

    print()
    print("=" * 72)
    print("ETL-005A.10 SUMMARY")
    print("=" * 72)
    print(
        f"Rows inserted .................. {inserted:,}"
    )
    print(
        f"Rows updated ................... {updated:,}"
    )
    print(
        f"Rows unchanged ................. {unchanged:,}"
    )
    print(
        f"Reference rows represented ..... "
        f"{inserted + updated + unchanged:,}"
    )
    print("=" * 72)
    print()
    print(
        "Extraordinary funding codes loaded successfully."
    )


if __name__ == "__main__":
    main()