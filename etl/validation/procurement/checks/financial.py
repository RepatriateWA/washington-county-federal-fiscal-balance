"""
ETL-114C.1 procurement financial-certification checks.

The transaction-level financial source of truth is:

    raw_award_transaction.raw_record
        ->> 'federal_action_obligation'

The normalized counterpart is:

    award_transaction.federal_action_obligation

All reconciliation uses source_row_number within load_batch_id so that
each raw observation is compared with its exact normalized transaction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from etl.validation.procurement.models import (
    CertificationCheck,
    CheckStatus,
)


RAW_OBLIGATION_EXPRESSION = """
CASE
    WHEN BTRIM(
        raw.raw_record ->> 'federal_action_obligation'
    ) ~ '^[+-]?[0-9]+([.][0-9]+)?$'
    THEN BTRIM(
        raw.raw_record ->> 'federal_action_obligation'
    )::numeric
    ELSE NULL
END
"""


def money(value: Any) -> str:
    """
    Format a database numeric value as U.S. currency.
    """
    amount = Decimal(str(value or 0))
    return f"${amount:,.2f}"


def pass_or_fail(condition: bool) -> CheckStatus:
    return (
        CheckStatus.PASS
        if condition
        else CheckStatus.FAIL
    )


def check_batch_obligation_totals(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-001: Raw and normalized batch obligation totals reconcile.
    """
    cur.execute(
        f"""
        WITH paired AS (
            SELECT
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation,
                txn.federal_action_obligation
                    AS normalized_obligation
            FROM procurement.raw_award_transaction AS raw
            JOIN procurement.award_transaction AS txn
              ON txn.load_batch_id = raw.load_batch_id
             AND txn.source_row_number =
                 raw.source_row_number
            WHERE raw.load_batch_id = %s
        )
        SELECT
            COUNT(*) AS paired_rows,
            COUNT(*) FILTER (
                WHERE raw_obligation IS NULL
            ) AS invalid_raw_rows,
            COALESCE(
                SUM(raw_obligation),
                0
            ) AS raw_total,
            COALESCE(
                SUM(normalized_obligation),
                0
            ) AS normalized_total
        FROM paired;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Batch obligation reconciliation returned no result."
        )

    paired_rows = int(row[0])
    invalid_raw_rows = int(row[1])
    raw_total = Decimal(row[2])
    normalized_total = Decimal(row[3])
    difference = normalized_total - raw_total

    passed = (
        paired_rows > 0
        and invalid_raw_rows == 0
        and difference == Decimal("0")
    )

    return CertificationCheck(
        check_code="FIN-001",
        section="FINANCIAL CERTIFICATION",
        label="Batch obligation totals reconcile",
        status=pass_or_fail(passed),
        observed_value=money(difference),
        expected_value="$0.00 difference",
        detail=(
            None
            if passed
            else (
                f"Raw total {money(raw_total)}; normalized total "
                f"{money(normalized_total)}; difference "
                f"{money(difference)}."
            )
        ),
        evidence={
            "paired_rows": paired_rows,
            "invalid_raw_rows": invalid_raw_rows,
            "raw_total": str(raw_total),
            "normalized_total": str(normalized_total),
            "difference": str(difference),
        },
    )


def check_award_obligation_totals(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-002: Every award reconciles independently.
    """
    cur.execute(
        f"""
        WITH paired AS (
            SELECT
                txn.award_id,
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation,
                txn.federal_action_obligation
                    AS normalized_obligation
            FROM procurement.raw_award_transaction AS raw
            JOIN procurement.award_transaction AS txn
              ON txn.load_batch_id = raw.load_batch_id
             AND txn.source_row_number =
                 raw.source_row_number
            WHERE raw.load_batch_id = %s
        ),
        award_totals AS (
            SELECT
                award_id,
                COUNT(*) AS transaction_count,
                COUNT(*) FILTER (
                    WHERE raw_obligation IS NULL
                ) AS invalid_raw_rows,
                COALESCE(
                    SUM(raw_obligation),
                    0
                ) AS raw_total,
                COALESCE(
                    SUM(normalized_obligation),
                    0
                ) AS normalized_total
            FROM paired
            GROUP BY award_id
        )
        SELECT
            COUNT(*) AS award_count,
            COUNT(*) FILTER (
                WHERE invalid_raw_rows > 0
                   OR normalized_total <> raw_total
            ) AS mismatched_awards,
            COALESCE(
                MAX(
                    ABS(normalized_total - raw_total)
                ),
                0
            ) AS maximum_difference
        FROM award_totals;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Award obligation reconciliation returned no result."
        )

    award_count = int(row[0])
    mismatched_awards = int(row[1])
    maximum_difference = Decimal(row[2])

    passed = (
        award_count > 0
        and mismatched_awards == 0
    )

    return CertificationCheck(
        check_code="FIN-002",
        section="FINANCIAL CERTIFICATION",
        label="Award obligation totals reconcile",
        status=pass_or_fail(passed),
        observed_value=(
            f"{award_count - mismatched_awards}/"
            f"{award_count} awards"
        ),
        expected_value="all awards",
        detail=(
            None
            if passed
            else (
                f"{mismatched_awards} awards failed reconciliation; "
                f"maximum difference was "
                f"{money(maximum_difference)}."
            )
        ),
        evidence={
            "award_count": award_count,
            "reconciled_awards": (
                award_count - mismatched_awards
            ),
            "mismatched_awards": mismatched_awards,
            "maximum_absolute_difference": str(
                maximum_difference
            ),
        },
    )


def check_transaction_obligations(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-003: Every transaction obligation matches its raw source row.
    """
    cur.execute(
        f"""
        WITH paired AS (
            SELECT
                raw.source_row_number,
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation,
                txn.federal_action_obligation
                    AS normalized_obligation
            FROM procurement.raw_award_transaction AS raw
            JOIN procurement.award_transaction AS txn
              ON txn.load_batch_id = raw.load_batch_id
             AND txn.source_row_number =
                 raw.source_row_number
            WHERE raw.load_batch_id = %s
        )
        SELECT
            COUNT(*) AS paired_rows,
            COUNT(*) FILTER (
                WHERE raw_obligation IS NULL
                   OR raw_obligation
                      IS DISTINCT FROM
                      normalized_obligation
            ) AS mismatched_rows,
            COALESCE(
                MAX(
                    ABS(
                        normalized_obligation
                        - raw_obligation
                    )
                ) FILTER (
                    WHERE raw_obligation IS NOT NULL
                ),
                0
            ) AS maximum_difference
        FROM paired;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Transaction obligation reconciliation "
            "returned no result."
        )

    paired_rows = int(row[0])
    mismatched_rows = int(row[1])
    maximum_difference = Decimal(row[2])

    passed = (
        paired_rows > 0
        and mismatched_rows == 0
    )

    return CertificationCheck(
        check_code="FIN-003",
        section="FINANCIAL CERTIFICATION",
        label="Transaction obligations reconcile",
        status=pass_or_fail(passed),
        observed_value=(
            f"{paired_rows - mismatched_rows}/"
            f"{paired_rows} rows"
        ),
        expected_value="all transactions",
        detail=(
            None
            if passed
            else (
                f"{mismatched_rows} transaction rows differ; "
                f"maximum difference was "
                f"{money(maximum_difference)}."
            )
        ),
        evidence={
            "paired_rows": paired_rows,
            "reconciled_rows": (
                paired_rows - mismatched_rows
            ),
            "mismatched_rows": mismatched_rows,
            "maximum_absolute_difference": str(
                maximum_difference
            ),
        },
    )


def check_negative_obligations_preserved(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-004: De-obligations remain negative and financially intact.
    """
    cur.execute(
        f"""
        WITH paired AS (
            SELECT
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation,
                txn.federal_action_obligation
                    AS normalized_obligation
            FROM procurement.raw_award_transaction AS raw
            JOIN procurement.award_transaction AS txn
              ON txn.load_batch_id = raw.load_batch_id
             AND txn.source_row_number =
                 raw.source_row_number
            WHERE raw.load_batch_id = %s
        )
        SELECT
            COUNT(*) FILTER (
                WHERE raw_obligation < 0
            ) AS raw_negative_count,
            COUNT(*) FILTER (
                WHERE normalized_obligation < 0
            ) AS normalized_negative_count,
            COALESCE(
                SUM(raw_obligation) FILTER (
                    WHERE raw_obligation < 0
                ),
                0
            ) AS raw_negative_total,
            COALESCE(
                SUM(normalized_obligation) FILTER (
                    WHERE normalized_obligation < 0
                ),
                0
            ) AS normalized_negative_total
        FROM paired;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Negative-obligation check returned no result."
        )

    raw_count = int(row[0])
    normalized_count = int(row[1])
    raw_total = Decimal(row[2])
    normalized_total = Decimal(row[3])

    passed = (
        raw_count == normalized_count
        and raw_total == normalized_total
    )

    return CertificationCheck(
        check_code="FIN-004",
        section="FINANCIAL CERTIFICATION",
        label="Negative obligations preserved",
        status=pass_or_fail(passed),
        observed_value=(
            f"{normalized_count} rows, "
            f"{money(normalized_total)}"
        ),
        expected_value=(
            f"{raw_count} rows, {money(raw_total)}"
        ),
        detail=(
            None
            if passed
            else (
                "Negative-obligation counts or totals changed "
                "during normalization."
            )
        ),
        evidence={
            "raw_negative_count": raw_count,
            "normalized_negative_count": normalized_count,
            "raw_negative_total": str(raw_total),
            "normalized_negative_total": str(
                normalized_total
            ),
        },
    )


def check_zero_obligations_preserved(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-005: Legitimate zero-dollar transactions are retained.
    """
    cur.execute(
        f"""
        WITH paired AS (
            SELECT
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation,
                txn.federal_action_obligation
                    AS normalized_obligation
            FROM procurement.raw_award_transaction AS raw
            JOIN procurement.award_transaction AS txn
              ON txn.load_batch_id = raw.load_batch_id
             AND txn.source_row_number =
                 raw.source_row_number
            WHERE raw.load_batch_id = %s
        )
        SELECT
            COUNT(*) FILTER (
                WHERE raw_obligation = 0
            ) AS raw_zero_count,
            COUNT(*) FILTER (
                WHERE normalized_obligation = 0
            ) AS normalized_zero_count
        FROM paired;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Zero-obligation check returned no result."
        )

    raw_count = int(row[0])
    normalized_count = int(row[1])
    passed = raw_count == normalized_count

    return CertificationCheck(
        check_code="FIN-005",
        section="FINANCIAL CERTIFICATION",
        label="Zero-dollar transactions preserved",
        status=pass_or_fail(passed),
        observed_value=normalized_count,
        expected_value=raw_count,
        detail=(
            None
            if passed
            else (
                "The number of zero-dollar transactions changed "
                "during normalization."
            )
        ),
        evidence={
            "raw_zero_count": raw_count,
            "normalized_zero_count": normalized_count,
        },
    )


def check_obligation_values_valid(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-006: Required transaction obligation values are populated and
    valid in both raw and normalized data.
    """
    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE raw.raw_record
                      ->> 'federal_action_obligation'
                      IS NULL
                   OR BTRIM(
                        raw.raw_record
                        ->> 'federal_action_obligation'
                      ) = ''
            ) AS raw_null_or_blank,
            COUNT(*) FILTER (
                WHERE BTRIM(
                    raw.raw_record
                    ->> 'federal_action_obligation'
                ) <> ''
                  AND BTRIM(
                    raw.raw_record
                    ->> 'federal_action_obligation'
                  ) !~ '^[+-]?[0-9]+([.][0-9]+)?$'
            ) AS raw_malformed,
            COUNT(*) FILTER (
                WHERE txn.federal_action_obligation
                      IS NULL
            ) AS normalized_null
        FROM procurement.raw_award_transaction AS raw
        LEFT JOIN procurement.award_transaction AS txn
          ON txn.load_batch_id = raw.load_batch_id
         AND txn.source_row_number =
             raw.source_row_number
        WHERE raw.load_batch_id = %s;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Obligation validity check returned no result."
        )

    raw_null_or_blank = int(row[0])
    raw_malformed = int(row[1])
    normalized_null = int(row[2])

    invalid_count = (
        raw_null_or_blank
        + raw_malformed
        + normalized_null
    )

    passed = invalid_count == 0

    return CertificationCheck(
        check_code="FIN-006",
        section="FINANCIAL CERTIFICATION",
        label="Obligation values are valid",
        status=pass_or_fail(passed),
        observed_value=invalid_count,
        expected_value=0,
        detail=(
            None
            if passed
            else (
                f"Raw blank/null: {raw_null_or_blank}; "
                f"raw malformed: {raw_malformed}; "
                f"normalized null: {normalized_null}."
            )
        ),
        evidence={
            "raw_null_or_blank": raw_null_or_blank,
            "raw_malformed": raw_malformed,
            "normalized_null": normalized_null,
            "total_invalid": invalid_count,
        },
    )


def check_monetary_precision(
    cur,
    load_batch_id: int,
) -> CertificationCheck:
    """
    FIN-007: Source values and normalized schema preserve cent-level
    precision without hidden rounding.
    """
    cur.execute(
        f"""
        WITH raw_values AS (
            SELECT
                BTRIM(
                    raw.raw_record
                    ->> 'federal_action_obligation'
                ) AS raw_text,
                {RAW_OBLIGATION_EXPRESSION} AS raw_obligation
            FROM procurement.raw_award_transaction AS raw
            WHERE raw.load_batch_id = %s
        ),
        column_definition AS (
            SELECT
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'procurement'
              AND table_name = 'award_transaction'
              AND column_name =
                  'federal_action_obligation'
        )
        SELECT
            definition.numeric_precision,
            definition.numeric_scale,
            COUNT(*) FILTER (
                WHERE values.raw_obligation IS NOT NULL
                  AND values.raw_obligation
                      <> ROUND(values.raw_obligation, 2)
            ) AS overprecision_rows
        FROM raw_values AS values
        CROSS JOIN column_definition AS definition
        GROUP BY
            definition.numeric_precision,
            definition.numeric_scale;
        """,
        (load_batch_id,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Monetary-precision check returned no result. "
            "The normalized obligation column may not exist."
        )

    precision = int(row[0])
    scale = int(row[1])
    overprecision_rows = int(row[2])

    passed = (
        precision == 20
        and scale == 2
        and overprecision_rows == 0
    )

    return CertificationCheck(
        check_code="FIN-007",
        section="FINANCIAL CERTIFICATION",
        label="Monetary precision preserved",
        status=pass_or_fail(passed),
        observed_value=(
            f"NUMERIC({precision},{scale}); "
            f"{overprecision_rows} overprecision rows"
        ),
        expected_value=(
            "NUMERIC(20,2); 0 overprecision rows"
        ),
        detail=(
            None
            if passed
            else (
                "The normalized schema or raw values do not "
                "conform to cent-level monetary precision."
            )
        ),
        evidence={
            "numeric_precision": precision,
            "numeric_scale": scale,
            "raw_overprecision_rows": overprecision_rows,
        },
    )


FINANCIAL_CHECKS = (
    check_batch_obligation_totals,
    check_award_obligation_totals,
    check_transaction_obligations,
    check_negative_obligations_preserved,
    check_zero_obligations_preserved,
    check_obligation_values_valid,
    check_monetary_precision,
)