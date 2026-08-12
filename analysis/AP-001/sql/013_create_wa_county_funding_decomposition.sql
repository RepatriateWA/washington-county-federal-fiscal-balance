BEGIN;

-- ============================================================================
-- AP-001B.3 — Washington County Exclusive Funding Decomposition
-- File: analysis/AP-001/sql/013_create_wa_county_funding_decomposition.sql
--
-- Source:
--   analysis.v_wa_county_transactions
--
-- Grain:
--   One row per fiscal year x Washington county x exclusive funding class.
--
-- Exclusive class precedence:
--   1. COVID
--   2. IIJA
--   3. OTHER_EXTRAORDINARY
--   4. ORDINARY
--
-- Rationale:
--   Independent transaction flags such as is_covid and is_iija may overlap.
--   They remain available upstream for thematic analysis, but they cannot be
--   added together safely. This view creates a mutually exclusive class for
--   additive reporting and stacked decompositions.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_county_funding_decomposition AS

WITH classified AS (
    SELECT
        t.*,

        CASE
            WHEN t.is_covid
                THEN 'COVID'

            WHEN t.is_iija
                THEN 'IIJA'

            WHEN t.is_extraordinary
                THEN 'OTHER_EXTRAORDINARY'

            ELSE 'ORDINARY'
        END AS exclusive_funding_class

    FROM analysis.v_wa_county_transactions t
)

SELECT
    action_date_fiscal_year AS fiscal_year,

    reference_county_id AS county_id,
    county_full_fips,
    reference_county_name AS county_name,

    exclusive_funding_class,

    COUNT(*) AS transaction_count,

    SUM(federal_action_obligation)
        AS federal_action_obligation

FROM classified

GROUP BY
    action_date_fiscal_year,
    reference_county_id,
    county_full_fips,
    reference_county_name,
    exclusive_funding_class
;

COMMENT ON VIEW analysis.v_wa_county_funding_decomposition IS
    'AP-001B.3 certified mutually exclusive Washington county funding '
    'decomposition. Classes use precedence COVID > IIJA > '
    'OTHER_EXTRAORDINARY > ORDINARY so additive totals reconcile exactly.';


-- ============================================================================
-- County-year wide form for reporting.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_county_funding_decomposition_wide AS
SELECT
    fiscal_year,
    county_id,
    county_full_fips,
    county_name,

    SUM(transaction_count)
        AS transaction_count,

    SUM(federal_action_obligation)
        AS federal_action_obligation,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'COVID'
            THEN transaction_count
            ELSE 0
        END
    ) AS covid_transaction_count,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'COVID'
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS covid_obligation,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'IIJA'
            THEN transaction_count
            ELSE 0
        END
    ) AS iija_transaction_count,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'IIJA'
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS iija_obligation,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'OTHER_EXTRAORDINARY'
            THEN transaction_count
            ELSE 0
        END
    ) AS other_extraordinary_transaction_count,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'OTHER_EXTRAORDINARY'
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS other_extraordinary_obligation,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'ORDINARY'
            THEN transaction_count
            ELSE 0
        END
    ) AS ordinary_transaction_count,

    SUM(
        CASE
            WHEN exclusive_funding_class = 'ORDINARY'
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS ordinary_obligation

FROM analysis.v_wa_county_funding_decomposition

GROUP BY
    fiscal_year,
    county_id,
    county_full_fips,
    county_name
;

COMMENT ON VIEW analysis.v_wa_county_funding_decomposition_wide IS
    'AP-001B.3 reporting-oriented county-year wide decomposition using '
    'mutually exclusive funding classes. Component obligations sum exactly '
    'to total federal_action_obligation.';


-- ============================================================================
-- Statewide exclusive decomposition including WA_UNSPECIFIED and conflicts.
-- This keeps county-resolved reporting separate from complete statewide
-- reconciliation.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_funding_decomposition_reconciliation AS

WITH classified AS (
    SELECT
        t.*,

        CASE
            WHEN t.is_covid
                THEN 'COVID'

            WHEN t.is_iija
                THEN 'IIJA'

            WHEN t.is_extraordinary
                THEN 'OTHER_EXTRAORDINARY'

            ELSE 'ORDINARY'
        END AS exclusive_funding_class

    FROM analysis.v_assistance_geographic_attribution t

    WHERE t.geographic_attribution_class IN (
        'WA_COUNTY',
        'WA_UNSPECIFIED',
        'GEOGRAPHY_CONFLICT'
    )
)

SELECT
    action_date_fiscal_year AS fiscal_year,
    geographic_attribution_class,
    exclusive_funding_class,

    COUNT(*) AS transaction_count,

    SUM(federal_action_obligation)
        AS federal_action_obligation

FROM classified

GROUP BY
    action_date_fiscal_year,
    geographic_attribution_class,
    exclusive_funding_class
;

COMMENT ON VIEW analysis.v_wa_funding_decomposition_reconciliation IS
    'AP-001B.3 statewide reconciliation of mutually exclusive funding '
    'classes by geographic attribution class. Preserves WA_UNSPECIFIED '
    'and GEOGRAPHY_CONFLICT separately from county-resolved totals.';

COMMIT;