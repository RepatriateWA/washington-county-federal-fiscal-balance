-- 141_profile_va_procurement_fy2024_timing.sql
--
-- Purpose:
--   Profile the timing structure of the canonical FY2024 Washington
--   VA procurement population.
--
-- Canonical control:
--   2,319 transactions
--   $384,771,014.98 federal action obligation
--
-- Questions:
--   1. How much FY2024 obligation belongs to awards whose performance
--      begins after FY2024?
--   2. How much belongs to awards already underway during FY2024?
--   3. How much consists of negative modifications / deobligations?
--   4. How much has missing or ambiguous performance-period timing?
--
-- Methodological status:
--   TIMING / ACCOUNTING DIAGNOSTIC ONLY.
--   No GDX overlap classification is assigned here.

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

        a.piid,
        a.award_description,
        a.period_of_performance_start,
        a.period_of_performance_end

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
),

summary AS (

    SELECT
        timing_class,
        COUNT(*) AS transaction_count,
        SUM(federal_action_obligation) AS obligation
    FROM classified
    GROUP BY timing_class
),

control AS (

    SELECT
        COUNT(*) AS control_transaction_count,
        SUM(federal_action_obligation) AS control_obligation
    FROM population
)

SELECT
    s.timing_class,
    s.transaction_count,
    s.obligation,
    ROUND(s.obligation / 1000000.0, 3) AS obligation_millions,
    ROUND(
        100.0 * s.obligation
        / NULLIF(c.control_obligation, 0),
        4
    ) AS pct_of_control,
    c.control_transaction_count,
    c.control_obligation

FROM summary s
CROSS JOIN control c

ORDER BY
    ABS(s.obligation) DESC,
    s.timing_class;