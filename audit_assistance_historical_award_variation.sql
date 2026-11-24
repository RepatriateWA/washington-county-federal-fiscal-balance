BEGIN;
SET TRANSACTION READ ONLY;

WITH observations AS (
    SELECT
        raw.load_batch_id,
        raw.assistance_award_unique_key,
        NULLIF(BTRIM(raw.raw_record ->> 'cfda_number'), '')
            AS listing_code,
        NULLIF(BTRIM(raw.raw_record ->> 'assistance_type_code'), '')
            AS type_code,
        NULLIF(BTRIM(raw.raw_record ->> 'award_id_uri'), '')
            AS uri
    FROM assistance.raw_award_transaction AS raw
    WHERE raw.load_batch_id IN (20, 21)
),
award_variation AS (
    SELECT
        load_batch_id,
        assistance_award_unique_key,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT listing_code) AS listing_count,
        COUNT(DISTINCT type_code) AS type_count,
        COUNT(DISTINCT uri) AS uri_count
    FROM observations
    GROUP BY load_batch_id, assistance_award_unique_key
),
classified AS (
    SELECT
        v.*,
        (a.assistance_award_id IS NOT NULL)
            AS exists_in_canonical
    FROM award_variation AS v
    LEFT JOIN assistance.award AS a
      ON a.assistance_award_unique_key =
         v.assistance_award_unique_key
)
SELECT
    load_batch_id,
    COUNT(*) AS total_awards,
    COUNT(*) FILTER (
        WHERE transaction_count > 1
    ) AS awards_with_multiple_transactions,
    COUNT(*) FILTER (
        WHERE listing_count > 1
    ) AS awards_with_multiple_listings,
    COUNT(*) FILTER (
        WHERE type_count > 1
    ) AS awards_with_multiple_types,
    COUNT(*) FILTER (
        WHERE uri_count > 1
    ) AS awards_with_multiple_uris,
    COUNT(*) FILTER (
        WHERE exists_in_canonical AND listing_count > 1
    ) AS existing_awards_multiple_listings,
    COUNT(*) FILTER (
        WHERE exists_in_canonical AND type_count > 1
    ) AS existing_awards_multiple_types,
    COUNT(*) FILTER (
        WHERE exists_in_canonical AND uri_count > 1
    ) AS existing_awards_multiple_uris
FROM classified
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;
