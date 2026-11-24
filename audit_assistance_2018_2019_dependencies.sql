BEGIN;
SET TRANSACTION READ ONLY;

SELECT
    raw.load_batch_id,
    COUNT(*) AS raw_rows,
    COUNT(*) FILTER (
        WHERE award.assistance_award_id IS NOT NULL
    ) AS resolved_awards,
    COUNT(*) FILTER (
        WHERE listing.assistance_listing_id IS NOT NULL
    ) AS resolved_listings,
    COUNT(*) FILTER (
        WHERE typ.assistance_type_id IS NOT NULL
    ) AS resolved_types,
    COUNT(*) FILTER (
        WHERE award.assistance_award_id IS NOT NULL
          AND listing.assistance_listing_id IS NOT NULL
          AND typ.assistance_type_id IS NOT NULL
    ) AS fully_resolved_rows
FROM assistance.raw_award_transaction AS raw
LEFT JOIN assistance.award AS award
    ON award.assistance_award_unique_key =
       raw.assistance_award_unique_key
LEFT JOIN assistance.assistance_listing AS listing
    ON listing.cfda_number =
       BTRIM(raw.raw_record ->> 'cfda_number')
LEFT JOIN assistance.assistance_type AS typ
    ON typ.assistance_type_code =
       BTRIM(raw.raw_record ->> 'assistance_type_code')
WHERE raw.load_batch_id IN (20, 21)
GROUP BY raw.load_batch_id
ORDER BY raw.load_batch_id;

ROLLBACK;
