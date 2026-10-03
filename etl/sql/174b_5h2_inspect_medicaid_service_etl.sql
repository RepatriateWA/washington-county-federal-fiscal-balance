/*
===============================================================================
ETL-174B-5H-2
MEDICAID SERVICE-DETAIL ETL INSPECTION
===============================================================================

PURPOSE
-------
Determine why cms.medicaid_service_expenditures contains no Washington
FY2020-FY2024 rows even though cms_raw.medicaid_mbes contains the source detail.

READ ONLY.
NO DB WRITES.
===============================================================================
*/

\pset pager off


/* 1. Row counts by layer and fiscal year. */

SELECT
    'RAW_MBED' AS layer,
    fiscal_year,
    COUNT(*) AS row_count,
    ROUND(SUM(federal_share), 2) AS federal_share
FROM cms_raw.medicaid_mbes
WHERE state_name = 'Washington'
  AND fiscal_year BETWEEN 2015 AND 2024
GROUP BY fiscal_year

UNION ALL

SELECT
    'NORMALIZED_SERVICE_DETAIL' AS layer,
    fiscal_year,
    COUNT(*) AS row_count,
    ROUND(SUM(federal_share), 2) AS federal_share
FROM cms.medicaid_service_expenditures AS mse
JOIN reference.state_registry AS s
  ON s.state_id = mse.state_id
WHERE s.state_abbreviation = 'WA'
  AND fiscal_year BETWEEN 2015 AND 2024
GROUP BY fiscal_year

ORDER BY fiscal_year, layer;


/* 2. Does normalized service detail contain anything at all? */

SELECT
    COUNT(*) AS total_rows,
    MIN(fiscal_year) AS first_fiscal_year,
    MAX(fiscal_year) AS last_fiscal_year,
    COUNT(DISTINCT state_id) AS distinct_states
FROM cms.medicaid_service_expenditures;


/* 3. Table definition / columns. */

SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'cms'
  AND table_name = 'medicaid_service_expenditures'
ORDER BY ordinal_position;


/* 4. Constraints. */

SELECT
    con.conname AS constraint_name,
    pg_get_constraintdef(con.oid, true) AS constraint_definition
FROM pg_constraint AS con
JOIN pg_class AS rel
  ON rel.oid = con.conrelid
JOIN pg_namespace AS ns
  ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'cms'
  AND rel.relname = 'medicaid_service_expenditures'
ORDER BY con.conname;


/* 5. Raw MBES structure. */

SELECT
    ordinal_position,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'cms_raw'
  AND table_name = 'medicaid_mbes'
ORDER BY ordinal_position;


/* 6. Raw Washington row-type / section structure. */

SELECT
    fiscal_year,
    section_code,
    row_type,
    COUNT(*) AS row_count,
    ROUND(SUM(federal_share), 2) AS federal_share
FROM cms_raw.medicaid_mbes
WHERE state_name = 'Washington'
  AND fiscal_year BETWEEN 2015 AND 2024
GROUP BY
    fiscal_year,
    section_code,
    row_type
ORDER BY
    fiscal_year,
    section_code,
    row_type;


/* 7. Category mapping coverage from raw MBES into reference dictionary. */

SELECT
    r.fiscal_year,

    COUNT(*) AS raw_rows,

    COUNT(msc.medicaid_service_category_id)
        AS category_matched_rows,

    COUNT(*) - COUNT(msc.medicaid_service_category_id)
        AS category_unmatched_rows,

    ROUND(
        100.0 * COUNT(msc.medicaid_service_category_id)
        / NULLIF(COUNT(*), 0),
        4
    ) AS category_match_pct

FROM cms_raw.medicaid_mbes AS r

LEFT JOIN reference.medicaid_service_category AS msc
  ON LOWER(TRIM(r.service_category))
     = LOWER(TRIM(msc.service_category_name))

WHERE r.state_name = 'Washington'
  AND r.fiscal_year BETWEEN 2015 AND 2024

GROUP BY r.fiscal_year
ORDER BY r.fiscal_year;


/* 8. Show unmatched category names. */

SELECT
    r.service_category,
    COUNT(*) AS raw_row_count,
    MIN(r.fiscal_year) AS first_fiscal_year,
    MAX(r.fiscal_year) AS last_fiscal_year,
    ROUND(SUM(r.federal_share), 2) AS federal_share

FROM cms_raw.medicaid_mbes AS r

LEFT JOIN reference.medicaid_service_category AS msc
  ON LOWER(TRIM(r.service_category))
     = LOWER(TRIM(msc.service_category_name))

WHERE r.state_name = 'Washington'
  AND r.fiscal_year BETWEEN 2015 AND 2024
  AND msc.medicaid_service_category_id IS NULL

GROUP BY r.service_category

ORDER BY
    ABS(SUM(r.federal_share)) DESC NULLS LAST,
    r.service_category;


/* 9. Search database objects for likely Medicaid service loaders/views. */

SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_type

FROM pg_class AS c

JOIN pg_namespace AS n
  ON n.oid = c.relnamespace

WHERE
       LOWER(c.relname) LIKE '%medicaid%service%'
    OR LOWER(c.relname) LIKE '%service%expenditure%'
    OR LOWER(c.relname) LIKE '%mbes%'

ORDER BY
    schema_name,
    object_name;


/* 10. End marker. */

SELECT
    'ETL-174B-5H-2 INSPECTION COMPLETE - NO DB WRITES'
        AS final_status;