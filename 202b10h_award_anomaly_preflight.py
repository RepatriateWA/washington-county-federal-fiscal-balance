from collections import Counter

from etl.common.db import get_connection
from etl.loaders.normalize_usaspending_awards import (
    read_raw_award_rows,
    build_award_records,
)

conn = get_connection()

try:
    conn.set_session(readonly=True, autocommit=False)

    for batch_id in (22, 23):
        raw_rows = read_raw_award_rows(
            conn, load_batch_id=batch_id
        )

        awards, anomalies = build_award_records(
            raw_rows, load_batch_id=batch_id
        )

        counts = Counter(
            anomaly["anomaly_code"]
            for anomaly in anomalies
        )

        print(f"\nBATCH {batch_id}")
        print(f"Raw observations: {len(raw_rows):,}")
        print(f"Distinct awards: {len(awards):,}")
        print(f"Award anomaly groups: {len(anomalies):,}")

        for code, count in sorted(counts.items()):
            print(f"  {code}: {count:,}")

    conn.rollback()

finally:
    conn.close()