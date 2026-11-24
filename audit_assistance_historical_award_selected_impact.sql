BEGIN;
SET TRANSACTION READ ONLY;

WITH observations AS (
    SELECT
        raw.load_batch_id,
        raw.assistance_award_unique_key,
        raw.source_row_number,
        CASE
            WHEN LEFT(
                BTRIM(raw.raw_record ->> 'action_date'), 10
            ) ~ '^\d{4}-\d{2}-\d{2}$'
            THEN LEFT(
                BTRIM(raw.raw_record ->> 'action_date'), 10
            )::date
            ELSE NULL
        END AS action_date,
        listing.assistance_listing_id,
        assistance_type.assistance_type_id,
        NULLIF(BTRIM(raw.raw_record ->> 'award_id_fain'), '')
            AS source_fain,
        NULLIF(BTRIM(raw.raw_record ->> 'award_id_uri'), '')
            AS source_uri
    FROM assistance.raw_award_transaction AS raw
    JOIN assistance.assistance_listing AS listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    JOIN assistance.assistance_type AS assistance_type
      ON assistance_type.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    WHERE raw.load_batch_id IN (20, 21)
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY load_batch_id, assistance_award_unique_key
            ORDER BY
                action_date DESC NULLS LAST,
                source_row_number DESC
        ) AS selection_rank
    FROM observations
),
selected AS (
    SELECT *
    FROM ranked
    WHERE selection_rank = 1
),
compared AS (
    SELECT
        s.load_batch_id,
        s.assistance_award_unique_key,
        a.assistance_listing_id
            IS DISTINCT FROM s.assistance_listing_id
            AS listing_diff,
        a.assistance_type_id
            IS DISTINCT FROM s.assistance_type_id
            AS type_diff,
        NULLIF(BTRIM(a.award_id_fain), '')
            IS DISTINCT FROM s.source_fain
            AS fain_diff,
        NULLIF(BTRIM(a.award_id_uri), '')
            IS DISTINCT FROM s.source_uri
            AS uri_diff
    FROM selected AS s
    JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         s.assistance_award_unique_key
)
SELECT
    load_batch_id,
    COUNT(*) AS existing_awards_compared,
    COUNT(*) FILTER (WHERE listing_diff)
        AS selected_listing_differences,
    COUNT(*) FILTER (WHERE type_diff)
        AS selected_type_differences,
    COUNT(*) FILTER (WHERE fain_diff)
        AS selected_fain_differences,
    COUNT(*) FILTER (WHERE uri_diff)
        AS selected_uri_differences,
    COUNT(*) FILTER (
        WHERE listing_diff OR type_diff OR fain_diff OR uri_diff
    ) AS awards_with_selected_difference
FROM compared
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;
