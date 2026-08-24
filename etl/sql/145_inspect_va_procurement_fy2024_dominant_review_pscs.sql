-- 145_inspect_va_procurement_fy2024_dominant_review_pscs.sql
--
-- Purpose:
--   Inspect the individual FY2024 Washington VA procurement transactions
--   underlying the dominant PSCs remaining in the Query 144 review
--   residual.
--
-- Target PSCs:
--   DG11  IT/network telecom access
--   R707  Contract/procurement/acquisition support
--   R408  Program management/support
--   V226  Taxicab transportation
--   D304  Telecommunications/transmission
--   G099  Other social services
--   S215  Warehousing/storage
--
-- Query 144 net values:
--   DG11   +$15.941M
--   R707    +$8.528M
--   R408    +$7.754M
--   V226    +$6.279M
--   D304    -$4.977M
--   G099    +$3.066M
--   S215    +$2.160M
--
-- Methodological status:
--   TRANSACTION-LEVEL EVIDENCE DEVELOPMENT ONLY.
--
-- IMPORTANT:
--   No GDX category or ledger treatment is assigned by this query.
--   We are inspecting the evidence before changing Query 143 rules.


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

target_transactions AS (

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
        a.funding_subagency_id

    FROM procurement.award_transaction t

    JOIN procurement.award a
      ON a.award_id = t.award_id

    WHERE
        t.fiscal_year = 2024

        AND NULLIF(trim(t.psc_code), '') IN (
            'DG11',
            'R707',
            'R408',
            'V226',
            'D304',
            'G099',
            'S215'
        )

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
)

SELECT
    t.psc_code,
    psc.psc_description,

    t.award_transaction_id,
    t.usaspending_transaction_id,

    t.piid,
    t.parent_award_id,

    t.action_date,
    t.fiscal_quarter,
    t.modification_number,

    t.federal_action_obligation,
    t.current_total_value,
    t.potential_total_value,

    t.naics_code,
    naics.naics_description,

    t.transaction_description,
    t.award_description,

    t.period_of_performance_start,
    t.period_of_performance_end,

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

    t.source_file,
    t.source_row_number

FROM target_transactions t

LEFT JOIN procurement.psc psc
  ON psc.psc_code = t.psc_code

LEFT JOIN procurement.naics naics
  ON naics.naics_code = t.naics_code

LEFT JOIN procurement.recipient r
  ON r.recipient_id = t.recipient_id

LEFT JOIN procurement.agency aa
  ON aa.agency_id = t.awarding_agency_id

LEFT JOIN procurement.agency asa
  ON asa.agency_id = t.awarding_subagency_id

LEFT JOIN procurement.agency fa
  ON fa.agency_id = t.funding_agency_id

LEFT JOIN procurement.agency fsa
  ON fsa.agency_id = t.funding_subagency_id

LEFT JOIN procurement.place_of_performance pop
  ON pop.award_transaction_id = t.award_transaction_id

ORDER BY
    CASE t.psc_code
        WHEN 'DG11' THEN 1
        WHEN 'R707' THEN 2
        WHEN 'R408' THEN 3
        WHEN 'V226' THEN 4
        WHEN 'D304' THEN 5
        WHEN 'G099' THEN 6
        WHEN 'S215' THEN 7
        ELSE 99
    END,
    ABS(t.federal_action_obligation) DESC,
    t.action_date,
    t.award_transaction_id;