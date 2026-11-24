\set ON_ERROR_STOP on

BEGIN;

WITH observations AS (
    SELECT
        BTRIM(raw_record ->> 'cfda_number') AS cfda_number,
        BTRIM(raw_record ->> 'cfda_title') AS observed_title,
        COUNT(*) AS occurrence_count,
        MAX(load_batch_id) AS latest_batch_id,
        MAX(source_row_number) AS latest_source_row_number
    FROM assistance.raw_award_transaction
    WHERE load_batch_id IN (20, 21)
      AND NULLIF(BTRIM(raw_record ->> 'cfda_number'), '') IS NOT NULL
      AND NULLIF(BTRIM(raw_record ->> 'cfda_title'), '') IS NOT NULL
    GROUP BY
        BTRIM(raw_record ->> 'cfda_number'),
        BTRIM(raw_record ->> 'cfda_title')
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY cfda_number
            ORDER BY
                occurrence_count DESC,
                latest_batch_id DESC,
                latest_source_row_number DESC,
                UPPER(REGEXP_REPLACE(observed_title, '\s+', ' ', 'g')),
                observed_title
        ) AS selection_rank
    FROM observations
),
inserted AS (
    INSERT INTO assistance.assistance_listing (
        cfda_number,
        cfda_title,
        cfda_title_normalized
    )
    SELECT
        cfda_number,
        observed_title,
        UPPER(REGEXP_REPLACE(BTRIM(observed_title), '\s+', ' ', 'g'))
    FROM ranked
    WHERE selection_rank = 1
    ON CONFLICT (cfda_number) DO NOTHING
    RETURNING cfda_number
)
SELECT
    COUNT(*) AS listings_inserted_in_dry_run
FROM inserted;

SELECT
    raw.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(listing.assistance_listing_id) AS resolved_rows,
    COUNT(*) - COUNT(listing.assistance_listing_id)
        AS unresolved_rows
FROM assistance.raw_award_transaction AS raw
LEFT JOIN assistance.assistance_listing AS listing
    ON listing.cfda_number =
       BTRIM(raw.raw_record ->> 'cfda_number')
WHERE raw.load_batch_id IN (20, 21)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

ROLLBACK;
