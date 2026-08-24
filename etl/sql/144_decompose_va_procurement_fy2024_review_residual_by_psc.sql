-- 144_decompose_va_procurement_fy2024_review_residual_by_psc.sql
--
-- Purpose:
--   Decompose the FY2024 Washington VA procurement transactions that
--   remain outside the HIGH-confidence candidate GDX scope categories
--   established in Query 143.
--
-- Canonical population:
--   FY2024
--   Washington place of performance
--   Department of Veterans Affairs funding agency
--
-- Query 143 control:
--   2,319 transactions
--   $384,771,014.98 federal action obligation
--
-- Query 143 HIGH-confidence subtotal:
--   MEDICAL_CARE_CANDIDATE
--   CONSTRUCTION_CANDIDATE
--   MEMORIAL_BENEFITS_CANDIDATE
--
-- Expected review residual:
--   approximately $62.510M
--   approximately 16.25% of total FY2024 VA procurement obligations
--
-- Methodological status:
--   RESIDUAL DECOMPOSITION ONLY.
--   No duplication or ledger treatment is assigned here.


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
        a.award_description,
        a.period_of_performance_start,
        a.period_of_performance_end,

        psc.psc_description,
        naics.naics_description,

        concat_ws(
            ' ',
            upper(coalesce(t.transaction_description, '')),
            upper(coalesce(a.award_description, '')),
            upper(coalesce(psc.psc_description, '')),
            upper(coalesce(naics.naics_description, ''))
        ) AS classification_text

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

            WHEN classification_text LIKE '%CEMETER%'
              OR classification_text LIKE '%BURIAL%'
              OR classification_text LIKE '%MEMORIAL%'
              OR p.psc_code = '9930'
            THEN 'MEMORIAL_BENEFITS_CANDIDATE'

            WHEN p.psc_code LIKE 'Q%'
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code LIKE 'AN%'
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code LIKE '65%'
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code IN (
                'J065',
                'H165',
                'H265',
                'H365',
                'K065',
                'L065',
                'N065',
                'W065'
            )
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code IN (
                '6632',
                '6640',
                '6835'
            )
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code = 'V225'
            THEN 'MEDICAL_CARE_CANDIDATE'

            WHEN p.psc_code LIKE 'Y%'
              OR p.psc_code LIKE 'Z%'
              OR p.psc_code LIKE 'C1%'
            THEN 'CONSTRUCTION_CANDIDATE'

            WHEN p.psc_code LIKE 'S2%'
              OR p.psc_code LIKE 'J04%'
              OR p.psc_code LIKE 'N04%'
              OR p.psc_code LIKE 'H14%'
              OR p.psc_code LIKE 'H24%'
              OR p.psc_code LIKE 'H34%'
            THEN 'FACILITY_OPERATIONS_REVIEW'

            WHEN p.psc_code LIKE 'D%'
              OR p.psc_code LIKE '7A%'
              OR p.psc_code LIKE '7B%'
              OR p.psc_code LIKE '7C%'
              OR p.psc_code LIKE '7D%'
              OR p.psc_code LIKE '7E%'
              OR p.psc_code LIKE '7F%'
            THEN 'IT_TELECOM_REVIEW'

            WHEN p.psc_code LIKE 'R%'
            THEN 'ADMIN_PROFESSIONAL_REVIEW'

            WHEN p.psc_code LIKE 'G%'
            THEN 'SOCIAL_SUPPORT_REVIEW'

            WHEN p.psc_code IS NOT NULL
            THEN 'OTHER_IDENTIFIED_REVIEW'

            ELSE 'UNRESOLVED'

        END AS candidate_gdx_scope

    FROM population p
),

review_population AS (

    SELECT *
    FROM classified
    WHERE candidate_gdx_scope IN (
        'ADMIN_PROFESSIONAL_REVIEW',
        'OTHER_IDENTIFIED_REVIEW',
        'IT_TELECOM_REVIEW',
        'FACILITY_OPERATIONS_REVIEW',
        'SOCIAL_SUPPORT_REVIEW',
        'UNRESOLVED'
    )
),

psc_summary AS (

    SELECT
        candidate_gdx_scope,

        psc_code,

        COALESCE(
            psc_description,
            CASE
                WHEN psc_code IS NULL
                    THEN '[MISSING PSC]'
                ELSE '[PSC DESCRIPTION NOT FOUND]'
            END
        ) AS psc_description,

        COUNT(*) AS transaction_count,

        SUM(federal_action_obligation)
            AS federal_action_obligation

    FROM review_population

    GROUP BY
        candidate_gdx_scope,
        psc_code,
        psc_description
),

review_control AS (

    SELECT
        COUNT(*) AS review_transaction_count,
        SUM(federal_action_obligation)
            AS review_obligation
    FROM review_population
),

full_control AS (

    SELECT
        COUNT(*) AS full_transaction_count,
        SUM(federal_action_obligation)
            AS full_obligation
    FROM population
)

SELECT
    s.candidate_gdx_scope,
    s.psc_code,
    s.psc_description,
    s.transaction_count,
    s.federal_action_obligation,

    ROUND(
        s.federal_action_obligation / 1000000.0,
        3
    ) AS obligation_millions,

    ROUND(
        100.0 * s.federal_action_obligation
        / NULLIF(r.review_obligation, 0),
        4
    ) AS pct_of_review_residual,

    ROUND(
        100.0 * s.federal_action_obligation
        / NULLIF(f.full_obligation, 0),
        4
    ) AS pct_of_full_va_procurement,

    r.review_transaction_count,
    r.review_obligation,

    f.full_transaction_count,
    f.full_obligation

FROM psc_summary s

CROSS JOIN review_control r
CROSS JOIN full_control f

ORDER BY
    ABS(s.federal_action_obligation) DESC,
    s.candidate_gdx_scope,
    s.psc_code NULLS LAST;