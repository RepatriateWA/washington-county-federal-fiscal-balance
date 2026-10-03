/*
===============================================================================
ETL-174B-5J
WASHINGTON USAspending ASSISTANCE — ACCOUNTING BRIDGE RECONSTRUCTION
===============================================================================

PURPOSE
-------
Reconstruct the complete FY2020-FY2024 Washington USAspending assistance
universe after all accounting classifications persisted through
ETL-174B-5I-2.

THIS SCRIPT IS READ ONLY.
NO DATABASE WRITES.

QUESTIONS
---------
1. Does the certified assistance universe still reproduce the established
   $348,524,407,674.34 gross control?

2. How much is currently:
       INCLUDE_ADDITIVE
       EXCLUDE_DUPLICATE
       WITHHOLD_UNRESOLVED
       UNCLASSIFIED_REVIEW

3. How much COVID / IIJA / extraordinary funding lies in each disposition?

4. What programs make up the remaining unclassified review universe?

5. Which remaining programs should be investigated next by materiality?

ACCOUNTING PRINCIPLE
--------------------
A persisted award classification overrides a program-level descriptive
classification for accounting disposition.

Program-level source policy is informative, but this reconstruction does not
infer an accounting disposition merely from similarity of program names.

Anything not affirmatively classified remains UNCLASSIFIED_REVIEW.

COVID, IIJA, and extraordinary status remain independent analytical
dimensions.

EXPECTED GROSS CONTROL
----------------------
FY2020-FY2024 Washington certified assistance:
    $348,524,407,674.34
===============================================================================
*/


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5J — WASHINGTON ASSISTANCE ACCOUNTING BRIDGE RECONSTRUCTION'
\echo '===================================================================================================='
\echo 'READ ONLY — NO DATABASE WRITES'
\echo ''


/* ============================================================================
   SECTION 1
   CERTIFIED GROSS CONTROL
   ========================================================================== */

\echo ''
\echo 'SECTION 1 — CERTIFIED ASSISTANCE GROSS CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT *
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
)
SELECT
    COUNT(*) AS transaction_count,
    ROUND(SUM(federal_action_obligation), 2) AS gross_assistance_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,
    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars
FROM universe;


/* Exact gross assertion. */

DO $$
DECLARE
    v_gross numeric;
BEGIN
    SELECT ROUND(SUM(federal_action_obligation), 2)
    INTO v_gross
    FROM analysis.v_certified_assistance_ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024;

    IF v_gross IS DISTINCT FROM 348524407674.34::numeric THEN
        RAISE EXCEPTION
            'ETL-174B-5J gross control failed. Expected 348524407674.34; observed %',
            v_gross;
    END IF;

    RAISE NOTICE
        'PASS gross assistance control: %',
        v_gross;
END
$$;


/* ============================================================================
   SECTION 2
   INSPECT CURRENT AWARD-CLASSIFICATION UNIVERSE

   This establishes exactly what has been persisted before reconstructing
   transaction dollars.
   ========================================================================== */

\echo ''
\echo 'SECTION 2 — PERSISTED AWARD CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    methodology_version,
    accounting_disposition,
    COUNT(*) AS classified_awards
FROM reference.federal_inflow_award_classification
WHERE source_system = 'USASPENDING_ASSISTANCE'
GROUP BY
    methodology_version,
    accounting_disposition
ORDER BY
    methodology_version,
    accounting_disposition;


/* ============================================================================
   SECTION 3
   AWARD-LEVEL ACCOUNTING MATCH

   Important:
   An award may potentially have classifications from multiple methodology
   versions. We therefore rank applicable classifications and select one
   accounting classification per transaction.

   Preference:
     1. classification whose FY validity covers transaction FY
     2. most recently updated
     3. highest classification ID as deterministic tie-breaker

   We DO NOT infer accounting treatment for an unmatched award.
   ========================================================================== */

\echo ''
\echo 'SECTION 3 — TRANSACTION ACCOUNTING MATCH COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.federal_inflow_award_classification_id,
        c.accounting_disposition,
        c.methodology_version,
        c.updated_at,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        s.accounting_disposition,
        s.methodology_version
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    CASE
        WHEN accounting_disposition IS NULL
            THEN 'UNCLASSIFIED_REVIEW'
        ELSE accounting_disposition
    END AS bridge_disposition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars

FROM bridge

GROUP BY 1
ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 4
   FULL ACCOUNTING BRIDGE WITH FUNDING DIMENSIONS
   ========================================================================== */

\echo ''
\echo 'SECTION 4 — FULL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,
        c.methodology_version,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    bridge_disposition,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS total_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,

    ROUND(
        SUM(
            CASE
                WHEN NOT is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS non_covid_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars

FROM bridge

GROUP BY bridge_disposition
ORDER BY total_dollars DESC;


/* ============================================================================
   SECTION 5
   BRIDGE CLOSURE ASSERTION
   ========================================================================== */

\echo ''
\echo 'SECTION 5 — BRIDGE CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.federal_action_obligation,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
),

summary AS (
    SELECT
        ROUND(SUM(federal_action_obligation), 2)
            AS bridge_total,

        ROUND(
            SUM(
                CASE
                    WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ) AS include_additive,

        ROUND(
            SUM(
                CASE
                    WHEN bridge_disposition = 'EXCLUDE_DUPLICATE'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ) AS exclude_duplicate,

        ROUND(
            SUM(
                CASE
                    WHEN bridge_disposition = 'WITHHOLD_UNRESOLVED'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ) AS withhold_unresolved,

        ROUND(
            SUM(
                CASE
                    WHEN bridge_disposition = 'REFERENCE_ONLY'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ) AS reference_only,

        ROUND(
            SUM(
                CASE
                    WHEN bridge_disposition = 'UNCLASSIFIED_REVIEW'
                        THEN federal_action_obligation
                    ELSE 0
                END
            ),
            2
        ) AS unclassified_review

    FROM bridge
)

SELECT
    bridge_total,
    include_additive,
    exclude_duplicate,
    withhold_unresolved,
    reference_only,
    unclassified_review,

    ROUND(
          include_additive
        + exclude_duplicate
        + withhold_unresolved
        + reference_only
        + unclassified_review,
        2
    ) AS reconstructed_total,

    ROUND(
        bridge_total
        -
        (
              include_additive
            + exclude_duplicate
            + withhold_unresolved
            + reference_only
            + unclassified_review
        ),
        2
    ) AS bridge_difference

FROM summary;


/* ============================================================================
   SECTION 6
   ANNUAL ACCOUNTING BRIDGE
   ========================================================================== */

\echo ''
\echo 'SECTION 6 — ANNUAL ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS gross_assistance,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS include_additive,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'EXCLUDE_DUPLICATE'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS exclude_duplicate,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'WITHHOLD_UNRESOLVED'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS withhold_unresolved,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'REFERENCE_ONLY'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS reference_only,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'UNCLASSIFIED_REVIEW'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS unclassified_review

FROM bridge

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/* ============================================================================
   SECTION 7
   ADDITIVE COVID / NON-COVID BRIDGE

   This is particularly important for eventual COVID-inclusive and
   COVID-excluded statewide reporting.
   ========================================================================== */

\echo ''
\echo 'SECTION 7 — ADDITIVE FUNDING DIMENSIONS'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_total,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                 AND is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_covid,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                 AND NOT is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_non_covid,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                 AND is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_iija,

    ROUND(
        SUM(
            CASE
                WHEN bridge_disposition = 'INCLUDE_ADDITIVE'
                 AND is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS additive_extraordinary

FROM bridge

GROUP BY action_date_fiscal_year
ORDER BY action_date_fiscal_year;


/* ============================================================================
   SECTION 8
   REMAINING UNCLASSIFIED REVIEW — PROGRAM MATERIALITY

   This is our principal next-work queue.
   ========================================================================== */

\echo ''
\echo 'SECTION 8 — REMAINING UNCLASSIFIED REVIEW BY PROGRAM'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    MAX(funding_agency_name) AS representative_funding_agency,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars

FROM bridge

WHERE bridge_disposition = 'UNCLASSIFIED_REVIEW'

GROUP BY cfda_number

ORDER BY obligation_dollars DESC
LIMIT 100;


/* ============================================================================
   SECTION 9
   REMAINING UNCLASSIFIED REVIEW — FUNDING AGENCY MATERIALITY
   ========================================================================== */

\echo ''
\echo 'SECTION 9 — REMAINING UNCLASSIFIED REVIEW BY FUNDING AGENCY'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    COALESCE(
        funding_agency_name,
        '[NULL FUNDING AGENCY]'
    ) AS funding_agency,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars

FROM bridge

WHERE bridge_disposition = 'UNCLASSIFIED_REVIEW'

GROUP BY funding_agency_name

ORDER BY obligation_dollars DESC;


/* ============================================================================
   SECTION 10
   TOP 50 UNCLASSIFIED AWARDS

   Helps determine whether the next materiality block can be classified at
   program level or requires award-specific treatment.
   ========================================================================== */

\echo ''
\echo 'SECTION 10 — TOP 50 REMAINING UNCLASSIFIED AWARDS'
\echo '----------------------------------------------------------------------------------------------------'

WITH universe AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                action_date_fiscal_year,
                assistance_transaction_id
        ) AS bridge_row_id,
        ledger.*
    FROM analysis.v_certified_assistance_ledger AS ledger
    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

candidate_matches AS (
    SELECT
        u.bridge_row_id,
        c.accounting_disposition,

        ROW_NUMBER() OVER (
            PARTITION BY u.bridge_row_id
            ORDER BY
                c.updated_at DESC,
                c.federal_inflow_award_classification_id DESC
        ) AS match_rank

    FROM universe AS u

    JOIN reference.federal_inflow_award_classification AS c
      ON c.source_system = 'USASPENDING_ASSISTANCE'
     AND c.source_program_code = u.cfda_number
     AND c.source_award_identifier = u.award_id_fain
     AND (
            c.valid_from_fiscal_year IS NULL
         OR u.action_date_fiscal_year >= c.valid_from_fiscal_year
     )
     AND (
            c.valid_through_fiscal_year IS NULL
         OR u.action_date_fiscal_year <= c.valid_through_fiscal_year
     )
),

selected AS (
    SELECT *
    FROM candidate_matches
    WHERE match_rank = 1
),

bridge AS (
    SELECT
        u.*,
        COALESCE(
            s.accounting_disposition,
            'UNCLASSIFIED_REVIEW'
        ) AS bridge_disposition
    FROM universe AS u
    LEFT JOIN selected AS s
      ON s.bridge_row_id = u.bridge_row_id
)

SELECT
    cfda_number,
    MAX(cfda_title) AS cfda_title,
    award_id_fain,
    MAX(recipient_name) AS recipient_name,
    MAX(funding_agency_name) AS funding_agency_name,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation),
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS covid_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS iija_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ),
        2
    ) AS extraordinary_dollars

FROM bridge

WHERE bridge_disposition = 'UNCLASSIFIED_REVIEW'

GROUP BY
    cfda_number,
    award_id_fain

ORDER BY obligation_dollars DESC
LIMIT 50;


/* ============================================================================
   SECTION 11
   FINAL CONTROL SUMMARY
   ========================================================================== */

\echo ''
\echo 'SECTION 11 — FINAL CONTROL SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    'EXPECTED_GROSS_ASSISTANCE' AS control_name,
    348524407674.34::numeric AS control_dollars

UNION ALL

SELECT
    'PERSISTED_93_777_INCLUDE_ADDITIVE',
    40775969.39::numeric

UNION ALL

SELECT
    'PERSISTED_93_775_791_796_WITHHOLD',
    353604119.65::numeric;


/* ============================================================================
   SECTION 12
   COMPLETION MARKER
   ========================================================================== */

\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5J PROFILE COMPLETE — NO DB WRITES'
\echo '===================================================================================================='