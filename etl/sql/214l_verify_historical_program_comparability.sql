
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-214L - HISTORICAL PROGRAM COMPARABILITY'
\echo 'FY2018-FY2024 / SIX ADDITIVE POLICY CANDIDATES'
\echo 'READ ONLY - NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. PROGRAM-YEAR COMPARABILITY PROFILE'

WITH target(program_code, program_name) AS (
    VALUES
        ('10.555', 'SCHOOL LUNCH'),
        ('84.010', 'TITLE I'),
        ('84.027', 'SPECIAL EDUCATION'),
        ('84.063', 'PELL GRANTS'),
        ('93.558', 'TANF'),
        ('93.600', 'HEAD START')
),
source_rows AS MATERIALIZED (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        l.cfda_title AS program_title,
        l.federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.assistance_award_unique_key,
        l.reference_county_id,
        l.funding_families,
        l.is_covid,
        l.is_iija,
        l.is_extraordinary
    FROM analysis.v_certified_assistance_ledger l
    JOIN target t
      ON TRIM(l.cfda_number) = t.program_code
    WHERE
        (
            l.action_date_fiscal_year = 2018
            AND l.load_batch_id = 20
        )
        OR (
            l.action_date_fiscal_year = 2019
            AND l.load_batch_id = 21
        )
        OR (
            l.action_date_fiscal_year BETWEEN 2020 AND 2024
            AND l.reference_state_abbreviation = 'WA'
        )
),
profile AS (
    SELECT
        program_code,
        fiscal_year,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT assistance_transaction_id)
            AS distinct_transaction_count,
        COUNT(DISTINCT award_identifier)
            AS distinct_award_identifiers,
        COUNT(DISTINCT assistance_award_unique_key)
            AS distinct_award_unique_keys,
        COUNT(*) FILTER (
            WHERE award_identifier IS NULL
        ) AS missing_award_identifiers,
        COUNT(*) FILTER (
            WHERE assistance_award_unique_key IS NULL
        ) AS missing_award_unique_keys,
        COUNT(DISTINCT program_title)
            AS distinct_program_titles,
        COUNT(*) FILTER (
            WHERE reference_county_id IS NOT NULL
        ) AS county_linked_rows,
        COUNT(*) FILTER (
            WHERE obligation < 0
        ) AS negative_obligation_rows,
        COUNT(*) FILTER (
            WHERE obligation IS NULL
        ) AS null_obligation_rows,
        COUNT(*) FILTER (
            WHERE is_covid IS TRUE
        ) AS covid_rows,
        COUNT(*) FILTER (
            WHERE is_iija IS TRUE
        ) AS iija_rows,
        COUNT(*) FILTER (
            WHERE is_extraordinary IS TRUE
        ) AS extraordinary_rows,
        ROUND(COALESCE(SUM(obligation), 0), 2)
            AS net_obligations,
        ROUND(COALESCE(SUM(obligation) FILTER (
            WHERE obligation > 0
        ), 0), 2) AS positive_obligations,
        ROUND(COALESCE(SUM(obligation) FILTER (
            WHERE obligation < 0
        ), 0), 2) AS negative_obligations
    FROM source_rows
    GROUP BY program_code, fiscal_year
)
SELECT
    p.*,
    CASE
        WHEN fiscal_year <= 2019
            THEN 'HISTORICAL_CANDIDATE'
        ELSE 'EXISTING_POLICY_PERIOD'
    END AS accounting_period
FROM profile p
ORDER BY program_code, fiscal_year;

\echo ''
\echo '2. SOURCE PROGRAM TITLES AND FUNDING FAMILIES'

WITH target(program_code) AS (
    VALUES
        ('10.555'),
        ('84.010'),
        ('84.027'),
        ('84.063'),
        ('93.558'),
        ('93.600')
),
source_rows AS MATERIALIZED (
    SELECT
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        COALESCE(
            NULLIF(TRIM(l.cfda_title), ''),
            '[MISSING TITLE]'
        ) AS program_title,
        COALESCE(
            ARRAY_TO_STRING(l.funding_families, ', '),
            '[MISSING FUNDING FAMILY]'
        ) AS funding_family_signature,
        l.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger l
    JOIN target t
      ON TRIM(l.cfda_number) = t.program_code
    WHERE
        (
            l.action_date_fiscal_year = 2018
            AND l.load_batch_id = 20
        )
        OR (
            l.action_date_fiscal_year = 2019
            AND l.load_batch_id = 21
        )
        OR (
            l.action_date_fiscal_year BETWEEN 2020 AND 2024
            AND l.reference_state_abbreviation = 'WA'
        )
)
SELECT
    program_code,
    fiscal_year,
    program_title,
    funding_family_signature,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation), 2) AS net_obligations
FROM source_rows
GROUP BY
    program_code,
    fiscal_year,
    program_title,
    funding_family_signature
ORDER BY
    program_code,
    fiscal_year,
    ABS(SUM(obligation)) DESC;

\echo ''
\echo '3. HISTORICAL POLICY COLLISION AND COVERAGE CHECK'

WITH target(program_code) AS (
    VALUES
        ('10.555'),
        ('84.010'),
        ('84.027'),
        ('84.063'),
        ('93.558'),
        ('93.600')
),
historical AS MATERIALIZED (
    SELECT
        l.assistance_transaction_id,
        l.action_date_fiscal_year AS fiscal_year,
        TRIM(l.cfda_number) AS program_code,
        COALESCE(
            NULLIF(TRIM(l.award_id_fain), ''),
            NULLIF(TRIM(l.award_id_uri), '')
        ) AS award_identifier,
        l.federal_action_obligation AS obligation
    FROM analysis.v_certified_assistance_ledger l
    JOIN target t
      ON TRIM(l.cfda_number) = t.program_code
    WHERE
        (l.action_date_fiscal_year = 2018
         AND l.load_batch_id = 20)
        OR
        (l.action_date_fiscal_year = 2019
         AND l.load_batch_id = 21)
),
checks AS (
    SELECT
        h.*,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping p
            WHERE p.source_system = 'USASPENDING_ASSISTANCE'
              AND p.source_program_code = h.program_code
              AND (
                  p.valid_from_fiscal_year IS NULL
                  OR p.valid_from_fiscal_year <= h.fiscal_year
              )
              AND (
                  p.valid_through_fiscal_year IS NULL
                  OR p.valid_through_fiscal_year >= h.fiscal_year
              )
        ) AS program_policy_matches,
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND a.source_program_code = h.program_code
              AND a.source_award_identifier = h.award_identifier
              AND (
                  a.valid_from_fiscal_year IS NULL
                  OR a.valid_from_fiscal_year <= h.fiscal_year
              )
              AND (
                  a.valid_through_fiscal_year IS NULL
                  OR a.valid_through_fiscal_year >= h.fiscal_year
              )
        ) AS award_policy_matches
    FROM historical h
)
SELECT
    program_code,
    fiscal_year,
    COUNT(*) AS historical_transactions,
    ROUND(SUM(obligation), 2) AS historical_net,
    COUNT(*) FILTER (
        WHERE program_policy_matches = 0
          AND award_policy_matches = 0
    ) AS currently_unclassified,
    COUNT(*) FILTER (
        WHERE program_policy_matches > 0
    ) AS program_policy_covered,
    COUNT(*) FILTER (
        WHERE award_policy_matches > 0
    ) AS award_policy_covered,
    COUNT(*) FILTER (
        WHERE program_policy_matches > 1
           OR award_policy_matches > 1
    ) AS multiple_policy_matches,
    COUNT(*) FILTER (
        WHERE program_policy_matches > 0
          AND award_policy_matches > 0
    ) AS simultaneous_policy_matches
FROM checks
GROUP BY program_code, fiscal_year
ORDER BY program_code, fiscal_year;

\echo ''
\echo '4. EXISTING POLICY METHODOLOGY REFERENCES'

SELECT
    p.source_program_code,
    p.resolved_accounting_disposition,
    p.valid_from_fiscal_year,
    p.valid_through_fiscal_year,
    p.methodology_version,
    p.mapping_basis,
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.ledger_treatment
FROM reference.federal_inflow_program_policy_mapping p
LEFT JOIN reference.federal_inflow_source_policy s
  ON s.federal_inflow_source_policy_id =
     p.federal_inflow_source_policy_id
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.source_program_code IN (
      '10.555',
      '84.010',
      '84.027',
      '84.063',
      '93.558',
      '93.600'
  )
ORDER BY
    p.source_program_code,
    p.valid_from_fiscal_year;

ROLLBACK;

\echo 'ETL-214L COMPLETE - NO DATABASE WRITES'
