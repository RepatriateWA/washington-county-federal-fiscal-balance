
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-223D - TOP FIVE HISTORICAL ASSISTANCE EVIDENCE'
\echo 'FY2018-FY2019 / READ ONLY / NO DATABASE WRITES'
\echo '============================================================'

BEGIN TRANSACTION READ ONLY;

\echo ''
\echo '1. ANNUAL SOURCE CONTROLS AND OBLIGATION SIGNS'

WITH target AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        BTRIM(cfda_number) AS program_code,
        cfda_title,
        recipient_name,
        funding_agency_name,
        award_id_fain,
        award_id_uri,
        federal_action_obligation AS amount,
        transaction_description
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN (
        '93.527','10.557','10.561','93.563','10.924'
    )
)
SELECT
    program_code,
    fiscal_year,
    COUNT(*) AS transactions,
    COUNT(DISTINCT COALESCE(
        NULLIF(BTRIM(award_id_fain), ''),
        NULLIF(BTRIM(award_id_uri), '')
    )) AS awards,
    COUNT(DISTINCT recipient_name) AS recipients,
    COUNT(*) FILTER (WHERE amount > 0) AS positive_tx,
    COUNT(*) FILTER (WHERE amount < 0) AS negative_tx,
    COUNT(*) FILTER (WHERE amount = 0) AS zero_tx,
    ROUND(SUM(amount)::numeric, 2) AS net_obligations,
    ROUND(SUM(ABS(amount))::numeric, 2) AS absolute_activity,
    ROUND(SUM(amount) FILTER (
        WHERE amount > 0
    )::numeric, 2) AS positive_obligations,
    ROUND(SUM(amount) FILTER (
        WHERE amount < 0
    )::numeric, 2) AS negative_adjustments
FROM target
GROUP BY program_code, fiscal_year
ORDER BY program_code, fiscal_year;

\echo ''
\echo '2. PROGRAM TITLES AND FUNDING AGENCIES'

SELECT
    BTRIM(cfda_number) AS program_code,
    cfda_title,
    funding_agency_name,
    COUNT(*) AS transactions,
    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligations
FROM analysis.v_certified_assistance_ledger
WHERE (
    (load_batch_id = 20 AND action_date_fiscal_year = 2018)
    OR
    (load_batch_id = 21 AND action_date_fiscal_year = 2019)
)
AND BTRIM(cfda_number) IN (
    '93.527','10.557','10.561','93.563','10.924'
)
GROUP BY BTRIM(cfda_number), cfda_title, funding_agency_name
ORDER BY program_code, ABS(SUM(federal_action_obligation)) DESC;

\echo ''
\echo '3. TOP RECIPIENTS BY ABSOLUTE OBLIGATION ACTIVITY'

WITH recipients AS (
    SELECT
        BTRIM(cfda_number) AS program_code,
        recipient_name,
        COUNT(*) AS transactions,
        COUNT(DISTINCT COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), '')
        )) AS awards,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(ABS(federal_action_obligation)) AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN (
        '93.527','10.557','10.561','93.563','10.924'
    )
    GROUP BY BTRIM(cfda_number), recipient_name
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY program_code
            ORDER BY absolute_activity DESC, recipient_name
        ) AS recipient_rank
    FROM recipients
)
SELECT
    program_code,
    recipient_rank,
    recipient_name,
    transactions,
    awards,
    ROUND(net_obligations::numeric, 2) AS net_obligations,
    ROUND(absolute_activity::numeric, 2) AS absolute_activity
FROM ranked
WHERE recipient_rank <= 5
ORDER BY program_code, recipient_rank;

\echo ''
\echo '4. LARGEST AWARDS BY ABSOLUTE OBLIGATION ACTIVITY'

WITH awards AS (
    SELECT
        BTRIM(cfda_number) AS program_code,
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), ''),
            '[MISSING]'
        ) AS award_identifier,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(ABS(federal_action_obligation)) AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN (
        '93.527','10.557','10.561','93.563','10.924'
    )
    GROUP BY
        BTRIM(cfda_number),
        COALESCE(
            NULLIF(BTRIM(award_id_fain), ''),
            NULLIF(BTRIM(award_id_uri), ''),
            '[MISSING]'
        )
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY program_code
            ORDER BY absolute_activity DESC, award_identifier
        ) AS award_rank
    FROM awards
)
SELECT
    program_code,
    award_rank,
    award_identifier,
    transactions,
    ROUND(net_obligations::numeric, 2) AS net_obligations,
    ROUND(absolute_activity::numeric, 2) AS absolute_activity
FROM ranked
WHERE award_rank <= 5
ORDER BY program_code, award_rank;

\echo ''
\echo '5. MOST MATERIAL TRANSACTION DESCRIPTIONS'

WITH descriptions AS (
    SELECT
        BTRIM(cfda_number) AS program_code,
        LEFT(
            COALESCE(NULLIF(BTRIM(transaction_description), ''),
                     '[NO DESCRIPTION]'),
            180
        ) AS description_excerpt,
        COUNT(*) AS transactions,
        SUM(federal_action_obligation) AS net_obligations,
        SUM(ABS(federal_action_obligation)) AS absolute_activity
    FROM analysis.v_certified_assistance_ledger
    WHERE (
        (load_batch_id = 20 AND action_date_fiscal_year = 2018)
        OR
        (load_batch_id = 21 AND action_date_fiscal_year = 2019)
    )
    AND BTRIM(cfda_number) IN (
        '93.527','10.557','10.561','93.563','10.924'
    )
    GROUP BY
        BTRIM(cfda_number),
        LEFT(
            COALESCE(NULLIF(BTRIM(transaction_description), ''),
                     '[NO DESCRIPTION]'),
            180
        )
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY program_code
            ORDER BY absolute_activity DESC, description_excerpt
        ) AS description_rank
    FROM descriptions
)
SELECT
    program_code,
    description_rank,
    description_excerpt,
    transactions,
    ROUND(net_obligations::numeric, 2) AS net_obligations,
    ROUND(absolute_activity::numeric, 2) AS absolute_activity
FROM ranked
WHERE description_rank <= 5
ORDER BY program_code, description_rank;

COMMIT;

\echo 'ETL-223D COMPLETE - NO DATABASE WRITES'
