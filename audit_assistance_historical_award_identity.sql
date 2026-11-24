BEGIN;
SET TRANSACTION READ ONLY;

WITH historical AS (
    SELECT
        raw.load_batch_id,
        raw.assistance_award_unique_key,
        raw.raw_record ->> 'award_id_fain' AS source_fain,
        raw.raw_record ->> 'award_id_uri' AS source_uri,
        listing.assistance_listing_id AS source_listing_id,
        assistance_type.assistance_type_id AS source_type_id
    FROM assistance.raw_award_transaction AS raw
    JOIN assistance.assistance_listing AS listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    JOIN assistance.assistance_type AS assistance_type
      ON assistance_type.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    WHERE raw.load_batch_id IN (20, 21)
),
compared AS (
    SELECT
        historical.load_batch_id,
        historical.assistance_award_unique_key,
        BOOL_OR(
            award.assistance_listing_id
                IS DISTINCT FROM historical.source_listing_id
        ) AS listing_diff,
        BOOL_OR(
            award.assistance_type_id
                IS DISTINCT FROM historical.source_type_id
        ) AS type_diff,
        BOOL_OR(
            NULLIF(BTRIM(award.award_id_fain), '')
                IS DISTINCT FROM NULLIF(BTRIM(historical.source_fain), '')
        ) AS fain_diff,
        BOOL_OR(
            NULLIF(BTRIM(award.award_id_uri), '')
                IS DISTINCT FROM NULLIF(BTRIM(historical.source_uri), '')
        ) AS uri_diff
    FROM historical
    JOIN assistance.award AS award
      ON award.assistance_award_unique_key =
         historical.assistance_award_unique_key
    GROUP BY
        historical.load_batch_id,
        historical.assistance_award_unique_key
)
SELECT
    load_batch_id,
    COUNT(*) AS existing_awards_compared,
    COUNT(*) FILTER (WHERE listing_diff) AS listing_differences,
    COUNT(*) FILTER (WHERE type_diff) AS type_differences,
    COUNT(*) FILTER (WHERE fain_diff) AS fain_differences,
    COUNT(*) FILTER (WHERE uri_diff) AS uri_differences,
    COUNT(*) FILTER (
        WHERE listing_diff OR type_diff OR fain_diff OR uri_diff
    ) AS awards_with_any_difference
FROM compared
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;
