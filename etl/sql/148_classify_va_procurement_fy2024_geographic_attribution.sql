-- 148_classify_va_procurement_fy2024_geographic_attribution.sql
--
-- Purpose:
--   Apply a conservative, evidence-supported geographic attribution layer
--   to the canonical FY2024 Washington VA procurement population.
--
-- Canonical population:
--   FY2024
--   USAspending place of performance = Washington
--   Department of Veterans Affairs funding agency
--
-- Expected control:
--   2,319 transactions
--   $384,771,014.98 federal action obligation
--
-- Geographic attribution classes:
--
--   CONFIRMED_WASHINGTON_LOCAL
--       Strong affirmative evidence that the transaction concerns a
--       Washington VA facility/program/location.
--
--   CONFIRMED_ENTERPRISE_OR_MULTISTATE
--       Strong affirmative evidence that the transaction serves the VA
--       enterprise, nationwide, or multiple jurisdictions.
--
--   CONFIRMED_NON_WASHINGTON_BENEFICIARY
--       Strong affirmative evidence that the named VA facility/project
--       benefiting from the procurement is outside Washington.
--
--   UNRESOLVED_GEOGRAPHIC_ATTRIBUTION
--       USAspending reports Washington place of performance, but the
--       transaction/award text does not provide enough evidence for a
--       stronger attribution.
--
-- IMPORTANT:
--   No transaction is removed.
--   No GDX overlap treatment is assigned here.
--
-- Methodological principle:
--   Explicit evidence overrides broad keyword inference.
--   Generic words such as "NATIONAL" and bare city names such as
--   "PHOENIX" are NOT sufficient by themselves.


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
        t.fiscal_year,
        t.fiscal_quarter,
        t.modification_number,

        t.federal_action_obligation,
        t.current_total_value,
        t.potential_total_value,

        NULLIF(trim(t.psc_code), '') AS psc_code,
        NULLIF(trim(t.naics_code), '') AS naics_code,

        t.transaction_description,

        a.generated_unique_award_id,
        a.piid,
        a.parent_award_id,
        a.award_type_code,
        a.award_type_description,
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

classified AS (

    SELECT
        p.*,

        CASE

            -- =========================================================
            -- 1. CONFIRMED WASHINGTON-LOCAL ACTIVITY
            --
            -- These rules are intentionally specific.
            --
            -- Tahoma National Cemetery must be evaluated before any
            -- enterprise/national terminology because Query 147 showed
            -- that the word NATIONAL created major false positives.
            -- =========================================================

            WHEN geographic_text LIKE '%TAHOMA NATIONAL CEMETERY%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%PUGET SOUND%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%SEATTLE VAMC%'
              OR geographic_text LIKE '%SEATTLE VA%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%SPOKANE VAMC%'
              OR geographic_text LIKE '%SPOKANE VA%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%MANN-GRANDSTAFF%'
              OR geographic_text LIKE '%MANN GRANDSTAFF%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%JONATHAN M. WAINWRIGHT%'
              OR geographic_text LIKE '%JONATHAN M WAINWRIGHT%'
              OR geographic_text LIKE '%WAINWRIGHT VA%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%AMERICAN LAKE%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'

            WHEN geographic_text LIKE '%VANCOUVER VA%'
              OR geographic_text LIKE '%VANCOUVER VAMC%'
            THEN 'CONFIRMED_WASHINGTON_LOCAL'


            -- =========================================================
            -- 2. CONFIRMED ENTERPRISE / MULTISTATE ACTIVITY
            --
            -- Require explicit scope language rather than merely the
            -- word NATIONAL.
            -- =========================================================

            WHEN geographic_text LIKE '%VA ENTERPRISE%'
              OR geographic_text LIKE '%ENTERPRISE-WIDE%'
              OR geographic_text LIKE '%ENTERPRISE WIDE%'
            THEN 'CONFIRMED_ENTERPRISE_OR_MULTISTATE'

            WHEN geographic_text LIKE '%THROUGHOUT THE FIFTY (50) UNITED STATES%'
              OR geographic_text LIKE '%THROUGHOUT THE FIFTY UNITED STATES%'
              OR geographic_text LIKE '%50 STATES%'
            THEN 'CONFIRMED_ENTERPRISE_OR_MULTISTATE'

            WHEN geographic_text LIKE '%NATIONWIDE VA%'
              OR geographic_text LIKE '%VA NATIONWIDE%'
            THEN 'CONFIRMED_ENTERPRISE_OR_MULTISTATE'


            -- =========================================================
            -- 3. CONFIRMED NON-WASHINGTON BENEFICIARY / FACILITY
            --
            -- Require explicit facility/location combinations observed
            -- in Query 147.
            --
            -- Avoid naked terms such as "PHOENIX", which produced a
            -- false positive for Seattle HVAC work.
            -- =========================================================

            WHEN geographic_text LIKE '%PALO ALTO%'
             AND (
                    geographic_text LIKE '%VAMC%'
                 OR geographic_text LIKE '%VA MEDICAL%'
                 OR geographic_text LIKE '%BUILDING%'
                 OR geographic_text LIKE '%DESIGN BUILD%'
                 )
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%WEST PALM BEACH%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%LITTLE ROCK, AR%'
              OR geographic_text LIKE '%VAMC LITTLE ROCK%'
              OR geographic_text LIKE '%NORTH LITTLE ROCK%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%ORLANDO, FL%'
              OR geographic_text LIKE '%VAMC ORLANDO%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%WHITE RIVER JUNCTION%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%GRAND JUNCTION, CO%'
              OR geographic_text LIKE '%VAMC GRAND JUNCTION%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%TAMPA, FL%'
              OR geographic_text LIKE '%VAMC TAMPA%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%BAY PINES%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%MUSKOGEE, OK%'
              OR geographic_text LIKE '%VAMC MUSKOGEE%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%FORT MEADE, SD%'
              OR geographic_text LIKE '%VAMC FORT MEADE%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%HOUSTON NATIONAL CEMETERY%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'

            WHEN geographic_text LIKE '%FT GIBSON NATIONAL CEMETERY%'
              OR geographic_text LIKE '%FORT GIBSON NATIONAL CEMETERY%'
            THEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY'


            -- =========================================================
            -- 4. UNRESOLVED
            -- =========================================================

            ELSE 'UNRESOLVED_GEOGRAPHIC_ATTRIBUTION'

        END AS geographic_attribution_class

    FROM population p
),

summary AS (

    SELECT
        geographic_attribution_class,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation)
            AS federal_action_obligation
    FROM classified
    GROUP BY geographic_attribution_class
),

control AS (

    SELECT
        COUNT(*) AS control_transaction_count,
        SUM(federal_action_obligation)
            AS control_obligation
    FROM population
)

SELECT
    s.geographic_attribution_class,
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
    CASE s.geographic_attribution_class
        WHEN 'CONFIRMED_WASHINGTON_LOCAL' THEN 1
        WHEN 'CONFIRMED_ENTERPRISE_OR_MULTISTATE' THEN 2
        WHEN 'CONFIRMED_NON_WASHINGTON_BENEFICIARY' THEN 3
        WHEN 'UNRESOLVED_GEOGRAPHIC_ATTRIBUTION' THEN 4
        ELSE 99
    END;