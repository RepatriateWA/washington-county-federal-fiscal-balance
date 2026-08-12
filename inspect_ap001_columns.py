from etl.common.db import get_connection

TABLES = [
    ("assistance", "award_transaction"),
    ("assistance", "award"),
    ("assistance", "assistance_listing"),
    ("assistance", "assistance_type"),
    ("assistance", "award_transaction_defc"),
    ("procurement", "recipient"),
    ("procurement", "agency"),
    ("procurement", "place"),
    ("reference", "extraordinary_funding_code"),
    ("reference", "state_registry"),
    ("reference", "county_registry"),
]

def main():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            table_schema,
            table_name,
            ordinal_position,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE (table_schema, table_name) IN (
            ('assistance', 'award_transaction'),
            ('assistance', 'award'),
            ('assistance', 'assistance_listing'),
            ('assistance', 'assistance_type'),
            ('assistance', 'award_transaction_defc'),
            ('procurement', 'recipient'),
            ('procurement', 'agency'),
            ('procurement', 'place'),
            ('reference', 'extraordinary_funding_code'),
            ('reference', 'state_registry'),
            ('reference', 'county_registry')
        )
        ORDER BY
            table_schema,
            table_name,
            ordinal_position;
        """
    )

    for row in cur.fetchall():
        print("|".join(str(value) for value in row))

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()