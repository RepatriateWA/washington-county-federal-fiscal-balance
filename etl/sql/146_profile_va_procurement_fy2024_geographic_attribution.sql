-- 146_profile_va_procurement_fy2024_geographic_attribution.sql
--
-- Purpose:
--   Investigate whether FY2024 Washington VA procurement transactions
--   reported with Washington place of performance actually represent:
--
--      1. Washington-local VA activity,
--      2. enterprise/nationwide VA activity,
--      3. activity supporting clearly non-Washington VA facilities,
--      4. geographically unclear activity.
--
-- Canonical population:
--   FY2024
--   Washington place of performance
--   Department of Veterans Affairs funding agency
--
-- Expected control:
--   2,319 transactions
--   $384,771,014.98 federal action obligation
--
-- IMPORTANT:
--   This query does NOT change the canonical population.
--   It does NOT assign final geographic treatment.
--
-- It is a profiling query designed to identify transactions that require
-- closer geographic attribution review before GDX overlap treatment.


WITH RECURSIVE va_roots AS (

    SELECT agency_id
    FROM procurement.agency
    WHERE
           upper(coalesce(agency_name, ''))
               = 'DEPARTMENT OF VETERANS AFFAIRS'
        OR upper(coalesce(agency_name_normalized, ''))
               = 'DEPARTMENT OF VETERANS AFFAIRS'
),

va_agencies AS (

    SELECT agency_id
    FROM va_roots

    UNION ALL

    SELECT child.agency_id
    FROM procurement.agency child
    JOIN va_agencies parent
      ON child.parent_agency_id = parent.agency_id
),

population AS (

    SELECT
        t.award_transaction_id,
        t.usaspending_transaction_id,
        t.award_id,

        t.action_date,
        t.federal_action_obligation,

        NULLIF(trim(t.psc_code), '') AS psc_code,
        NULLIF(trim(t.naics_code), '') AS naics_code,

        t.transaction_description,

        a.piid,
        a.parent_award_id,
        a.award_description,
        a.period_of_performance_start,
        a.period_of_performance_end,

        a.recipient_id,

        psc.psc_description,
        naics.naics_description,

        concat_ws(
            ' ',
            upper(coalesce(t.transaction_description, '')),
            upper(coalesce(a.award_description, '')),
            upper(coalesce(psc.psc_description, '')),
            upper(coalesce(naics.naics_description, ''))
        ) AS geographic_text

    FROM procurement.award_transaction t

    JOIN procurement.award a
      ON a.award_id = t.award_id

    LEFT JOIN procurement.psc psc
      ON psc.psc_code = t.psc_code

    LEFT JOIN procurement.naics naics
      ON naics.naics_code = t.naics_code

    WHERE
        t.fiscal_year = 2024

        AND EXISTS (
            SELECT 1
            FROM va_agencies va
            WHERE va.agency_id = a.funding_agency_id
               OR va.agency_id = a.funding_subagency_id
        )

        AND EXISTS (
            SELECT 1
            FROM procurement.place_of_performance pop
            WHERE pop.award_transaction_id = t.award_transaction_id
              AND upper(coalesce(pop.state_code, '')) = 'WA'
        )
),

profiled AS (

    SELECT
        p.*,

        CASE

            -- =========================================================
            -- CLEAR ENTERPRISE / NATIONAL ACTIVITY
            -- =========================================================

            WHEN geographic_text LIKE '%VA ENTERPRISE%'
              OR geographic_text LIKE '%ENTERPRISE-WIDE%'
              OR geographic_text LIKE '%ENTERPRISE WIDE%'
              OR geographic_text LIKE '%NATIONWIDE%'
              OR geographic_text LIKE '%NATIONAL%'
              OR geographic_text LIKE '%THROUGHOUT THE FIFTY%'
              OR geographic_text LIKE '%50 STATES%'
              OR geographic_text LIKE '%FIFTY (50) UNITED STATES%'
              OR geographic_text LIKE '%ALL VA%'
            THEN 'ENTERPRISE_OR_NATIONAL_REVIEW'


            -- =========================================================
            -- CLEAR NON-WASHINGTON FACILITY / VISN REFERENCES
            --
            -- These are examples exposed in Query 145.
            -- The intent is to flag, not to exhaustively encode every
            -- possible non-WA geography.
            -- =========================================================

            WHEN geographic_text LIKE '%WEST PALM BEACH%'
              OR geographic_text LIKE '%BAY PINES%'
              OR geographic_text LIKE '%PALO ALTO%'
              OR geographic_text LIKE '%PHOENIX%'
              OR geographic_text LIKE '%ORLANDO%'
              OR geographic_text LIKE '%FORT MEADE%'
              OR geographic_text LIKE '%HOT SPRINGS%'
              OR geographic_text LIKE '%NORTH LITTLE ROCK%'
              OR geographic_text LIKE '%LITTLE ROCK%'
              OR geographic_text LIKE '%WHITE RIVER JUNCTION%'
              OR geographic_text LIKE '%OKLAHOMA CITY%'
              OR geographic_text LIKE '%MUSKOGEE%'
              OR geographic_text LIKE '%SALT LAKE CITY%'
              OR geographic_text LIKE '%GRAND JUNCTION%'
              OR geographic_text LIKE '%TAMPA%'
              OR geographic_text LIKE '%NORTHPORT%'
            THEN 'NON_WASHINGTON_ACTIVITY_REVIEW'


            -- =========================================================
            -- CLEAR WASHINGTON VA FACILITY / PROGRAM REFERENCES
            -- =========================================================

            WHEN geographic_text LIKE '%PUGET SOUND%'
              OR geographic_text LIKE '%SEATTLE VA%'
              OR geographic_text LIKE '%SEATTLE VAMC%'
              OR geographic_text LIKE '%SPOKANE VAMC%'
              OR geographic_text LIKE '%MANN-GRANDSTAFF%'
              OR geographic_text LIKE '%MANN GRANDSTAFF%'
              OR geographic_text LIKE '%WALLA WALLA%'
              OR geographic_text LIKE '%WAINWRIGHT%'
              OR geographic_text LIKE '%AMERICAN LAKE%'
              OR geographic_text LIKE '%TACOMA%'
              OR geographic_text LIKE '%VANCOUVER VA%'
              OR geographic_text LIKE '%TAHOMA NATIONAL CEMETERY%'
            THEN 'WASHINGTON_LOCAL_EVIDENCE'


            -- =========================================================
            -- NO STRONG TEXTUAL GEOGRAPHIC SIGNAL
            -- =========================================================

            ELSE 'GEOGRAPHY_UNCLEAR'

        END AS geographic_review_class

    FROM population p
),

summary AS (

    SELECT
        geographic_review_class,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS federal_action_obligation
    FROM profiled
    GROUP BY geographic_review_class
),

control AS (

    SELECT
        COUNT(*) AS control_transaction_count,
        SUM(federal_action_obligation) AS control_obligation
    FROM population
)

SELECT
    s.geographic_review_class,
    s.transaction_count,
    s.federal_action_obligation,

    ROUND(
        s.federal_action_obligation / 1000000.0,
        3
    ) AS obligation_millions,

    ROUND(
        100.0 * s.federal_action_obligation
        / NULLIF(c.control_obligation, 0),
        4
    ) AS pct_of_control,

    c.control_transaction_count,
    c.control_obligation

FROM summary s
CROSS JOIN control c

ORDER BY
    ABS(s.federal_action_obligation) DESC,
    s.geographic_review_class;