BEGIN;
SET TRANSACTION READ ONLY;

WITH historical AS (
    SELECT
        raw.load_batch_id,
        raw.assistance_award_unique_key,
        NULLIF(BTRIM(raw.raw_record ->> 'award_id_fain'), '')
            AS source_fain,
        NULLIF(BTRIM(raw.raw_record ->> 'award_id_uri'), '')
            AS source_uri,
        listing.assistance_listing_id,
        assistance_type.assistance_type_id
    FROM assistance.raw_award_transaction AS raw
    LEFT JOIN assistance.award AS existing
      ON existing.assistance_award_unique_key =
         raw.assistance_award_unique_key
    LEFT JOIN assistance.assistance_listing AS listing
      ON listing.cfda_number =
         BTRIM(raw.raw_record ->> 'cfda_number')
    LEFT JOIN assistance.assistance_type AS assistance_type
      ON assistance_type.assistance_type_code =
         BTRIM(raw.raw_record ->> 'assistance_type_code')
    WHERE raw.load_batch_id IN (20, 21)
      AND existing.assistance_award_id IS NULL
),
award_checks AS (
    SELECT
        load_batch_id,
        assistance_award_unique_key,
        COUNT(*) AS observation_count,
        BOOL_AND(
            source_fain IS NULL AND source_uri IS NULL
        ) AS lacks_both_identifiers,
        BOOL_OR(
            assistance_listing_id IS NULL
        ) AS missing_listing,
        BOOL_OR(
            assistance_type_id IS NULL
        ) AS missing_type
    FROM historical
    GROUP BY
        load_batch_id,
        assistance_award_unique_key
)
SELECT
    load_batch_id,
    COUNT(*) AS missing_canonical_awards,
    COUNT(*) FILTER (
        WHERE lacks_both_identifiers
    ) AS awards_without_fain_or_uri,
    COUNT(*) FILTER (
        WHERE missing_listing
    ) AS awards_with_missing_listing,
    COUNT(*) FILTER (
        WHERE missing_type
    ) AS awards_with_missing_type,
    COUNT(*) FILTER (
        WHERE observation_count > 1
    ) AS awards_with_multiple_observations
FROM award_checks
GROUP BY load_batch_id
ORDER BY load_batch_id;

ROLLBACK;
