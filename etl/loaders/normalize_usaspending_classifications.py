"""
ETL-004A.3C — Normalize USAspending NAICS and PSC classifications.
"""

import argparse
from typing import Any

from etl.common.db import get_connection
from etl.common.usaspending import get_optional


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize USAspending NAICS and PSC classifications."
    )
    parser.add_argument("--load-batch-id", type=int, default=None)
    return parser.parse_args()


def get_target_load_batch_id(conn, requested_batch_id: int | None) -> int:
    with conn.cursor() as cur:
        if requested_batch_id is not None:
            cur.execute(
                """
                SELECT lb.load_batch_id, lb.load_status,
                       COUNT(raw.raw_award_transaction_id)
                FROM procurement.load_batch lb
                LEFT JOIN procurement.raw_award_transaction raw
                  ON raw.load_batch_id = lb.load_batch_id
                WHERE lb.load_batch_id = %s
                GROUP BY lb.load_batch_id, lb.load_status;
                """,
                (requested_batch_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Load batch {requested_batch_id} does not exist.")

            load_batch_id, load_status, raw_rows = row
            if load_status not in {"COMPLETED", "COMPLETED_WITH_REJECTIONS"}:
                raise ValueError(
                    f"Load batch {load_batch_id} has status {load_status!r}."
                )
            if raw_rows == 0:
                raise ValueError(f"Load batch {load_batch_id} contains no raw rows.")
            return int(load_batch_id)

        cur.execute(
            """
            SELECT raw.load_batch_id
            FROM procurement.raw_award_transaction raw
            JOIN procurement.load_batch lb
              ON lb.load_batch_id = raw.load_batch_id
            WHERE lb.load_status IN ('COMPLETED', 'COMPLETED_WITH_REJECTIONS')
            GROUP BY raw.load_batch_id
            ORDER BY raw.load_batch_id DESC
            LIMIT 1;
            """
        )
        row = cur.fetchone()

    if row is None:
        raise ValueError("No completed raw procurement load batch was found.")
    return int(row[0])


def read_raw_records(conn, load_batch_id: int) -> list[tuple[int, dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_row_number, raw_record
            FROM procurement.raw_award_transaction
            WHERE load_batch_id = %s
            ORDER BY source_row_number, raw_award_transaction_id;
            """,
            (load_batch_id,),
        )
        return [(int(row_number), record) for row_number, record in cur.fetchall()]


def derive_classifications(
    raw_rows: list[tuple[int, dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, str | None]]:
    naics: dict[str, str] = {}
    naics_codes_seen: set[str] = set()
    psc: dict[str, str | None] = {}

    for row_number, record in raw_rows:
        naics_code = get_optional(record, "NAICS")
        naics_description = get_optional(record, "NAICS_DESCRIPTION")

        if naics_code is not None:
            if not naics_code.isdigit() or not 2 <= len(naics_code) <= 6:
                raise ValueError(
                    f"Invalid NAICS code {naics_code!r} at source row {row_number}."
                )

            naics_codes_seen.add(naics_code)

            if naics_description is not None:
                existing = naics.get(naics_code)

                if existing is not None and existing != naics_description:
                    raise ValueError(
                        f"Conflicting descriptions for NAICS {naics_code!r}."
                    )

                naics[naics_code] = naics_description

        psc_code = get_optional(record, "PSC")
        psc_description = get_optional(record, "PSC_DESCRIPTION")

        if psc_code is not None:
            existing = psc.get(psc_code)

            if (
                existing is not None
                and psc_description is not None
                and existing != psc_description
            ):
                raise ValueError(
                    f"Conflicting descriptions for PSC {psc_code!r}."
                )

            if psc_code not in psc or psc_description is not None:
                psc[psc_code] = psc_description

    unresolved_naics = sorted(naics_codes_seen - set(naics))

    if unresolved_naics:
        raise ValueError(
            "The following NAICS codes have no description anywhere "
            f"in the source batch: {', '.join(unresolved_naics)}"
        )

    return naics, psc

def upsert_naics(conn, rows: dict[str, str]) -> tuple[int, int]:
    sql = """
        INSERT INTO procurement.naics (
            naics_code, naics_description, naics_year
        )
        VALUES (%s, %s, NULL)
        ON CONFLICT (naics_code)
        DO UPDATE SET naics_description = EXCLUDED.naics_description
        RETURNING (xmax = 0) AS inserted;
    """
    inserted = updated = 0
    with conn.cursor() as cur:
        for code in sorted(rows):
            cur.execute(sql, (code, rows[code]))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def upsert_psc(conn, rows: dict[str, str | None]) -> tuple[int, int]:
    sql = """
        INSERT INTO procurement.psc (
            psc_code, psc_description, product_or_service
        )
        VALUES (%s, %s, NULL)
        ON CONFLICT (psc_code)
        DO UPDATE SET
            psc_description = COALESCE(
                EXCLUDED.psc_description,
                procurement.psc.psc_description
            )
        RETURNING (xmax = 0) AS inserted;
    """
    inserted = updated = 0
    with conn.cursor() as cur:
        for code in sorted(rows):
            cur.execute(sql, (code, rows[code]))
            if bool(cur.fetchone()[0]):
                inserted += 1
            else:
                updated += 1
    return inserted, updated


def validate(conn, naics: dict[str, str], psc: dict[str, str | None]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT naics_code FROM procurement.naics WHERE naics_code = ANY(%s);",
            (list(naics),),
        )
        loaded_naics = {row[0] for row in cur.fetchall()}

        cur.execute(
            "SELECT psc_code FROM procurement.psc WHERE psc_code = ANY(%s);",
            (list(psc),),
        )
        loaded_psc = {row[0] for row in cur.fetchall()}

    missing_naics = set(naics) - loaded_naics
    missing_psc = set(psc) - loaded_psc

    if missing_naics:
        raise ValueError("Missing NAICS codes: " + ", ".join(sorted(missing_naics)))
    if missing_psc:
        raise ValueError("Missing PSC codes: " + ", ".join(sorted(missing_psc)))


def main() -> None:
    args = parse_arguments()
    print("=" * 68)
    print("ETL-004A.3C — Normalize USAspending Classifications")
    print("=" * 68)

    conn = get_connection()
    try:
        batch_id = get_target_load_batch_id(conn, args.load_batch_id)
        print(f"Target raw load batch: {batch_id}")

        raw_rows = read_raw_records(conn, batch_id)
        print(f"Raw observations read: {len(raw_rows):,}")

        naics, psc = derive_classifications(raw_rows)
        print(f"Distinct NAICS codes derived: {len(naics):,}")
        print(f"Distinct PSC codes derived: {len(psc):,}")

        ni, nu = upsert_naics(conn, naics)
        pi, pu = upsert_psc(conn, psc)

        validate(conn, naics, psc)
        conn.commit()

        print(f"NAICS inserted: {ni:,}")
        print(f"NAICS updated: {nu:,}")
        print(f"PSC inserted: {pi:,}")
        print(f"PSC updated: {pu:,}")
        print("Classification validation: PASS")
        print("ETL-004A.3C completed successfully.")

    except Exception as exc:
        conn.rollback()
        print("ETL-004A.3C failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()