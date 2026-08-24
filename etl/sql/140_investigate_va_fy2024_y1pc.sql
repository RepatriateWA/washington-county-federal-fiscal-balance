-- 140_investigate_va_fy2024_y1pc.sql
--
-- Purpose:
--   Investigate the anomalously large FY2024 Washington VA procurement
--   transaction classified under PSC Y1PC.
--
-- Context:
--   PSC Y1PC FY2024 WA VA obligation = $73,086,136
--   GDX FY2024 WA Construction control = $23,778,000 (approx.)
--
-- Methodological status:
--   EVIDENCE DEVELOPMENT ONLY.
--   No overlap or ledger treatment is assigned.

WITH target AS (

    SELECT
        t.award_transaction_id,
        t.usaspending_transaction_id,
        t.award_id,
        t.load_batch_id,
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
        t.source_file,
        t.source_row_number

    FROM procurement.award_transaction t

    JOIN procurement.award a
      ON a.award_id = t.award_id

    JOIN procurement.agency fa
      ON fa.agency_id = a.funding_agency_id

    WHERE
        t.fiscal_year = 2024
        AND t.psc_code = 'Y1PC'

        AND upper(coalesce(fa.agency_name, ''))
            = 'DEPARTMENT OF VETERANS AFFAIRS'

        AND EXISTS (
            SELECT 1
            FROM procurement.place_of_performance pop
            WHERE pop.award_transaction_id = t.award_transaction_id
              AND upper(coalesce(pop.state_code, '')) = 'WA'
        )
)

SELECT
    t.*,

    a.generated_unique_award_id,
    a.piid,
    a.parent_award_id,
    a.award_type_code,
    a.award_type_description,
    a.award_description,
    a.period_of_performance_start,
    a.period_of_performance_end,

    aa.agency_name AS awarding_agency,
    asa.agency_name AS awarding_subagency,
    fa.agency_name AS funding_agency,
    fsa.agency_name AS funding_subagency,

    r.recipient_name,

    pop.state_code,
    pop.county_code,
    pop.city_name,
    pop.zip_code,
    pop.location_scope

FROM target t

JOIN procurement.award a
  ON a.award_id = t.award_id

LEFT JOIN procurement.agency aa
  ON aa.agency_id = a.awarding_agency_id

LEFT JOIN procurement.agency asa
  ON asa.agency_id = a.awarding_subagency_id

LEFT JOIN procurement.agency fa
  ON fa.agency_id = a.funding_agency_id

LEFT JOIN procurement.agency fsa
  ON fsa.agency_id = a.funding_subagency_id

LEFT JOIN procurement.recipient r
  ON r.recipient_id = a.recipient_id

LEFT JOIN procurement.place_of_performance pop
  ON pop.award_transaction_id = t.award_transaction_id

ORDER BY
    ABS(t.federal_action_obligation) DESC;