
\pset pager off
\set ON_ERROR_STOP on

\echo '============================================================'
\echo 'ETL-209L - HISTORICAL MEDICAID OVERLAP PREFLIGHT'
\echo 'FY2018-FY2019 / AL 93.778 / READ ONLY'
\echo '============================================================'

BEGIN READ ONLY;

\echo ''
\echo '1. CERTIFIED HISTORICAL USAspending MEDICAID OBLIGATIONS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    cfda_number AS program_code,
    MIN(cfda_title) AS program_title,
    COUNT(*) AS transactions,
    COUNT(DISTINCT award_id_fain) AS distinct_fains,
    COUNT(DISTINCT recipient_name) AS distinct_recipients,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations,
    ROUND(SUM(ABS(federal_action_obligation))::numeric, 2)
        AS gross_absolute_obligations,
    COUNT(*) FILTER (
        WHERE federal_action_obligation < 0
    ) AS negative_transactions
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
  AND BTRIM(cfda_number) = '93.778'
GROUP BY action_date_fiscal_year, cfda_number
ORDER BY fiscal_year;

\echo ''
\echo '2. AUTHORITATIVE WASHINGTON CMS MEDICAID CONTROLS'

SELECT
    m.fiscal_year,
    m.control_total_label,
    m.expenditure_time_basis,
    ROUND(m.total_computable::numeric, 2)
        AS total_computable,
    ROUND(m.federal_share::numeric, 2)
        AS federal_share,
    ROUND(m.federal_share_medicaid::numeric, 2)
        AS federal_share_medicaid,
    ROUND(m.federal_share_arra::numeric, 2)
        AS federal_share_arra,
    ROUND(m.federal_share_covid::numeric, 2)
        AS federal_share_covid,
    ROUND(m.state_share::numeric, 2)
        AS state_share,
    m.source_file,
    m.source_worksheet,
    m.source_row_number
FROM cms.medicaid_state_control_total m
JOIN reference.state_registry s
  ON s.state_id = m.state_id
WHERE s.state_abbreviation = 'WA'
  AND m.fiscal_year BETWEEN 2018 AND 2019
ORDER BY m.fiscal_year;

\echo ''
\echo '3. HISTORICAL CMS CONTROL VS USAspending OBLIGATIONS'

WITH usa AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS obligations
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) = '93.778'
    GROUP BY action_date_fiscal_year
),
cms_control AS (
    SELECT
        m.fiscal_year,
        COUNT(*) AS control_rows,
        SUM(m.federal_share) AS federal_share
    FROM cms.medicaid_state_control_total m
    JOIN reference.state_registry s
      ON s.state_id = m.state_id
    WHERE s.state_abbreviation = 'WA'
      AND m.fiscal_year BETWEEN 2018 AND 2019
    GROUP BY m.fiscal_year
)
SELECT
    y.fiscal_year,
    COALESCE(u.transactions, 0) AS usa_transactions,
    ROUND(u.obligations::numeric, 2)
        AS usa_obligations,
    COALESCE(c.control_rows, 0) AS cms_control_rows,
    ROUND(c.federal_share::numeric, 2)
        AS cms_federal_share,
    ROUND(
        (u.obligations - c.federal_share)::numeric,
        2
    ) AS obligations_minus_cms_control,
    CASE
        WHEN c.control_rows = 0
            THEN 'CMS CONTROL MISSING'
        WHEN c.control_rows <> 1
            THEN 'CMS CONTROL MULTIPLE ROWS'
        ELSE 'CONTROL PRESENT - SCOPE REVIEW REQUIRED'
    END AS preflight_status
FROM generate_series(2018, 2019) AS y(fiscal_year)
LEFT JOIN usa u
  ON u.fiscal_year = y.fiscal_year
LEFT JOIN cms_control c
  ON c.fiscal_year = y.fiscal_year
ORDER BY y.fiscal_year;

\echo ''
\echo '4. HISTORICAL MEDICAID AWARDS AND RECIPIENTS'

SELECT
    action_date_fiscal_year AS fiscal_year,
    award_id_fain,
    recipient_name,
    funding_agency_name,
    MIN(canonical_award_description)
        AS award_description,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
       (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
  AND BTRIM(cfda_number) = '93.778'
GROUP BY
    action_date_fiscal_year,
    award_id_fain,
    recipient_name,
    funding_agency_name
ORDER BY fiscal_year, ABS(SUM(federal_action_obligation)) DESC;

\echo ''
\echo '5. EXISTING MEDICAID SOURCE POLICIES'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
FROM reference.federal_inflow_source_policy
WHERE UPPER(COALESCE(inflow_family, '')) LIKE '%MEDICAID%'
   OR UPPER(COALESCE(preferred_source, '')) LIKE '%MEDICAID%'
ORDER BY valid_from_fiscal_year, methodology_version;

\echo ''
\echo '6. EXISTING AL 93.778 PROGRAM POLICY'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.federal_inflow_source_policy_id,
    m.mapping_basis,
    m.methodology_version,
    m.valid_from_fiscal_year,
    m.valid_through_fiscal_year
FROM reference.federal_inflow_program_policy_mapping m
WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '93.778'
ORDER BY m.valid_from_fiscal_year;

\echo ''
\echo '7. MEDICAID SERVICE-DETAIL COVERAGE'

SELECT
    mse.fiscal_year,
    COUNT(*) AS service_rows,
    COUNT(DISTINCT mse.medicaid_service_category_id)
        AS service_categories,
    ROUND(SUM(mse.federal_share)::numeric, 2)
        AS all_service_federal_share,
    ROUND(
        SUM(mse.federal_share) FILTER (
            WHERE mse.is_additive_to_control_total
        )::numeric, 2
    ) AS additive_service_federal_share
FROM cms.medicaid_service_expenditures mse
JOIN reference.state_registry s
  ON s.state_id = mse.state_id
WHERE s.state_abbreviation = 'WA'
  AND mse.fiscal_year BETWEEN 2018 AND 2019
GROUP BY mse.fiscal_year
ORDER BY mse.fiscal_year;

\echo ''
\echo '8. HARD SOURCE CONTROLS'

DO $$
DECLARE
    v_transactions bigint;
    v_obligations numeric;
    v_years bigint;
BEGIN
    SELECT
        COUNT(*),
        ROUND(SUM(federal_action_obligation)::numeric, 2),
        COUNT(DISTINCT action_date_fiscal_year)
    INTO
        v_transactions,
        v_obligations,
        v_years
    FROM analysis.v_certified_assistance_ledger
    WHERE (
           (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
      AND BTRIM(cfda_number) = '93.778';

    IF v_transactions <> 53
       OR v_obligations <> 16453706376.00::numeric
       OR v_years <> 2 THEN
        RAISE EXCEPTION
            'ETL-209L source control mismatch: rows %, dollars %, years %',
            v_transactions, v_obligations, v_years;
    END IF;

    RAISE NOTICE
        'ETL-209L SOURCE PASS: 53 transactions / $16,453,706,376 / 2 years';

    RAISE NOTICE
        'ETL-209L PREFLIGHT ONLY: no historical Medicaid accounting decision made';
END
$$;

ROLLBACK;

\echo 'ETL-209L COMPLETE - NO DATABASE WRITES'
