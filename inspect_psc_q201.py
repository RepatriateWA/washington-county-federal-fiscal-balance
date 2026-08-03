from etl.common.db import get_connection


LOAD_BATCH_ID = 5
PSC_CODE = "Q201"


def main() -> None:
    sql = """
        SELECT
            raw_record ->> 'product_or_service_code'
                AS psc_code,
            raw_record ->> 'product_or_service_code_description'
                AS psc_description,
            COUNT(*) AS row_count,
            MIN(source_row_number) AS first_source_row,
            MAX(source_row_number) AS last_source_row
        FROM procurement.raw_award_transaction
        WHERE load_batch_id = %s
          AND raw_record ->> 'product_or_service_code' = %s
        GROUP BY
            raw_record ->> 'product_or_service_code',
            raw_record ->> 'product_or_service_code_description'
        ORDER BY
            row_count DESC,
            psc_description;
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (LOAD_BATCH_ID, PSC_CODE))
            rows = cur.fetchall()

        print(f"PSC: {PSC_CODE}")
        print(f"Distinct descriptions: {len(rows)}")
        print()

        for (
            psc_code,
            description,
            row_count,
            first_source_row,
            last_source_row,
        ) in rows:
            print(
                f"code={psc_code!r} "
                f"description={description!r} "
                f"rows={row_count:,} "
                f"first_row={first_source_row} "
                f"last_row={last_source_row}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()