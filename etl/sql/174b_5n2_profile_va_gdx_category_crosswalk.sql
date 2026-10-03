/*
===============================================================================
ETL-174B-5N-2
VA GDX CATEGORY / USASPENDING ASSISTANCE CROSSWALK PROFILE
===============================================================================

PURPOSE
-------
Establish the quantitative and semantic structure needed to reconcile
Washington USAspending Veterans Affairs assistance (CFDA 64.*) against the
authoritative VA Geographic Distribution of Expenditures (GDX) ledger.

READ ONLY.
NO DATABASE WRITES.

THIS SCRIPT DOES NOT:
---------------------
- classify any CFDA program as duplicate or additive;
- create program-policy mappings;
- modify VA source policy;
- assume title similarity proves accounting overlap;
- force USAspending obligations to equal GDX expenditures.

QUESTIONS
---------
1. What expenditure categories actually exist in VA GDX?
2. Which categories are components versus control totals?
3. What are their statewide Washington annual amounts?
4. Do component categories reconcile to the authoritative GDX control?
5. How did the category structure change in FY2024?
6. Which USAspending CFDA 64.* programs are plausible semantic counterparts
   to GDX categories and therefore candidates for subsequent reconciliation?

KNOWN CONTROL
-------------
Certified FY2020-FY2024 Washington CFDA 64.* assistance:

    $23,707,643,332.28

The complete CFDA 64.* population remains unresolved entering this profile.
===============================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-2 - VA GDX CATEGORY / USASPENDING ASSISTANCE CROSSWALK PROFILE'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1
   GDX CATEGORY DICTIONARY
   ========================================================================== */

\echo ''
\echo 'SECTION 1 - COMPLETE VA GDX EXPENDITURE CATEGORY DICTIONARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    gdx_category_id,
    category_code,
    category_name,
    aggregation_role,
    first_fiscal_year,
    last_fiscal_year,
    description
FROM va.gdx_expenditure_category
ORDER BY
    first_fiscal_year,
    category_code;


/* ============================================================================
   SECTION 2
   CATEGORY INVENTORY BY FISCAL YEAR

   Shows which normalized GDX categories are actually populated in each year.
   ========================================================================== */

\echo ''
\echo 'SECTION 2 - POPULATED GDX CATEGORY INVENTORY BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    COUNT(*) AS county_rows,
    COUNT(DISTINCT e.county_id) AS distinct_counties,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    c.aggregation_role,
    c.category_code;


/* ============================================================================
   SECTION 3
   EXPENDITURE CLASS x CATEGORY

   expenditure_class is retained separately from normalized category metadata.
   This exposes any semantic distinctions embedded in the loaded GDX rows.
   ========================================================================== */

\echo ''
\echo 'SECTION 3 - GDX EXPENDITURE CLASS x CATEGORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    e.expenditure_class,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    COUNT(*) AS county_rows,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    e.fiscal_year,
    e.expenditure_class,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    e.expenditure_class,
    c.category_code;


/* ============================================================================
   SECTION 4
   SOURCE CATEGORY NAME x NORMALIZED CATEGORY

   This is provenance evidence showing how raw GDX labels were normalized.
   ========================================================================== */

\echo ''
\echo 'SECTION 4 - SOURCE CATEGORY NAME -> NORMALIZED GDX CATEGORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    e.schema_regime,
    e.source_category_name,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    COUNT(*) AS row_count,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
GROUP BY
    e.fiscal_year,
    e.schema_regime,
    e.source_category_name,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    c.category_code,
    e.source_category_name;


/* ============================================================================
   SECTION 5
   AUTHORITATIVE GDX CONTROL — STATEWIDE

   The existing view defines:
       FY2015-FY2023 -> TOTAL_EXPENDITURE
       FY2024+       -> TOTAL_DIRECT_EXPENDITURE
                        + TOTAL_INDIRECT_EXPENDITURE
   ========================================================================== */

\echo ''
\echo 'SECTION 5 - AUTHORITATIVE VA GDX WASHINGTON STATEWIDE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    fiscal_year,
    COUNT(*) AS county_rows,
    ROUND(SUM(va_gdx_expenditure_amount), 2)
        AS washington_gdx_control
FROM va.v_washington_county_gdx_control_total
WHERE fiscal_year BETWEEN 2020 AND 2024
GROUP BY fiscal_year
ORDER BY fiscal_year;


/* ============================================================================
   SECTION 6
   LEGACY GDX CATEGORY TOTALS — FY2020-FY2023
   ========================================================================== */

\echo ''
\echo 'SECTION 6 - LEGACY GDX CATEGORY TOTALS FY2020-FY2023'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2023
GROUP BY
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    washington_amount DESC;


/* ============================================================================
   SECTION 7
   FY2024 REVISED GDX CATEGORY TOTALS
   ========================================================================== */

\echo ''
\echo 'SECTION 7 - FY2024 REVISED GDX CATEGORY TOTALS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    c.category_code,
    c.category_name,
    c.aggregation_role,
    e.expenditure_class,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year = 2024
GROUP BY
    c.category_code,
    c.category_name,
    c.aggregation_role,
    e.expenditure_class
ORDER BY
    washington_amount DESC,
    c.category_code;


/* ============================================================================
   SECTION 8
   GDX CONTROL-CATEGORY REPRODUCTION

   Independently reconstruct the control using the exact category-code rules
   discovered in ETL-174B-5N.
   ========================================================================== */

\echo ''
\echo 'SECTION 8 - INDEPENDENT GDX CONTROL-CATEGORY REPRODUCTION'
\echo '----------------------------------------------------------------------------------------------------'

WITH reconstructed AS (
    SELECT
        e.fiscal_year,

        SUM(
            CASE
                WHEN e.fiscal_year <= 2023
                 AND c.category_code = 'TOTAL_EXPENDITURE'
                    THEN e.expenditure_amount

                WHEN e.fiscal_year >= 2024
                 AND c.category_code IN (
                        'TOTAL_DIRECT_EXPENDITURE',
                        'TOTAL_INDIRECT_EXPENDITURE'
                     )
                    THEN e.expenditure_amount

                ELSE 0
            END
        ) AS reconstructed_control

    FROM va.gdx_county_expenditure AS e

    JOIN va.gdx_expenditure_category AS c
      ON c.gdx_category_id = e.gdx_category_id

    WHERE e.fiscal_year BETWEEN 2020 AND 2024

    GROUP BY e.fiscal_year
),

authoritative AS (
    SELECT
        fiscal_year,
        SUM(va_gdx_expenditure_amount) AS authoritative_control
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2020 AND 2024
    GROUP BY fiscal_year
)

SELECT
    a.fiscal_year,
    ROUND(a.authoritative_control, 2)
        AS authoritative_control,
    ROUND(r.reconstructed_control, 2)
        AS reconstructed_control,
    ROUND(
        r.reconstructed_control
        - a.authoritative_control,
        2
    ) AS difference

FROM authoritative AS a

JOIN reconstructed AS r
  ON r.fiscal_year = a.fiscal_year

ORDER BY a.fiscal_year;


/* ============================================================================
   SECTION 9
   HARD CONTROL REPRODUCTION ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 9 - GDX CONTROL REPRODUCTION ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_failures bigint;
BEGIN

    WITH reconstructed AS (
        SELECT
            e.fiscal_year,

            SUM(
                CASE
                    WHEN e.fiscal_year <= 2023
                     AND c.category_code = 'TOTAL_EXPENDITURE'
                        THEN e.expenditure_amount

                    WHEN e.fiscal_year >= 2024
                     AND c.category_code IN (
                            'TOTAL_DIRECT_EXPENDITURE',
                            'TOTAL_INDIRECT_EXPENDITURE'
                         )
                        THEN e.expenditure_amount

                    ELSE 0
                END
            ) AS reconstructed_control

        FROM va.gdx_county_expenditure AS e

        JOIN va.gdx_expenditure_category AS c
          ON c.gdx_category_id = e.gdx_category_id

        WHERE e.fiscal_year BETWEEN 2020 AND 2024

        GROUP BY e.fiscal_year
    ),

    authoritative AS (
        SELECT
            fiscal_year,
            SUM(va_gdx_expenditure_amount) AS authoritative_control
        FROM va.v_washington_county_gdx_control_total
        WHERE fiscal_year BETWEEN 2020 AND 2024
        GROUP BY fiscal_year
    )

    SELECT COUNT(*)
    INTO v_failures

    FROM authoritative AS a

    JOIN reconstructed AS r
      ON r.fiscal_year = a.fiscal_year

    WHERE ROUND(
        r.reconstructed_control
        - a.authoritative_control,
        2
    ) <> 0.00;

    IF v_failures <> 0 THEN
        RAISE EXCEPTION
            'GDX control reproduction failed for % fiscal years',
            v_failures;
    END IF;

    RAISE NOTICE
        'PASS: GDX authoritative control reproduced exactly for FY2020-FY2024';

END
$$;


/* ============================================================================
   SECTION 10
   AGGREGATION ROLE PROFILE

   This tells us whether aggregation_role itself can safely distinguish
   component categories from totals/subtotals.
   ========================================================================== */

\echo ''
\echo 'SECTION 10 - GDX AGGREGATION ROLE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    c.aggregation_role,
    COUNT(DISTINCT c.gdx_category_id) AS category_count,
    COUNT(*) AS expenditure_rows,
    ROUND(SUM(e.expenditure_amount), 2) AS raw_sum_across_rows
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
GROUP BY c.aggregation_role
ORDER BY c.aggregation_role;


/* ============================================================================
   SECTION 11
   COMPONENT-LIKE GDX CATEGORIES BY YEAR

   We do NOT assume an aggregation-role vocabulary. Instead we exclude only
   the exact control-category codes already proven by the authoritative view.

   These amounts are descriptive and MUST NOT be summed into the ledger
   without understanding the category hierarchy.
   ========================================================================== */

\echo ''
\echo 'SECTION 11 - NON-CONTROL GDX CATEGORIES BY YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role,
    ROUND(SUM(e.expenditure_amount), 2) AS washington_amount
FROM va.gdx_county_expenditure AS e
JOIN va.gdx_expenditure_category AS c
  ON c.gdx_category_id = e.gdx_category_id
WHERE e.fiscal_year BETWEEN 2020 AND 2024
  AND c.category_code NOT IN (
        'TOTAL_EXPENDITURE',
        'TOTAL_DIRECT_EXPENDITURE',
        'TOTAL_INDIRECT_EXPENDITURE'
  )
GROUP BY
    e.fiscal_year,
    c.category_code,
    c.category_name,
    c.aggregation_role
ORDER BY
    e.fiscal_year,
    washington_amount DESC;


/* ============================================================================
   SECTION 12
   COMPLETE CFDA 64.* PROGRAM PROFILE FOR CROSSWALK

   Same population as ETL-174B-5N, now arranged beside the GDX work.
   ========================================================================== */

\echo ''
\echo 'SECTION 12 - CFDA 64.* PROGRAM PROFILE FOR CROSSWALK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT NULLIF(award_id_fain, ''))
        AS distinct_nonblank_fains,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2020),
        2
    ) AS fy2020,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2021),
        2
    ) AS fy2021,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2022),
        2
    ) AS fy2022,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2023),
        2
    ) AS fy2023,

    ROUND(
        SUM(federal_action_obligation)
            FILTER (WHERE action_date_fiscal_year = 2024),
        2
    ) AS fy2024,

    ROUND(SUM(federal_action_obligation), 2)
        AS total_2020_2024,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number LIKE '64.%'

GROUP BY cfda_number

ORDER BY total_2020_2024 DESC;


/* ============================================================================
   SECTION 13
   SEMANTIC CROSSWALK CANDIDATES

   IMPORTANT:
   This is a discovery aid only.

   A row here means:
       "These labels contain related accounting concepts."

   It DOES NOT mean:
       "The USAspending program has been proven duplicate."

   Matching is deliberately conservative and transparent.
   ========================================================================== */

\echo ''
\echo 'SECTION 13 - SEMANTIC CFDA -> GDX CROSSWALK CANDIDATES'
\echo '----------------------------------------------------------------------------------------------------'

WITH cfda AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        SUM(federal_action_obligation) AS cfda_total
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
    GROUP BY cfda_number
),

categories AS (
    SELECT DISTINCT
        category_code,
        category_name,
        aggregation_role
    FROM va.gdx_expenditure_category
),

candidate AS (
    SELECT
        f.cfda_number,
        f.cfda_title,
        f.cfda_total,
        c.category_code,
        c.category_name,
        c.aggregation_role,

        CASE
            WHEN
                (
                    UPPER(f.cfda_title) LIKE '%COMPENSATION%'
                    AND UPPER(c.category_name) LIKE '%COMPENSATION%'
                )
                OR
                (
                    UPPER(f.cfda_title) LIKE '%PENSION%'
                    AND UPPER(c.category_name) LIKE '%PENSION%'
                )
                OR
                (
                    (
                        UPPER(f.cfda_title) LIKE '%EDUCATION%'
                        OR UPPER(f.cfda_title) LIKE '%GI BILL%'
                    )
                    AND
                    (
                        UPPER(c.category_name) LIKE '%EDUCATION%'
                        OR UPPER(c.category_name) LIKE '%GI BILL%'
                    )
                )
                OR
                (
                    (
                        UPPER(f.cfda_title) LIKE '%MEDICAL%'
                        OR UPPER(f.cfda_title) LIKE '%VHA%'
                        OR UPPER(f.cfda_title) LIKE '%HEALTH%'
                        OR UPPER(f.cfda_title) LIKE '%PRESCRIPTION%'
                        OR UPPER(f.cfda_title) LIKE '%DENTAL%'
                        OR UPPER(f.cfda_title) LIKE '%PROSTHETIC%'
                        OR UPPER(f.cfda_title) LIKE '%CHAMPVA%'
                    )
                    AND
                    (
                        UPPER(c.category_name) LIKE '%MEDICAL%'
                        OR UPPER(c.category_name) LIKE '%HEALTH%'
                        OR UPPER(c.category_name) LIKE '%VHA%'
                        OR UPPER(c.category_name) LIKE '%PRESCRIPTION%'
                        OR UPPER(c.category_name) LIKE '%DENTAL%'
                        OR UPPER(c.category_name) LIKE '%PROSTHETIC%'
                    )
                )
                OR
                (
                    (
                        UPPER(f.cfda_title) LIKE '%BURIAL%'
                        OR UPPER(f.cfda_title) LIKE '%CEMETERY%'
                        OR UPPER(f.cfda_title) LIKE '%MEMORIAL%'
                    )
                    AND
                    (
                        UPPER(c.category_name) LIKE '%BURIAL%'
                        OR UPPER(c.category_name) LIKE '%CEMETERY%'
                        OR UPPER(c.category_name) LIKE '%MEMORIAL%'
                    )
                )
                OR
                (
                    UPPER(f.cfda_title) LIKE '%CONSTRUCTION%'
                    AND UPPER(c.category_name) LIKE '%CONSTRUCTION%'
                )
            THEN TRUE
            ELSE FALSE
        END AS semantic_candidate

    FROM cfda AS f
    CROSS JOIN categories AS c
)

SELECT
    cfda_number,
    cfda_title,
    ROUND(cfda_total, 2) AS cfda_total,
    category_code,
    category_name,
    aggregation_role

FROM candidate

WHERE semantic_candidate

ORDER BY
    cfda_total DESC,
    cfda_number,
    category_code;


/* ============================================================================
   SECTION 14
   MAJOR CFDA PROGRAMS WITHOUT A SEMANTIC GDX CANDIDATE

   This is especially important. It prevents our semantic matcher from making
   apparent coverage look more complete than it really is.
   ========================================================================== */

\echo ''
\echo 'SECTION 14 - CFDA PROGRAMS WITHOUT SEMANTIC GDX CANDIDATE'
\echo '----------------------------------------------------------------------------------------------------'

WITH cfda AS (
    SELECT
        cfda_number,
        MAX(cfda_title) AS cfda_title,
        SUM(federal_action_obligation) AS cfda_total,
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ) AS covid_total

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'

    GROUP BY cfda_number
),

categories AS (
    SELECT DISTINCT
        category_code,
        category_name
    FROM va.gdx_expenditure_category
),

matches AS (
    SELECT DISTINCT
        f.cfda_number

    FROM cfda AS f
    CROSS JOIN categories AS c

    WHERE
           (
               UPPER(f.cfda_title) LIKE '%COMPENSATION%'
               AND UPPER(c.category_name) LIKE '%COMPENSATION%'
           )

        OR (
               UPPER(f.cfda_title) LIKE '%PENSION%'
               AND UPPER(c.category_name) LIKE '%PENSION%'
           )

        OR (
               (
                   UPPER(f.cfda_title) LIKE '%EDUCATION%'
                   OR UPPER(f.cfda_title) LIKE '%GI BILL%'
               )
               AND
               (
                   UPPER(c.category_name) LIKE '%EDUCATION%'
                   OR UPPER(c.category_name) LIKE '%GI BILL%'
               )
           )

        OR (
               (
                   UPPER(f.cfda_title) LIKE '%MEDICAL%'
                   OR UPPER(f.cfda_title) LIKE '%VHA%'
                   OR UPPER(f.cfda_title) LIKE '%HEALTH%'
                   OR UPPER(f.cfda_title) LIKE '%PRESCRIPTION%'
                   OR UPPER(f.cfda_title) LIKE '%DENTAL%'
                   OR UPPER(f.cfda_title) LIKE '%PROSTHETIC%'
                   OR UPPER(f.cfda_title) LIKE '%CHAMPVA%'
               )
               AND
               (
                   UPPER(c.category_name) LIKE '%MEDICAL%'
                   OR UPPER(c.category_name) LIKE '%HEALTH%'
                   OR UPPER(c.category_name) LIKE '%VHA%'
                   OR UPPER(c.category_name) LIKE '%PRESCRIPTION%'
                   OR UPPER(c.category_name) LIKE '%DENTAL%'
                   OR UPPER(c.category_name) LIKE '%PROSTHETIC%'
               )
           )

        OR (
               (
                   UPPER(f.cfda_title) LIKE '%BURIAL%'
                   OR UPPER(f.cfda_title) LIKE '%CEMETERY%'
                   OR UPPER(f.cfda_title) LIKE '%MEMORIAL%'
               )
               AND
               (
                   UPPER(c.category_name) LIKE '%BURIAL%'
                   OR UPPER(c.category_name) LIKE '%CEMETERY%'
                   OR UPPER(c.category_name) LIKE '%MEMORIAL%'
               )
           )

        OR (
               UPPER(f.cfda_title) LIKE '%CONSTRUCTION%'
               AND UPPER(c.category_name) LIKE '%CONSTRUCTION%'
           )
)

SELECT
    f.cfda_number,
    f.cfda_title,
    ROUND(f.cfda_total, 2) AS obligation_dollars,
    ROUND(f.covid_total, 2) AS covid_dollars

FROM cfda AS f

LEFT JOIN matches AS m
  ON m.cfda_number = f.cfda_number

WHERE m.cfda_number IS NULL

ORDER BY f.cfda_total DESC;


/* ============================================================================
   SECTION 15
   ANNUAL CFDA 64.* vs AUTHORITATIVE GDX CONTROL

   THIS IS NOT A RECONCILIATION EQUATION.

   USAspending = obligations.
   GDX         = expenditures.

   The comparison is diagnostic only.
   ========================================================================== */

\echo ''
\echo 'SECTION 15 - ANNUAL CFDA 64.* ASSISTANCE vs VA GDX CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

WITH assistance AS (
    SELECT
        action_date_fiscal_year AS fiscal_year,
        SUM(federal_action_obligation) AS assistance_obligation
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
    GROUP BY action_date_fiscal_year
),

gdx AS (
    SELECT
        fiscal_year,
        SUM(va_gdx_expenditure_amount) AS gdx_expenditure
    FROM va.v_washington_county_gdx_control_total
    WHERE fiscal_year BETWEEN 2020 AND 2024
    GROUP BY fiscal_year
)

SELECT
    a.fiscal_year,

    ROUND(a.assistance_obligation, 2)
        AS usaspending_assistance_obligation,

    ROUND(g.gdx_expenditure, 2)
        AS gdx_expenditure,

    ROUND(
        100.0 * a.assistance_obligation
        / NULLIF(g.gdx_expenditure, 0),
        2
    ) AS assistance_as_percent_of_gdx

FROM assistance AS a

JOIN gdx AS g
  ON g.fiscal_year = a.fiscal_year

ORDER BY a.fiscal_year;


/* ============================================================================
   SECTION 16
   CFDA 64.* CONTROL ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 16 - CFDA 64.* CONTROL ASSERTION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_amount numeric;
    v_programs bigint;
BEGIN

    SELECT
        ROUND(SUM(federal_action_obligation), 2),
        COUNT(DISTINCT cfda_number)

    INTO
        v_amount,
        v_programs

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%';


    IF v_amount <> 23707643332.28::numeric THEN
        RAISE EXCEPTION
            'CFDA 64.* control failure. Expected 23707643332.28; found %',
            v_amount;
    END IF;


    IF v_programs <> 49 THEN
        RAISE EXCEPTION
            'CFDA 64.* program-count failure. Expected 49; found %',
            v_programs;
    END IF;


    RAISE NOTICE
        'PASS: CFDA 64.* control reproduced - 49 programs, $%',
        v_amount;

END
$$;


/* ============================================================================
   SECTION 17
   FINAL DIAGNOSTIC SUMMARY
   ========================================================================== */

\echo ''
\echo 'SECTION 17 - FINAL DIAGNOSTIC SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH category_inventory AS (
    SELECT
        COUNT(*) AS category_count,
        COUNT(*) FILTER (
            WHERE category_code IN (
                'TOTAL_EXPENDITURE',
                'TOTAL_DIRECT_EXPENDITURE',
                'TOTAL_INDIRECT_EXPENDITURE'
            )
        ) AS known_control_categories
    FROM va.gdx_expenditure_category
),

gdx_years AS (
    SELECT COUNT(DISTINCT fiscal_year) AS year_count
    FROM va.gdx_county_expenditure
    WHERE fiscal_year BETWEEN 2020 AND 2024
),

cfda AS (
    SELECT
        COUNT(DISTINCT cfda_number) AS program_count,
        ROUND(SUM(federal_action_obligation), 2) AS obligation_dollars
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
      AND cfda_number LIKE '64.%'
)

SELECT
    c.category_count AS gdx_dictionary_categories,
    c.known_control_categories,
    y.year_count AS gdx_years_profiled,
    f.program_count AS cfda_64_programs,
    f.obligation_dollars AS cfda_64_obligation_control
FROM category_inventory AS c
CROSS JOIN gdx_years AS y
CROSS JOIN cfda AS f;


/* ============================================================================
   SECTION 18
   COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-2 PROFILE COMPLETE - GDX CATEGORY CROSSWALK EVIDENCE - NO DB WRITES'
\echo '===================================================================================================='