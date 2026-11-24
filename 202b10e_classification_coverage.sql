BEGIN TRANSACTION READ ONLY;

WITH source_codes AS (
    SELECT DISTINCT
        NULLIF(BTRIM(raw_record ->> 'naics_code'), '')
            AS naics_code,
        NULLIF(BTRIM(raw_record ->> 'product_or_service_code'), '')
            AS psc_code
    FROM procurement.raw_award_transaction
    WHERE load_batch_id IN (22, 23)
)
SELECT
    'NAICS' AS classification,
    COUNT(DISTINCT s.naics_code) AS source_codes,
    COUNT(DISTINCT s.naics_code) FILTER (
        WHERE n.naics_code IS NULL
    ) AS missing_codes
FROM source_codes s
LEFT JOIN procurement.naics n
    ON n.naics_code = s.naics_code
WHERE s.naics_code IS NOT NULL

UNION ALL

SELECT
    'PSC',
    COUNT(DISTINCT s.psc_code),
    COUNT(DISTINCT s.psc_code) FILTER (
        WHERE p.psc_code IS NULL
    )
FROM source_codes s
LEFT JOIN procurement.psc p
    ON p.psc_code = s.psc_code
WHERE s.psc_code IS NOT NULL;

COMMIT;
