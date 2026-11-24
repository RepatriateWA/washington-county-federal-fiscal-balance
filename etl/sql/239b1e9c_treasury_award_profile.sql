\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

\echo 'ETL-239B1E9C - TREASURY AWARD IDENTITY PROFILE'
\echo 'READ ONLY - NO LEDGER AUTHORIZATION'

WITH awards AS (
    SELECT
        cfda_number,
        action_date_fiscal_year AS fiscal_year,
        assistance_award_unique_key,
        award_id_fain,
        award_id_uri,
        COUNT(*) AS transaction_count,
        ROUND(
            SUM(federal_action_obligation)::numeric, 2
        ) AS obligation_usd
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2018 AND 2024
      AND cfda_number IN (
          '21.019', '21.023', '21.027',
          '21.026', '21.029', '21.031', '21.032'
      )
    GROUP BY
        cfda_number,
        action_date_fiscal_year,
        assistance_award_unique_key,
        award_id_fain,
        award_id_uri
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY ABS(obligation_usd) DESC,
                     fiscal_year,
                     assistance_award_unique_key
        ) AS award_rank
    FROM awards
)
SELECT
    cfda_number,
    fiscal_year,
    transaction_count,
    obligation_usd,
    assistance_award_unique_key,
    award_id_fain,
    award_id_uri
FROM ranked
WHERE award_rank <= 10
ORDER BY cfda_number, award_rank;

ROLLBACK;