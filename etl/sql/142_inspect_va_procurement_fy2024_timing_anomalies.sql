-- 142_inspect_va_procurement_fy2024_timing_anomalies.sql
--
-- Purpose:
--   Inspect FY2024 Washington VA procurement transactions whose
--   award performance timing appears anomalous relative to FY2024:
--
--      1. Performance starts after FY2024
--      2. Performance ended before FY2024
--
-- Canonical control population:
--   FY2024
--   Washington place of performance
--   Department of Veterans Affairs funding agency
--
-- Methodological status:
--   TRANSACTION-LEVEL DIAGNOSTIC ONLY.
--   No GDX overlap or ledger treatment is assigned here.
--
-- Relationship to Query 141:
--   Query 141 summarizes the timing buckets.
--   Query 142 preserves the same population and classification logic
--   but returns the individual transactions in the two timing-anomaly
--   categories for inspection.


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
        t.psc_code,
        t.naics_code,
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
        a.awarding_agency_id,
        a.awarding_subagency_id,
        a.funding_agency_id,
        a.funding_subagency_id

    FROM procurement.award_transaction t

    JOIN procurement.award a
      ON a.award_id = t.award_id

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
            WHEN p.federal_action_obligation < 0
                THEN 'NEGATIVE_MODIFICATION'

            WHEN p.period_of_performance_start IS NULL
                THEN 'MISSING_PERFORMANCE_START'

            WHEN p.period_of_performance_start >= DATE '2024-10-01'
                THEN 'PERFORMANCE_STARTS_AFTER_FY2024'

            WHEN p.period_of_performance_end IS NOT NULL
             AND p.period_of_performance_end < DATE '2023-10-01'
                THEN 'PERFORMANCE_ENDED_BEFORE_FY2024'

            WHEN p.period_of_performance_start <= DATE '2024-09-30'
             AND (
                    p.period_of_performance_end IS NULL
                    OR p.period_of_performance_end >= DATE '2023-10-01'
                 )
                THEN 'PERFORMANCE_OVERLAPS_FY2024'

            ELSE 'OTHER_TIMING_CONDITION'
        END AS timing_class

    FROM population p
)

SELECT
    c.timing_class,

    c.award_transaction_id,
    c.usaspending_transaction_id,

    c.piid,
    c.parent_award_id,

    c.action_date,
    c.fiscal_quarter,
    c.modification_number,

    c.period_of_performance_start,
    c.period_of_performance_end,

    c.federal_action_obligation,
    c.current_total_value,
    c.potential_total_value,

    c.psc_code,
    psc.psc_description,

    c.naics_code,
    naics.naics_description,

    c.transaction_description,
    c.award_description,

    r.recipient_name,

    aa.agency_name AS awarding_agency,
    asa.agency_name AS awarding_subagency,
    fa.agency_name AS funding_agency,
    fsa.agency_name AS funding_subagency,

    pop.state_code,
    pop.county_code,
    pop.city_name,
    pop.zip_code,
    pop.location_scope

FROM classified c

LEFT JOIN procurement.psc psc
  ON psc.psc_code = c.psc_code

LEFT JOIN procurement.naics naics
  ON naics.naics_code = c.naics_code

LEFT JOIN procurement.recipient r
  ON r.recipient_id = c.recipient_id

LEFT JOIN procurement.agency aa
  ON aa.agency_id = c.awarding_agency_id

LEFT JOIN procurement.agency asa
  ON asa.agency_id = c.awarding_subagency_id

LEFT JOIN procurement.agency fa
  ON fa.agency_id = c.funding_agency_id

LEFT JOIN procurement.agency fsa
  ON fsa.agency_id = c.funding_subagency_id

LEFT JOIN procurement.place_of_performance pop
  ON pop.award_transaction_id = c.award_transaction_id

WHERE
    c.timing_class IN (
        'PERFORMANCE_STARTS_AFTER_FY2024',
        'PERFORMANCE_ENDED_BEFORE_FY2024'
    )

ORDER BY
    c.timing_class,
    ABS(c.federal_action_obligation) DESC,
    c.action_date,
    c.award_transaction_id;