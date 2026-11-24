
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-218F - EFFECTIVE MEDICAID/CHIP OVERLAP AUDIT'
\echo 'FY2018-FY2024 / READ ONLY / NO LEDGER WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '240s';

\echo ''
\echo '1. TRANSACTION-LEVEL EFFECTIVE CLASSIFICATIONS'

WITH transactions AS (
    SELECT
        t.assistance_transaction_id,
        t.action_date_fiscal_year AS fiscal_year,
        t.cfda_number,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.cfda_number IN ('93.778','93.767')
      AND t.action_date_fiscal_year BETWEEN 2018 AND 2024
),
classified AS (
    SELECT
        t.*,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system='USASPENDING_ASSISTANCE'
              AND m.source_program_code=t.cfda_number
              AND t.fiscal_year BETWEEN
                  m.valid_from_fiscal_year
                  AND m.valid_through_fiscal_year
        ) AS program_matches,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system='USASPENDING_ASSISTANCE'
              AND a.source_program_code=t.cfda_number
              AND t.fiscal_year BETWEEN
                  a.valid_from_fiscal_year
                  AND a.valid_through_fiscal_year
              AND a.source_award_identifier IN (
                  t.award_id_fain,t.award_id_uri
              )
        ) AS award_matches,
        (
            SELECT STRING_AGG(
                DISTINCT m.resolved_accounting_disposition,','
            )
            FROM reference.federal_inflow_program_policy_mapping m
            WHERE m.source_system='USASPENDING_ASSISTANCE'
              AND m.source_program_code=t.cfda_number
              AND t.fiscal_year BETWEEN
                  m.valid_from_fiscal_year
                  AND m.valid_through_fiscal_year
        ) AS program_disposition,
        (
            SELECT STRING_AGG(
                DISTINCT a.accounting_disposition,','
            )
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system='USASPENDING_ASSISTANCE'
              AND a.source_program_code=t.cfda_number
              AND t.fiscal_year BETWEEN
                  a.valid_from_fiscal_year
                  AND a.valid_through_fiscal_year
              AND a.source_award_identifier IN (
                  t.award_id_fain,t.award_id_uri
              )
        ) AS award_disposition
    FROM transactions t
),
resolved AS (
    SELECT *,
        CASE
            WHEN program_matches > 1 OR award_matches > 1
                THEN 'AMBIGUOUS'
            WHEN program_matches = 1 AND award_matches = 1
                THEN 'DUAL_POLICY_REVIEW'
            WHEN program_matches = 1
                THEN program_disposition
            WHEN award_matches = 1
                THEN award_disposition
            ELSE 'UNMAPPED_WITHHOLD'
        END AS effective_disposition
    FROM classified
)
SELECT
    fiscal_year,
    cfda_number,
    effective_disposition,
    COUNT(*) AS transaction_count,
    SUM(federal_action_obligation) AS net_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions
FROM resolved
GROUP BY fiscal_year,cfda_number,effective_disposition
ORDER BY fiscal_year,cfda_number,effective_disposition;

\echo ''
\echo '2. CHIP AWARDS REQUIRING ATTENTION'

WITH transactions AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        t.assistance_transaction_id,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
    FROM analysis.v_certified_assistance_ledger t
    WHERE t.cfda_number='93.767'
      AND t.action_date_fiscal_year BETWEEN 2018 AND 2024
),
matched AS (
    SELECT
        t.*,
        COUNT(a.federal_inflow_award_classification_id)
            AS classification_matches,
        STRING_AGG(
            DISTINCT a.accounting_disposition,','
        ) AS dispositions
    FROM transactions t
    LEFT JOIN reference.federal_inflow_award_classification a
      ON a.source_system='USASPENDING_ASSISTANCE'
     AND a.source_program_code='93.767'
     AND t.fiscal_year BETWEEN
         a.valid_from_fiscal_year
         AND a.valid_through_fiscal_year
     AND a.source_award_identifier IN (
         t.award_id_fain,t.award_id_uri
     )
    GROUP BY
        t.fiscal_year,
        t.assistance_transaction_id,
        t.award_id_fain,
        t.award_id_uri,
        t.federal_action_obligation
)
SELECT
    fiscal_year,
    award_id_fain,
    award_id_uri,
    COUNT(*) AS transactions,
    SUM(federal_action_obligation) AS net_obligations,
    MAX(classification_matches) AS max_matches,
    STRING_AGG(DISTINCT dispositions,'; ') AS dispositions
FROM matched
WHERE classification_matches <> 1
   OR dispositions NOT IN (
       'EXCLUDE_DUPLICATE','WITHHOLD_UNRESOLVED'
   )
GROUP BY fiscal_year,award_id_fain,award_id_uri
ORDER BY fiscal_year,award_id_fain,award_id_uri;

\echo ''
\echo '3. FAIL-CLOSED ADDITIVE/AMBIGUITY SAFETY GATE'

DO $gate$
DECLARE
    v_unsafe bigint;
BEGIN
    WITH transactions AS (
        SELECT
            t.assistance_transaction_id,
            t.action_date_fiscal_year AS fiscal_year,
            t.cfda_number,
            t.award_id_fain,
            t.award_id_uri
        FROM analysis.v_certified_assistance_ledger t
        WHERE t.cfda_number IN ('93.778','93.767')
          AND t.action_date_fiscal_year BETWEEN 2018 AND 2024
    ),
    checks AS (
        SELECT
            t.*,
            (
                SELECT COUNT(*)
                FROM reference.federal_inflow_program_policy_mapping m
                WHERE m.source_system='USASPENDING_ASSISTANCE'
                  AND m.source_program_code=t.cfda_number
                  AND t.fiscal_year BETWEEN
                      m.valid_from_fiscal_year
                      AND m.valid_through_fiscal_year
                  AND m.resolved_accounting_disposition=
                      'EXCLUDE_DUPLICATE'
            ) AS safe_program_matches,
            (
                SELECT COUNT(*)
                FROM reference.federal_inflow_program_policy_mapping m
                WHERE m.source_system='USASPENDING_ASSISTANCE'
                  AND m.source_program_code=t.cfda_number
                  AND t.fiscal_year BETWEEN
                      m.valid_from_fiscal_year
                      AND m.valid_through_fiscal_year
            ) AS all_program_matches,
            (
                SELECT COUNT(*)
                FROM reference.federal_inflow_award_classification a
                WHERE a.source_system='USASPENDING_ASSISTANCE'
                  AND a.source_program_code=t.cfda_number
                  AND t.fiscal_year BETWEEN
                      a.valid_from_fiscal_year
                      AND a.valid_through_fiscal_year
                  AND a.source_award_identifier IN (
                      t.award_id_fain,t.award_id_uri
                  )
                  AND a.accounting_disposition IN (
                      'EXCLUDE_DUPLICATE','WITHHOLD_UNRESOLVED'
                  )
            ) AS safe_award_matches,
            (
                SELECT COUNT(*)
                FROM reference.federal_inflow_award_classification a
                WHERE a.source_system='USASPENDING_ASSISTANCE'
                  AND a.source_program_code=t.cfda_number
                  AND t.fiscal_year BETWEEN
                      a.valid_from_fiscal_year
                      AND a.valid_through_fiscal_year
                  AND a.source_award_identifier IN (
                      t.award_id_fain,t.award_id_uri
                  )
            ) AS all_award_matches
        FROM transactions t
    )
    SELECT COUNT(*) INTO v_unsafe
    FROM checks
    WHERE
        (
            cfda_number='93.778'
            AND (
                all_program_matches <> 1
                OR safe_program_matches <> 1
                OR all_award_matches <> 0
            )
        )
        OR
        (
            cfda_number='93.767'
            AND (
                all_program_matches <> 0
                OR all_award_matches <> 1
                OR safe_award_matches <> 1
            )
        );

    IF v_unsafe <> 0 THEN
        RAISE EXCEPTION
            'ETL-218F BLOCK: % transactions lack unique safe classification',
            v_unsafe;
    END IF;

    RAISE NOTICE
        'ETL-218F PASS: ALL CORE TRANSACTIONS UNIQUELY EXCLUDED OR WITHHELD';
END
$gate$;

ROLLBACK;

\echo ''
\echo 'ETL-218F COMPLETE - READ ONLY'
