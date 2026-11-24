
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218D - INDEPENDENT CMS EXPENDITURE RECONCILIATION'
\echo 'FY2018-FY2024 / READ ONLY / ZERO-TOLERANCE GATES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '180s';

\echo ''
\echo '1. MEDICAID SOURCE-TO-REPORTING RECONCILIATION'

WITH source AS (
    SELECT
        m.fiscal_year,
        COUNT(*) AS source_rows,
        SUM(m.federal_share) AS source_dollars,
        COUNT(*) FILTER (
            WHERE m.control_total_label IS DISTINCT FROM
                  'Total Net Expenditures'
               OR m.expenditure_time_basis IS DISTINCT FROM
                  'FEDERAL_FISCAL_YEAR'
               OR m.source_file IS NULL
               OR m.source_worksheet IS NULL
               OR m.source_row_number IS NULL
        ) AS invalid_provenance_rows
    FROM cms.medicaid_state_control_total m
    JOIN reference.state_registry s
      ON s.state_id = m.state_id
    WHERE s.state_abbreviation = 'WA'
      AND m.fiscal_year BETWEEN 2018 AND 2024
    GROUP BY m.fiscal_year
),
reported AS (
    SELECT
        fiscal_year,
        COUNT(*) AS reporting_rows,
        SUM(federal_expenditure_amount) AS reported_dollars
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
)
SELECT
    y.fiscal_year,
    COALESCE(s.source_rows,0) AS source_rows,
    s.source_dollars,
    COALESCE(r.reporting_rows,0) AS reporting_rows,
    r.reported_dollars,
    s.source_dollars-r.reported_dollars AS difference_dollars,
    COALESCE(s.invalid_provenance_rows,0) AS invalid_provenance_rows
FROM generate_series(2018,2024) y(fiscal_year)
LEFT JOIN source s USING (fiscal_year)
LEFT JOIN reported r USING (fiscal_year)
ORDER BY y.fiscal_year;

\echo ''
\echo '2. CHIP SOURCE-TO-REPORTING RECONCILIATION'

WITH source AS (
    SELECT
        fiscal_year,
        COUNT(*) AS all_control_rows,
        COUNT(*) FILTER (
            WHERE is_additive_expenditure IS TRUE
              AND is_financing_adjustment IS FALSE
        ) AS additive_rows,
        COUNT(*) FILTER (
            WHERE is_financing_adjustment IS TRUE
        ) AS financing_adjustment_rows,
        SUM(federal_share) FILTER (
            WHERE is_additive_expenditure IS TRUE
              AND is_financing_adjustment IS FALSE
        ) AS source_dollars,
        SUM(federal_share) FILTER (
            WHERE is_financing_adjustment IS TRUE
        ) AS excluded_financing_adjustment_dollars,
        COUNT(*) FILTER (
            WHERE worksheet_type NOT IN (
                'CHIP','MCHIP','MCHIP_20_PERCENT'
            )
               OR is_additive_expenditure IS NULL
               OR is_financing_adjustment IS NULL
               OR source_workbook IS NULL
               OR source_sheet IS NULL
               OR source_row IS NULL
        ) AS invalid_provenance_rows,
        COUNT(*) FILTER (
            WHERE worksheet_type = 'CHIP'
              AND is_additive_expenditure IS TRUE
              AND is_financing_adjustment IS FALSE
        ) AS chip_rows,
        COUNT(*) FILTER (
            WHERE worksheet_type = 'MCHIP'
              AND is_additive_expenditure IS TRUE
              AND is_financing_adjustment IS FALSE
        ) AS mchip_rows,
        COUNT(*) FILTER (
            WHERE worksheet_type = 'MCHIP_20_PERCENT'
              AND is_additive_expenditure IS FALSE
              AND is_financing_adjustment IS TRUE
        ) AS adjustment_rows
    FROM chip.v_cms21_control_totals
    WHERE state_abbreviation = 'WA'
      AND fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
),
reported AS (
    SELECT
        fiscal_year,
        COUNT(*) AS reporting_rows,
        SUM(federal_expenditure_amount) AS reported_dollars
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
    GROUP BY fiscal_year
)
SELECT
    y.fiscal_year,
    s.all_control_rows,
    s.additive_rows,
    s.financing_adjustment_rows,
    s.source_dollars,
    r.reported_dollars,
    s.source_dollars-r.reported_dollars AS difference_dollars,
    s.excluded_financing_adjustment_dollars,
    s.invalid_provenance_rows,
    s.chip_rows,
    s.mchip_rows,
    s.adjustment_rows
FROM generate_series(2018,2024) y(fiscal_year)
LEFT JOIN source s USING (fiscal_year)
LEFT JOIN reported r USING (fiscal_year)
ORDER BY y.fiscal_year;

\echo ''
\echo '3. COMBINED CMS CONTROL TOTALS'

WITH controls AS (
    SELECT
        fiscal_year,
        'MEDICAID'::text AS program,
        federal_expenditure_amount::numeric AS dollars
    FROM reporting.v_washington_medicaid_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024

    UNION ALL

    SELECT
        fiscal_year,
        'CHIP',
        federal_expenditure_amount::numeric
    FROM reporting.v_washington_chip_expenditures
    WHERE fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    fiscal_year,
    SUM(dollars) FILTER (
        WHERE program='MEDICAID'
    ) AS medicaid_dollars,
    SUM(dollars) FILTER (
        WHERE program='CHIP'
    ) AS chip_dollars,
    SUM(dollars) AS combined_cms_dollars
FROM controls
GROUP BY fiscal_year
ORDER BY fiscal_year;

\echo ''
\echo '4. FAIL-CLOSED SOURCE RECONCILIATION GATE'

DO $gate$
DECLARE
    v_bad_medicaid bigint;
    v_bad_chip bigint;
BEGIN
    WITH expected AS (
        SELECT generate_series(2018,2024) AS fiscal_year
    ),
    source AS (
        SELECT
            m.fiscal_year,
            COUNT(*) AS n,
            SUM(m.federal_share) AS dollars,
            COUNT(*) FILTER (
                WHERE m.control_total_label IS DISTINCT FROM
                      'Total Net Expenditures'
                   OR m.expenditure_time_basis IS DISTINCT FROM
                      'FEDERAL_FISCAL_YEAR'
                   OR m.federal_share IS NULL
                   OR m.federal_share <= 0
                   OR m.source_file IS NULL
                   OR m.source_worksheet IS NULL
                   OR m.source_row_number IS NULL
            ) AS invalid_rows
        FROM cms.medicaid_state_control_total m
        JOIN reference.state_registry s
          ON s.state_id=m.state_id
        WHERE s.state_abbreviation='WA'
          AND m.fiscal_year BETWEEN 2018 AND 2024
        GROUP BY m.fiscal_year
    ),
    reported AS (
        SELECT
            fiscal_year,
            COUNT(*) AS n,
            SUM(federal_expenditure_amount) AS dollars
        FROM reporting.v_washington_medicaid_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    )
    SELECT COUNT(*) INTO v_bad_medicaid
    FROM expected e
    LEFT JOIN source s USING (fiscal_year)
    LEFT JOIN reported r USING (fiscal_year)
    WHERE COALESCE(s.n,0) <> 1
       OR COALESCE(r.n,0) <> 1
       OR COALESCE(s.invalid_rows,0) <> 0
       OR s.dollars IS DISTINCT FROM r.dollars;

    WITH expected AS (
        SELECT generate_series(2018,2024) AS fiscal_year
    ),
    source AS (
        SELECT
            fiscal_year,
            COUNT(*) AS all_rows,
            COUNT(*) FILTER (
                WHERE worksheet_type='CHIP'
                  AND is_additive_expenditure IS TRUE
                  AND is_financing_adjustment IS FALSE
            ) AS chip_rows,
            COUNT(*) FILTER (
                WHERE worksheet_type='MCHIP'
                  AND is_additive_expenditure IS TRUE
                  AND is_financing_adjustment IS FALSE
            ) AS mchip_rows,
            COUNT(*) FILTER (
                WHERE worksheet_type='MCHIP_20_PERCENT'
                  AND is_additive_expenditure IS FALSE
                  AND is_financing_adjustment IS TRUE
            ) AS adjustment_rows,
            COUNT(*) FILTER (
                WHERE source_workbook IS NULL
                   OR source_sheet IS NULL
                   OR source_row IS NULL
                   OR federal_share IS NULL
            ) AS invalid_rows,
            SUM(federal_share) FILTER (
                WHERE is_additive_expenditure IS TRUE
                  AND is_financing_adjustment IS FALSE
            ) AS dollars
        FROM chip.v_cms21_control_totals
        WHERE state_abbreviation='WA'
          AND fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    ),
    reported AS (
        SELECT
            fiscal_year,
            COUNT(*) AS n,
            SUM(federal_expenditure_amount) AS dollars
        FROM reporting.v_washington_chip_expenditures
        WHERE fiscal_year BETWEEN 2018 AND 2024
        GROUP BY fiscal_year
    )
    SELECT COUNT(*) INTO v_bad_chip
    FROM expected e
    LEFT JOIN source s USING (fiscal_year)
    LEFT JOIN reported r USING (fiscal_year)
    WHERE COALESCE(s.all_rows,0) <> 3
       OR COALESCE(s.chip_rows,0) <> 1
       OR COALESCE(s.mchip_rows,0) <> 1
       OR COALESCE(s.adjustment_rows,0) <> 1
       OR COALESCE(s.invalid_rows,0) <> 0
       OR COALESCE(r.n,0) <> 1
       OR s.dollars IS DISTINCT FROM r.dollars;

    IF v_bad_medicaid <> 0 OR v_bad_chip <> 0 THEN
        RAISE EXCEPTION
            'ETL-218D BLOCK: Medicaid failures %, CHIP failures %',
            v_bad_medicaid,v_bad_chip;
    END IF;

    RAISE NOTICE
        'ETL-218D SOURCE RECONCILIATION PASS: 14 EXACT MATCHES, ZERO DOLLAR DISCREPANCY';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218D COMPLETE - READ ONLY'
