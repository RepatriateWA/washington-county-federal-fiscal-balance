COPY (
    WITH source_classifications AS (
        SELECT
            raw.load_batch_id,
            NULLIF(BTRIM(raw.raw_record ->> 'naics_code'), '')
                AS naics_code,
            NULLIF(BTRIM(raw.raw_record ->> 'naics_description'), '')
                AS naics_description,
            NULLIF(BTRIM(raw.raw_record ->> 'product_or_service_code'), '')
                AS psc_code,
            NULLIF(BTRIM(raw.raw_record ->> 'product_or_service_code_description'), '')
                AS psc_description
        FROM procurement.raw_award_transaction raw
        WHERE raw.load_batch_id IN (22, 23)
    ),
    missing_naics AS (
        SELECT
            'NAICS'::text AS classification,
            s.naics_code AS code,
            MIN(s.naics_description) AS source_description,
            COUNT(*) AS observation_count,
            COUNT(*) FILTER (
                WHERE s.load_batch_id = 22
            ) AS fy2018_observations,
            COUNT(*) FILTER (
                WHERE s.load_batch_id = 23
            ) AS fy2019_observations
        FROM source_classifications s
        LEFT JOIN procurement.naics n
            ON n.naics_code = s.naics_code
        WHERE s.naics_code IS NOT NULL
          AND n.naics_code IS NULL
        GROUP BY s.naics_code
    ),
    missing_psc AS (
        SELECT
            'PSC'::text AS classification,
            s.psc_code AS code,
            MIN(s.psc_description) AS source_description,
            COUNT(*) AS observation_count,
            COUNT(*) FILTER (
                WHERE s.load_batch_id = 22
            ) AS fy2018_observations,
            COUNT(*) FILTER (
                WHERE s.load_batch_id = 23
            ) AS fy2019_observations
        FROM source_classifications s
        LEFT JOIN procurement.psc p
            ON p.psc_code = s.psc_code
        WHERE s.psc_code IS NOT NULL
          AND p.psc_code IS NULL
        GROUP BY s.psc_code
    )
    SELECT *
    FROM missing_naics

    UNION ALL

    SELECT *
    FROM missing_psc

    ORDER BY classification, observation_count DESC, code
) TO STDOUT WITH CSV HEADER;
