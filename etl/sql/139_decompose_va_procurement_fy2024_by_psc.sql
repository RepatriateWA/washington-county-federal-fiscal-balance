-- 139_decompose_va_procurement_fy2024_by_psc.sql
--
-- Purpose:
--   Decompose the canonical FY2024 Washington VA procurement control
--   population by Product or Service Code (PSC).
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
-- Methodological status:
--   DESCRIPTIVE DECOMPOSITION ONLY.
--   PSC categories are not yet assigned GDX overlap treatment.
--
-- Principle:
--   Classification and overlap determination remain separate.


WITH RECURSIVE va_roots AS (

    SELECT
        agency_id
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

va_fy2024_wa AS (

    SELECT
        t.award_transaction_id,
        t.usaspending_transaction_id,
        t.award_id,
        t.action_date,
        t.federal_action_obligation,
        NULLIF(trim(t.psc_code), '') AS psc_code,
        NULLIF(trim(t.naics_code), '') AS naics_code,
        t.transaction_description

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

psc_decomposition AS (

    SELECT
        v.psc_code,

        COALESCE(
            p.psc_description,
            CASE
                WHEN v.psc_code IS NULL
                    THEN '[MISSING PSC]'
                ELSE '[PSC NOT FOUND IN REFERENCE TABLE]'
            END
        ) AS psc_description,

        COALESCE(
            p.product_or_service,
            '[UNKNOWN]'
        ) AS product_or_service,

        COUNT(*) AS transaction_count,

        SUM(v.federal_action_obligation)
            AS federal_action_obligation

    FROM va_fy2024_wa v

    LEFT JOIN procurement.psc p
      ON p.psc_code = v.psc_code

    GROUP BY
        v.psc_code,
        p.psc_description,
        p.product_or_service
),

control AS (

    SELECT
        COUNT(*) AS control_transaction_count,
        SUM(federal_action_obligation) AS control_obligation
    FROM va_fy2024_wa
)

SELECT
    d.psc_code,
    d.psc_description,
    d.product_or_service,
    d.transaction_count,
    d.federal_action_obligation,

    ROUND(
        d.federal_action_obligation / 1000000.0,
        3
    ) AS obligation_millions,

    ROUND(
        100.0 * d.federal_action_obligation
        / NULLIF(c.control_obligation, 0),
        4
    ) AS pct_of_va_procurement,

    c.control_transaction_count,
    c.control_obligation

FROM psc_decomposition d
CROSS JOIN control c

ORDER BY
    ABS(d.federal_action_obligation) DESC,
    d.psc_code NULLS LAST;