
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223K - HISTORICAL PERFORMANCE GEOGRAPHY'
\echo 'READ ONLY - NO DATABASE WRITES'

BEGIN TRANSACTION READ ONLY;

WITH target AS (
    SELECT
        t.action_date_fiscal_year AS fiscal_year,
        BTRIM(al.cfda_number) AS program_code,
        t.federal_action_obligation AS amount,

        NULLIF(BTRIM(
            r.raw_record ->> 'recipient_state_code'
        ), '') AS recipient_state,

        NULLIF(BTRIM(
            r.raw_record ->>
            'prime_award_transaction_place_of_performance_state_fips_code'
        ), '') AS performance_state_fips,

        NULLIF(BTRIM(
            r.raw_record ->> 'primary_place_of_performance_state_name'
        ), '') AS performance_state_name

    FROM assistance.award_transaction t
    JOIN assistance.assistance_listing al
      ON al.assistance_listing_id = t.assistance_listing_id
    JOIN assistance.raw_award_transaction r
      ON r.load_batch_id = t.load_batch_id
     AND r.source_row_number = t.source_row_number

    WHERE (
        (t.load_batch_id = 20
         AND t.action_date_fiscal_year = 2018)
        OR
        (t.load_batch_id = 21
         AND t.action_date_fiscal_year = 2019)
    )
      AND BTRIM(al.cfda_number) IN (
          '93.527','10.557','10.561','93.563','10.924'
      )
),
classified AS (
    SELECT *,
        CASE
            WHEN performance_state_fips = '53'
                THEN 'WA_PERFORMANCE'
            WHEN performance_state_fips IS NULL
                THEN 'PERFORMANCE_FIPS_MISSING'
            ELSE 'OTHER_PERFORMANCE_FIPS'
        END AS performance_class,

        CASE
            WHEN recipient_state = 'WA'
             AND performance_state_fips = '53'
                THEN 'BOTH_WA'
            WHEN recipient_state = 'WA'
             AND performance_state_fips <> '53'
                THEN 'WA_RECIPIENT_OTHER_PERFORMANCE'
            WHEN recipient_state <> 'WA'
             AND performance_state_fips = '53'
                THEN 'OTHER_RECIPIENT_WA_PERFORMANCE'
            ELSE 'OTHER_OR_UNRESOLVED'
        END AS geography_comparison
    FROM target
)
SELECT
    program_code,
    fiscal_year,
    performance_class,
    geography_comparison,
    performance_state_name,
    COUNT(*) AS transactions,
    ROUND(SUM(COALESCE(amount, 0)), 2)
        AS net_obligations,
    ROUND(SUM(ABS(COALESCE(amount, 0))), 2)
        AS absolute_activity
FROM classified
GROUP BY
    program_code,
    fiscal_year,
    performance_class,
    geography_comparison,
    performance_state_name
ORDER BY
    program_code,
    fiscal_year,
    performance_class,
    geography_comparison,
    performance_state_name;

COMMIT;

\echo 'ETL-223K COMPLETE - NO DATABASE WRITES'
