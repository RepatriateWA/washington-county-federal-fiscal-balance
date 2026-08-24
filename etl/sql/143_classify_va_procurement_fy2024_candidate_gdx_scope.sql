-- 143_classify_va_procurement_fy2024_candidate_gdx_scope.sql
--
-- Purpose:
--   Create a provisional, reproducible FY2024 Washington VA procurement
--   classification into candidate GDX scope categories.
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
--   This query DOES NOT determine duplication.
--
--   Candidate GDX scope classification answers:
--       "What kind of VA activity does this procurement transaction
--        appear to represent?"
--
--   It does NOT answer:
--       "Should this procurement dollar be added to GDX?"
--
-- Possible later ledger treatments remain:
--       EXCLUDE_DUPLICATE
--       INCLUDE_SEPARATELY
--       REVIEW_REQUIRED
--
-- Methodological principle:
--   Classification and accounting treatment remain separate.


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

            -- =========================================================
            -- MEMORIAL BENEFITS / NATIONAL CEMETERY
            --
            -- Transaction text is required because construction PSCs
            -- alone cannot distinguish cemetery projects from other VA
            -- construction.
            -- =========================================================

            WHEN classification_text LIKE '%CEMETER%'
              OR classification_text LIKE '%BURIAL%'
              OR classification_text LIKE '%MEMORIAL%'
              OR p.psc_code = '9930'
            THEN 'MEMORIAL_BENEFITS_CANDIDATE'


            -- =========================================================
            -- MEDICAL CARE -- explicit medical services
            -- =========================================================

            WHEN p.psc_code LIKE 'Q%'
            THEN 'MEDICAL_CARE_CANDIDATE'


            -- =========================================================
            -- MEDICAL CARE -- health research
            -- =========================================================

            WHEN p.psc_code LIKE 'AN%'
            THEN 'MEDICAL_CARE_CANDIDATE'


            -- =========================================================
            -- MEDICAL CARE -- medical/dental product families
            --
            -- FSC 65xx is strongly medical/dental.
            -- =========================================================

            WHEN p.psc_code LIKE '65%'
            THEN 'MEDICAL_CARE_CANDIDATE'


            -- =========================================================
            -- MEDICAL CARE -- explicit medical equipment support
            -- =========================================================

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


            -- =========================================================
            -- MEDICAL CARE -- explicit medical/laboratory items
            -- =========================================================

            WHEN p.psc_code IN (
                '6632',
                '6640',
                '6835'
            )
            THEN 'MEDICAL_CARE_CANDIDATE'


            -- =========================================================
            -- MEDICAL CARE -- ambulance / patient transportation
            -- =========================================================

            WHEN p.psc_code = 'V225'
            THEN 'MEDICAL_CARE_CANDIDATE'


            -- =========================================================
            -- CONSTRUCTION
            --
            -- Y = construction of structures/facilities
            -- Z = maintenance/repair/alteration of real property
            -- C1 = A/E construction services
            --
            -- Cemetery/memorial projects were caught ABOVE so they do
            -- not automatically fall into generic construction.
            -- =========================================================

            WHEN p.psc_code LIKE 'Y%'
              OR p.psc_code LIKE 'Z%'
              OR p.psc_code LIKE 'C1%'
            THEN 'CONSTRUCTION_CANDIDATE'


            -- =========================================================
            -- FACILITY OPERATIONS
            --
            -- These are plausibly institutional VA expenditures but
            -- require later GDX scope determination.
            -- =========================================================

            WHEN p.psc_code LIKE 'S2%'
              OR p.psc_code LIKE 'J04%'
              OR p.psc_code LIKE 'N04%'
              OR p.psc_code LIKE 'H14%'
              OR p.psc_code LIKE 'H24%'
              OR p.psc_code LIKE 'H34%'
            THEN 'FACILITY_OPERATIONS_REVIEW'


            -- =========================================================
            -- IT / TELECOM
            -- =========================================================

            WHEN p.psc_code LIKE 'D%'
              OR p.psc_code LIKE '7A%'
              OR p.psc_code LIKE '7B%'
              OR p.psc_code LIKE '7C%'
              OR p.psc_code LIKE '7D%'
              OR p.psc_code LIKE '7E%'
              OR p.psc_code LIKE '7F%'
            THEN 'IT_TELECOM_REVIEW'


            -- =========================================================
            -- ADMINISTRATIVE / PROFESSIONAL SUPPORT
            -- =========================================================

            WHEN p.psc_code LIKE 'R%'
            THEN 'ADMIN_PROFESSIONAL_REVIEW'


            -- =========================================================
            -- SOCIAL / VETERAN SUPPORT SERVICES
            -- =========================================================

            WHEN p.psc_code LIKE 'G%'
            THEN 'SOCIAL_SUPPORT_REVIEW'


            -- =========================================================
            -- OTHER IDENTIFIED
            -- =========================================================

            WHEN p.psc_code IS NOT NULL
            THEN 'OTHER_IDENTIFIED_REVIEW'


            -- =========================================================
            -- UNRESOLVED
            -- =========================================================

            ELSE 'UNRESOLVED'

        END AS candidate_gdx_scope,

        CASE

            WHEN classification_text LIKE '%CEMETER%'
              OR classification_text LIKE '%BURIAL%'
              OR classification_text LIKE '%MEMORIAL%'
              OR p.psc_code = '9930'
            THEN 'HIGH'

            WHEN p.psc_code LIKE 'Q%'
              OR p.psc_code LIKE 'AN%'
              OR p.psc_code LIKE '65%'
              OR p.psc_code IN (
                    'J065','H165','H265','H365',
                    'K065','L065','N065','W065',
                    '6632','6640','6835','V225'
                 )
            THEN 'HIGH'

            WHEN p.psc_code LIKE 'Y%'
              OR p.psc_code LIKE 'Z%'
              OR p.psc_code LIKE 'C1%'
            THEN 'HIGH'

            WHEN p.psc_code LIKE 'S2%'
              OR p.psc_code LIKE 'J04%'
              OR p.psc_code LIKE 'N04%'
              OR p.psc_code LIKE 'H14%'
              OR p.psc_code LIKE 'H24%'
              OR p.psc_code LIKE 'H34%'
            THEN 'MEDIUM'

            WHEN p.psc_code LIKE 'D%'
              OR p.psc_code LIKE '7%'
              OR p.psc_code LIKE 'R%'
              OR p.psc_code LIKE 'G%'
            THEN 'MEDIUM'

            ELSE 'LOW'

        END AS classification_confidence

    FROM population p
),

summary AS (

    SELECT
        candidate_gdx_scope,
        classification_confidence,

        COUNT(*) AS transaction_count,

        SUM(federal_action_obligation)
            AS federal_action_obligation

    FROM classified

    GROUP BY
        candidate_gdx_scope,
        classification_confidence
),

control AS (

    SELECT
        COUNT(*) AS control_transaction_count,
        SUM(federal_action_obligation) AS control_obligation
    FROM population
)

SELECT
    s.candidate_gdx_scope,
    s.classification_confidence,
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
    s.candidate_gdx_scope,
    s.classification_confidence;