\set ON_ERROR_STOP on

BEGIN;
SET TRANSACTION READ ONLY;

WITH missing_awards AS (
    SELECT DISTINCT
        raw.load_batch_id,
        raw.assistance_award_unique_key
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN assistance.award AS existing
      ON existing.assistance_award_unique_key =
         raw.assistance_award_unique_key
    WHERE raw.load_batch_id IN (20, 21)
      AND existing.assistance_award_id IS NULL
),
cross_year AS (
    SELECT
        assistance_award_unique_key,
        BOOL_OR(load_batch_id = 20) AS in_2018,
        BOOL_OR(load_batch_id = 21) AS in_2019
    FROM missing_awards
    GROUP BY assistance_award_unique_key
)
SELECT
    COUNT(*) AS distinct_missing_awards,
    COUNT(*) FILTER (
        WHERE in_2018 AND in_2019
    ) AS missing_awards_in_both_years,
    COUNT(*) FILTER (
        WHERE in_2018 AND NOT in_2019
    ) AS missing_awards_2018_only,
    COUNT(*) FILTER (
        WHERE in_2019 AND NOT in_2018
    ) AS missing_awards_2019_only
FROM cross_year;

ROLLBACK;
