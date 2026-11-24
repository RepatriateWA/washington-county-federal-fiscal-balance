BEGIN TRANSACTION READ ONLY;

WITH classified AS (
    SELECT
        r.load_batch_id,
        r.raw_record ->> 'contract_transaction_unique_key'
            AS transaction_key,
        COALESCE(
            NULLIF(BTRIM(r.raw_record ->> 'federal_action_obligation'), '')::numeric,
            0
        ) AS obligation,
        (
            NULLIF(BTRIM(r.raw_record ->> 'naics_code'), '') IS NOT NULL
            AND n.naics_code IS NULL
        ) AS missing_naics,
        (
            NULLIF(BTRIM(r.raw_record ->> 'product_or_service_code'), '') IS NOT NULL
            AND p.psc_code IS NULL
        ) AS missing_psc,
        (t.award_transaction_id IS NOT NULL) AS already_canonical
    FROM procurement.raw_award_transaction r
    LEFT JOIN procurement.naics n
        ON n.naics_code =
            NULLIF(BTRIM(r.raw_record ->> 'naics_code'), '')
    LEFT JOIN procurement.psc p
        ON p.psc_code =
            NULLIF(BTRIM(r.raw_record ->> 'product_or_service_code'), '')
    LEFT JOIN procurement.award_transaction t
        ON t.usaspending_transaction_id =
            r.raw_record ->> 'contract_transaction_unique_key'
    WHERE r.load_batch_id IN (22, 23)
)
SELECT
    load_batch_id,
    COUNT(*) AS total_observations,
    COUNT(*) FILTER (
        WHERE missing_naics OR missing_psc
    ) AS affected_observations,
    COUNT(*) FILTER (
        WHERE missing_naics AND missing_psc
    ) AS missing_both,
    COUNT(*) FILTER (
        WHERE (missing_naics OR missing_psc)
          AND already_canonical
    ) AS affected_already_canonical,
    ROUND(SUM(obligation), 2) AS total_net_obligations,
    ROUND(SUM(ABS(obligation)), 2) AS total_absolute_obligations,
    ROUND(SUM(obligation) FILTER (
        WHERE missing_naics OR missing_psc
    ), 2) AS affected_net_obligations,
    ROUND(SUM(ABS(obligation)) FILTER (
        WHERE missing_naics OR missing_psc
    ), 2) AS affected_absolute_obligations,
    ROUND(
        100 * SUM(ABS(obligation)) FILTER (
            WHERE missing_naics OR missing_psc
        ) / NULLIF(SUM(ABS(obligation)), 0),
        4
    ) AS affected_percent_absolute,
    ROUND(SUM(obligation) FILTER (
        WHERE (missing_naics OR missing_psc)
          AND NOT already_canonical
    ), 2) AS affected_net_not_yet_canonical
FROM classified
GROUP BY ROLLUP(load_batch_id)
ORDER BY load_batch_id NULLS LAST;

COMMIT;