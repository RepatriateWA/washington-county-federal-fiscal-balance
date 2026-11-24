
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-215E - UNMAPPED ASSISTANCE PRIOR-WORK CROSSWALK'
\echo 'FY2018-FY2024 / READ ONLY / NO POLICY CHANGES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. TOP 40 PROGRAMS: PROGRAM-YEAR CROSSWALK'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        cfda_title AS program_title,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
        OR
        (reference_state_abbreviation = 'WA'
         AND action_date_fiscal_year BETWEEN 2020 AND 2024)
),
unmapped AS MATERIALIZED (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (a.valid_from_fiscal_year IS NULL
               OR a.valid_from_fiscal_year <= s.fiscal_year)
          AND (a.valid_through_fiscal_year IS NULL
               OR a.valid_through_fiscal_year >= s.fiscal_year)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (p.valid_from_fiscal_year IS NULL
               OR p.valid_from_fiscal_year <= s.fiscal_year)
          AND (p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= s.fiscal_year)
    )
),
ranked AS (
    SELECT
        program_code,
        SUM(ABS(obligation)) AS absolute_activity
    FROM unmapped
    GROUP BY program_code
    ORDER BY absolute_activity DESC, program_code
    LIMIT 40
),
program_year AS (
    SELECT
        u.fiscal_year,
        u.program_code,
        MAX(u.program_title) AS program_title,
        COUNT(*) AS transactions,
        SUM(u.obligation) AS net_obligations,
        SUM(ABS(u.obligation)) AS absolute_activity
    FROM unmapped u
    JOIN ranked r USING (program_code)
    GROUP BY u.fiscal_year, u.program_code
),
classified AS (
    SELECT
        py.*,
        c.classification_count,
        c.inflow_family,
        c.inflow_subfamily,
        c.overlap_risk,
        c.methodology_versions,
        sp.source_policy_count,
        sp.source_policy_versions,
        sp.preferred_sources,
        sp.ledger_treatments
    FROM program_year py
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS classification_count,
            STRING_AGG(
                DISTINCT x.inflow_family, '; '
            ) AS inflow_family,
            STRING_AGG(
                DISTINCT x.inflow_subfamily, '; '
            ) AS inflow_subfamily,
            STRING_AGG(
                DISTINCT x.overlap_risk, '; '
            ) AS overlap_risk,
            STRING_AGG(
                DISTINCT x.methodology_version, '; '
            ) AS methodology_versions
        FROM reference.federal_inflow_program_classification x
        WHERE x.source_system = 'USASPENDING_ASSISTANCE'
          AND x.source_program_code = py.program_code
          AND (x.valid_from_fiscal_year IS NULL
               OR x.valid_from_fiscal_year <= py.fiscal_year)
          AND (x.valid_through_fiscal_year IS NULL
               OR x.valid_through_fiscal_year >= py.fiscal_year)
    ) c ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS source_policy_count,
            STRING_AGG(
                DISTINCT sp.methodology_version, '; '
            ) AS source_policy_versions,
            STRING_AGG(
                DISTINCT sp.preferred_source, '; '
            ) AS preferred_sources,
            STRING_AGG(
                DISTINCT sp.ledger_treatment, '; '
            ) AS ledger_treatments
        FROM reference.federal_inflow_source_policy sp
        WHERE c.classification_count = 1
          AND sp.inflow_family = c.inflow_family
          AND sp.inflow_subfamily
              IS NOT DISTINCT FROM c.inflow_subfamily
          AND (sp.valid_from_fiscal_year IS NULL
               OR sp.valid_from_fiscal_year <= py.fiscal_year)
          AND (sp.valid_through_fiscal_year IS NULL
               OR sp.valid_through_fiscal_year >= py.fiscal_year)
    ) sp ON TRUE
)
SELECT
    fiscal_year,
    program_code,
    program_title,
    transactions,
    ROUND(net_obligations, 2) AS net_obligations,
    ROUND(absolute_activity, 2) AS absolute_activity,
    classification_count,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    methodology_versions,
    source_policy_count,
    preferred_sources,
    ledger_treatments,
    source_policy_versions,
    CASE
        WHEN classification_count > 1
            THEN 'REVIEW_CLASSIFICATION_MULTIPLICITY'
        WHEN classification_count = 1
         AND source_policy_count > 0
            THEN 'CLASSIFIED_WITH_FAMILY_POLICY'
        WHEN classification_count = 1
            THEN 'CLASSIFIED_NO_FAMILY_POLICY'
        ELSE 'NO_APPLICABLE_CLASSIFICATION'
    END AS prior_work_evidence
FROM classified
ORDER BY
    absolute_activity DESC,
    program_code,
    fiscal_year;

\echo ''
\echo '2. CHIP AND MEDICARE: UNMAPPED TRANSACTION PROFILE'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier,
        funding_agency_name,
        recipient_name
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (
            (load_batch_id = 20
             AND action_date_fiscal_year = 2018)
            OR
            (load_batch_id = 21
             AND action_date_fiscal_year = 2019)
            OR
            (reference_state_abbreviation = 'WA'
             AND action_date_fiscal_year BETWEEN 2020 AND 2024)
        )
        AND TRIM(cfda_number) IN ('93.767', '93.770')
),
unmapped AS (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (a.valid_from_fiscal_year IS NULL
               OR a.valid_from_fiscal_year <= s.fiscal_year)
          AND (a.valid_through_fiscal_year IS NULL
               OR a.valid_through_fiscal_year >= s.fiscal_year)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (p.valid_from_fiscal_year IS NULL
               OR p.valid_from_fiscal_year <= s.fiscal_year)
          AND (p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= s.fiscal_year)
    )
)
SELECT
    fiscal_year,
    program_code,
    funding_agency_name,
    recipient_name,
    COUNT(*) AS transactions,
    ROUND(SUM(obligation)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(obligation))::numeric, 2)
        AS absolute_activity
FROM unmapped
GROUP BY
    fiscal_year,
    program_code,
    funding_agency_name,
    recipient_name
ORDER BY
    program_code,
    fiscal_year,
    absolute_activity DESC;

\echo ''
\echo '3. SEVEN-YEAR UNMAPPED CONTROL ASSERTION'

WITH source_rows AS MATERIALIZED (
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year AS fiscal_year,
        TRIM(cfda_number) AS program_code,
        federal_action_obligation AS obligation,
        COALESCE(
            NULLIF(TRIM(award_id_fain), ''),
            NULLIF(TRIM(award_id_uri), '')
        ) AS award_identifier
    FROM analysis.v_certified_assistance_ledger
    WHERE
        (load_batch_id = 20
         AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21
         AND action_date_fiscal_year = 2019)
        OR
        (reference_state_abbreviation = 'WA'
         AND action_date_fiscal_year BETWEEN 2020 AND 2024)
),
unmapped AS (
    SELECT s.*
    FROM source_rows s
    WHERE NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_award_classification a
        WHERE a.source_system = 'USASPENDING_ASSISTANCE'
          AND a.source_program_code = s.program_code
          AND a.source_award_identifier = s.award_identifier
          AND (a.valid_from_fiscal_year IS NULL
               OR a.valid_from_fiscal_year <= s.fiscal_year)
          AND (a.valid_through_fiscal_year IS NULL
               OR a.valid_through_fiscal_year >= s.fiscal_year)
    )
    AND NOT EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping p
        WHERE p.source_system = 'USASPENDING_ASSISTANCE'
          AND p.source_program_code = s.program_code
          AND (p.valid_from_fiscal_year IS NULL
               OR p.valid_from_fiscal_year <= s.fiscal_year)
          AND (p.valid_through_fiscal_year IS NULL
               OR p.valid_through_fiscal_year >= s.fiscal_year)
    )
)
SELECT
    COUNT(*) AS unmapped_transactions,
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transactions,
    ROUND(SUM(obligation)::numeric, 2)
        AS unmapped_net_obligations,
    CASE
        WHEN COUNT(*) = 939968
         AND COUNT(DISTINCT assistance_transaction_id) = 939968
         AND ROUND(SUM(obligation)::numeric, 2)
             = 48545579756.65
            THEN 'PASS'
        ELSE 'FAIL'
    END AS control_status
FROM unmapped;

ROLLBACK;

\echo ''
\echo 'ETL-215E COMPLETE - READ ONLY'
