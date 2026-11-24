
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218E - MEDICAID / CHIP CROSS-SOURCE OVERLAP AUDIT'
\echo 'FY2018-FY2024 / READ ONLY / NO POLICY CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '240s';

\echo ''
\echo '1. SOURCE POLICY COVERAGE'

SELECT
    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.ledger_treatment,
    p.methodology_version,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year
FROM reference.federal_inflow_source_policy p
WHERE p.inflow_family IN ('MEDICAID','CHIP')
   OR p.inflow_subfamily ILIKE '%MEDICAID%'
   OR p.inflow_subfamily ILIKE '%CHIP%'
ORDER BY p.inflow_family,
         p.inflow_subfamily,
         p.valid_from_fiscal_year;

\echo ''
\echo '2. PROGRAM-LEVEL CLASSIFICATIONS'

SELECT
    c.source_system,
    c.source_program_code,
    c.source_program_title,
    c.inflow_family,
    c.inflow_subfamily,
    c.overlap_risk,
    c.methodology_version,
    c.valid_from_fiscal_year,
    c.valid_through_fiscal_year
FROM reference.federal_inflow_program_classification c
WHERE c.source_program_code IN ('93.778','93.767')
ORDER BY c.source_program_code,
         c.valid_from_fiscal_year;

\echo ''
\echo '3. PROGRAM-LEVEL POLICY MAPPINGS'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping m
JOIN reference.federal_inflow_source_policy p
  ON p.federal_inflow_source_policy_id =
     m.federal_inflow_source_policy_id
WHERE m.source_program_code IN ('93.778','93.767')
ORDER BY m.source_program_code,
         m.valid_from_fiscal_year;

\echo ''
\echo '4. AWARD-LEVEL CLASSIFICATIONS'

SELECT
    a.source_system,
    a.source_program_code,
    a.source_award_identifier,
    a.inflow_family,
    a.inflow_subfamily,
    a.accounting_disposition,
    a.methodology_version,
    a.valid_from_fiscal_year,
    a.valid_through_fiscal_year
FROM reference.federal_inflow_award_classification a
WHERE a.source_program_code IN ('93.778','93.767')
ORDER BY a.source_program_code,
         a.valid_from_fiscal_year,
         a.source_award_identifier;

\echo ''
\echo '5. USAspending TRANSACTION PROFILE'

WITH transactions AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        cfda_number,
        assistance_transaction_id,
        federal_action_obligation,
        award_id_fain,
        award_id_uri
    FROM analysis.v_certified_assistance_ledger
    WHERE cfda_number IN ('93.778','93.767')
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
)
SELECT
    fiscal_year,
    cfda_number,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    COUNT(DISTINCT COALESCE(award_id_fain,award_id_uri))
        AS distinct_awards,
    SUM(federal_action_obligation) AS net_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions,
    SUM(federal_action_obligation) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_obligations
FROM transactions
GROUP BY fiscal_year,cfda_number
ORDER BY fiscal_year,cfda_number;

\echo ''
\echo '6. POLICY COVERAGE BY SOURCE YEAR'

WITH expected AS (
    SELECT
        y.fiscal_year,
        p.source_program_code
    FROM generate_series(2018,2024) y(fiscal_year)
    CROSS JOIN (
        VALUES ('93.778'),('93.767')
    ) p(source_program_code)
),
mappings AS (
    SELECT
        e.fiscal_year,
        e.source_program_code,
        COUNT(m.federal_inflow_program_policy_mapping_id)
            AS mapping_count,
        STRING_AGG(
            DISTINCT m.resolved_accounting_disposition,
            ', '
        ) AS mapped_dispositions
    FROM expected e
    LEFT JOIN reference.federal_inflow_program_policy_mapping m
      ON m.source_program_code=e.source_program_code
     AND m.source_system='USASPENDING_ASSISTANCE'
     AND e.fiscal_year BETWEEN
         m.valid_from_fiscal_year
         AND m.valid_through_fiscal_year
    GROUP BY e.fiscal_year,e.source_program_code
)
SELECT *
FROM mappings
ORDER BY fiscal_year,source_program_code;

\echo ''
\echo '7. AWARD CLASSIFICATION COVERAGE BY YEAR'

SELECT
    y.fiscal_year,
    a.source_program_code,
    a.accounting_disposition,
    COUNT(*) AS classification_rows
FROM generate_series(2018,2024) y(fiscal_year)
JOIN reference.federal_inflow_award_classification a
  ON y.fiscal_year BETWEEN
     a.valid_from_fiscal_year
     AND a.valid_through_fiscal_year
WHERE a.source_program_code IN ('93.778','93.767')
  AND a.source_system='USASPENDING_ASSISTANCE'
GROUP BY y.fiscal_year,
         a.source_program_code,
         a.accounting_disposition
ORDER BY y.fiscal_year,
         a.source_program_code,
         a.accounting_disposition;

\echo ''
\echo '8. POTENTIALLY ADDITIVE CORE-PROGRAM MAPPINGS'

SELECT
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year,
    m.methodology_version
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.source_system='USASPENDING_ASSISTANCE'
  AND m.source_program_code IN ('93.778','93.767')
  AND m.valid_from_fiscal_year <= 2024
  AND m.valid_through_fiscal_year >= 2018
  AND m.resolved_accounting_disposition
      NOT IN ('EXCLUDE_DUPLICATE','WITHHOLD_UNRESOLVED');

\echo ''
\echo '9. READ-ONLY POLICY SAFETY GATE'

DO $gate$
DECLARE
    v_bad_medicaid bigint;
    v_bad_chip bigint;
BEGIN
    WITH years AS (
        SELECT generate_series(2018,2024) AS fiscal_year
    ),
    coverage AS (
        SELECT
            y.fiscal_year,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                AS mapping_count,
            COUNT(*) FILTER (
                WHERE m.resolved_accounting_disposition
                      IS DISTINCT FROM 'EXCLUDE_DUPLICATE'
                  AND m.federal_inflow_program_policy_mapping_id
                      IS NOT NULL
            ) AS unsafe_count
        FROM years y
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system='USASPENDING_ASSISTANCE'
         AND m.source_program_code='93.778'
         AND y.fiscal_year BETWEEN
             m.valid_from_fiscal_year
             AND m.valid_through_fiscal_year
        GROUP BY y.fiscal_year
    )
    SELECT COUNT(*) INTO v_bad_medicaid
    FROM coverage
    WHERE mapping_count <> 1 OR unsafe_count <> 0;

    SELECT COUNT(*) INTO v_bad_chip
    FROM reference.federal_inflow_program_policy_mapping m
    WHERE m.source_system='USASPENDING_ASSISTANCE'
      AND m.source_program_code='93.767'
      AND m.valid_from_fiscal_year <= 2024
      AND m.valid_through_fiscal_year >= 2018
      AND m.resolved_accounting_disposition='INCLUDE_ADDITIVE';

    IF v_bad_medicaid <> 0 OR v_bad_chip <> 0 THEN
        RAISE EXCEPTION
            'ETL-218E BLOCK: Medicaid mapping failures %, CHIP additive mappings %',
            v_bad_medicaid,v_bad_chip;
    END IF;

    RAISE NOTICE
        'ETL-218E POLICY SAFETY PASS: MEDICAID CORE EXCLUDED; NO CHIP ADDITIVE PROGRAM MAPPINGS';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218E COMPLETE - READ ONLY'
