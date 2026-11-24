BEGIN;
SET TRANSACTION READ ONLY;

WITH observations AS (
    SELECT
        raw.load_batch_id,
        BTRIM(raw.raw_record ->> 'cfda_number') AS cfda_number,
        BTRIM(raw.raw_record ->> 'cfda_title') AS observed_title,
        COUNT(*) AS occurrence_count,
        MAX(raw.source_row_number) AS last_source_row_number
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (20, 21)
      AND NULLIF(BTRIM(raw.raw_record ->> 'cfda_number'), '') IS NOT NULL
      AND NULLIF(BTRIM(raw.raw_record ->> 'cfda_title'), '') IS NOT NULL
    GROUP BY
        raw.load_batch_id,
        BTRIM(raw.raw_record ->> 'cfda_number'),
        BTRIM(raw.raw_record ->> 'cfda_title')
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY load_batch_id, cfda_number
            ORDER BY
                occurrence_count DESC,
                last_source_row_number DESC,
                UPPER(REGEXP_REPLACE(BTRIM(observed_title), '\s+', ' ', 'g')),
                observed_title
        ) AS selection_rank
    FROM observations
),
proposed AS (
    SELECT
        load_batch_id,
        cfda_number,
        observed_title AS proposed_title,
        UPPER(REGEXP_REPLACE(BTRIM(observed_title), '\s+', ' ', 'g'))
            AS proposed_normalized_title
    FROM ranked
    WHERE selection_rank = 1
),
classified AS (
    SELECT
        p.load_batch_id,
        p.cfda_number,
        CASE
            WHEN existing.assistance_listing_id IS NULL
                THEN 'INSERT'
            WHEN existing.cfda_title IS NOT DISTINCT FROM p.proposed_title
             AND existing.cfda_title_normalized
                 IS NOT DISTINCT FROM p.proposed_normalized_title
                THEN 'UNCHANGED'
            ELSE 'UPDATE'
        END AS proposed_action
    FROM proposed AS p
    LEFT JOIN assistance.assistance_listing AS existing
      ON existing.cfda_number = p.cfda_number
)
SELECT
    load_batch_id,
    proposed_action,
    COUNT(*) AS listing_count
FROM classified
GROUP BY load_batch_id, proposed_action
ORDER BY load_batch_id, proposed_action;

ROLLBACK;
