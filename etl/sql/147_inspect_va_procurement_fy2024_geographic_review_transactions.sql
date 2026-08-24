-- 147_inspect_va_procurement_fy2024_geographic_review_transactions.sql
--
-- Purpose:
--   Inspect the FY2024 Washington VA procurement transactions flagged by
--   Query 146 as:
--
--      ENTERPRISE_OR_NATIONAL_REVIEW
--      NON_WASHINGTON_ACTIVITY_REVIEW
--
-- Query 146 summary:
--   ENTERPRISE_OR_NATIONAL_REVIEW
--       26 transactions
--       $85,095,439.02
--
--   NON_WASHINGTON_ACTIVITY_REVIEW
--       63 transactions
--       $13,271,099.29
--
-- Combined review population:
--       89 transactions
--       $98,366,538.31
--
-- Methodological status:
--   GEOGRAPHIC ATTRIBUTION EVIDENCE DEVELOPMENT ONLY.
--
-- IMPORTANT:
--   This query does not change the canonical FY2024 VA procurement
--   population and does not assign final Washington/non-Washington
--   treatment.
--
-- It reuses the Query 146 diagnostic logic exactly so that the detailed
-- rows reconcile to the previously observed summary.


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
        t.source_file,
        t.source_row_number,

        a.generated_unique_award_id,
        a.piid,
        a.parent_award_id,
        a.award_type_code,
        a.award_type_description,
        a.award_description,

        a.period_of_performance_start,
        a.period_of_performance_end,

        a.recipient_id,
        a.awarding_agency_id,
        a.awarding_subagency_id,
        a.funding_agency_id,
        a.funding_subagency_id,

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

            ELSE 'GEOGRAPHY_UNCLEAR'

        END AS geographic_review_class

    FROM population p
)

SELECT
    p.geographic_review_class,

    p.award_transaction_id,
    p.usaspending_transaction_id,

    p.piid,
    p.parent_award_id,

    p.action_date,
    p.fiscal_quarter,
    p.modification_number,

    p.federal_action_obligation,
    p.current_total_value,
    p.potential_total_value,

    p.psc_code,
    p.psc_description,

    p.naics_code,
    p.naics_description,

    p.transaction_description,
    p.award_description,

    p.period_of_performance_start,
    p.period_of_performance_end,

    r.recipient_name,

    aa.agency_name AS awarding_agency,
    asa.agency_name AS awarding_subagency,

    fa.agency_name AS funding_agency,
    fsa.agency_name AS funding_subagency,

    pop.state_code,
    pop.county_code,
    pop.city_name,
    pop.zip_code,
    pop.location_scope,

    p.source_file,
    p.source_row_number

FROM profiled p

LEFT JOIN procurement.recipient r
  ON r.recipient_id = p.recipient_id

LEFT JOIN procurement.agency aa
  ON aa.agency_id = p.awarding_agency_id

LEFT JOIN procurement.agency asa
  ON asa.agency_id = p.awarding_subagency_id

LEFT JOIN procurement.agency fa
  ON fa.agency_id = p.funding_agency_id

LEFT JOIN procurement.agency fsa
  ON fsa.agency_id = p.funding_subagency_id

LEFT JOIN procurement.place_of_performance pop
  ON pop.award_transaction_id = p.award_transaction_id

WHERE
    p.geographic_review_class IN (
        'ENTERPRISE_OR_NATIONAL_REVIEW',
        'NON_WASHINGTON_ACTIVITY_REVIEW'
    )

ORDER BY
    p.geographic_review_class,
    ABS(p.federal_action_obligation) DESC,
    p.action_date,
    p.award_transaction_id;