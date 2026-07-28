"""
ETL-004B — Load normalized procurement subagencies.

This loader inserts known subagencies required for award relationship
enrichment. It is idempotent and may be rerun safely.
"""

from __future__ import annotations

from dataclasses import dataclass

from etl.common.db import get_connection


@dataclass(frozen=True)
class SubagencyDefinition:
    agency_code: str
    agency_name: str
    parent_agency_code: str


SUBAGENCIES = (
    SubagencyDefinition(
        agency_code="8900",
        agency_name="Department of Energy",
        parent_agency_code="089",
    ),
)


def get_parent_agency_id(
    cur,
    *,
    parent_agency_code: str,
) -> int:
    """
    Resolve the parent agency ID.
    """
    cur.execute(
        """
        SELECT agency_id
        FROM procurement.agency
        WHERE agency_code = %s
          AND agency_level = 'AGENCY'
        ORDER BY agency_id
        LIMIT 2;
        """,
        (parent_agency_code,),
    )

    rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"Parent agency code {parent_agency_code!r} was not found."
        )

    if len(rows) > 1:
        raise ValueError(
            f"Parent agency code {parent_agency_code!r} matched "
            f"multiple agency rows."
        )

    return int(rows[0][0])


def upsert_subagency(
    cur,
    *,
    definition: SubagencyDefinition,
) -> tuple[int, bool]:
    """
    Insert or reconcile one normalized subagency.

    Returns:
        Tuple of agency ID and whether a new row was inserted.
    """
    parent_agency_id = get_parent_agency_id(
        cur,
        parent_agency_code=definition.parent_agency_code,
    )

    cur.execute(
        """
        SELECT
            agency_id,
            agency_name,
            parent_agency_id,
            agency_level
        FROM procurement.agency
        WHERE agency_code = %s
        ORDER BY agency_id
        LIMIT 2;
        """,
        (definition.agency_code,),
    )

    rows = cur.fetchall()

    if len(rows) > 1:
        raise ValueError(
            f"Agency code {definition.agency_code!r} matched "
            f"multiple rows."
        )

    normalized_name = definition.agency_name.upper()

    if rows:
        (
            agency_id,
            existing_name,
            existing_parent_id,
            existing_level,
        ) = rows[0]

        if (
            str(existing_name) != definition.agency_name
            or int(existing_parent_id) != parent_agency_id
            or str(existing_level) != "SUBAGENCY"
        ):
            raise ValueError(
                f"Existing agency code {definition.agency_code!r} "
                "does not match the expected subagency definition."
            )

        return int(agency_id), False

    cur.execute(
        """
        INSERT INTO procurement.agency (
            agency_code,
            agency_name,
            agency_name_normalized,
            parent_agency_id,
            agency_level
        )
        VALUES (%s, %s, %s, %s, 'SUBAGENCY')
        RETURNING agency_id;
        """,
        (
            definition.agency_code,
            definition.agency_name,
            normalized_name,
            parent_agency_id,
        ),
    )

    return int(cur.fetchone()[0]), True


def main() -> None:
    """
    Load required procurement subagencies.
    """
    conn = get_connection()

    inserted = 0
    existing = 0

    try:
        with conn:
            with conn.cursor() as cur:
                for definition in SUBAGENCIES:
                    agency_id, was_inserted = upsert_subagency(
                        cur,
                        definition=definition,
                    )

                    status = (
                        "INSERTED"
                        if was_inserted
                        else "EXISTING"
                    )

                    print(
                        f"{status}: "
                        f"{definition.agency_code} — "
                        f"{definition.agency_name} "
                        f"(agency_id={agency_id})"
                    )

                    if was_inserted:
                        inserted += 1
                    else:
                        existing += 1

        print()
        print("Procurement subagency load completed.")
        print(f"Inserted: {inserted}")
        print(f"Existing: {existing}")

    except Exception as exc:
        print()
        print("Procurement subagency load failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    finally:
        conn.close()


if __name__ == "__main__":
    main()