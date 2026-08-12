BEGIN;

-- ============================================================================
-- AP-002A SQL-001
-- Washington State Federal Assistance by Fiscal Year
--
-- Purpose:
--   Produce the certified statewide annual Assistance summary for
--   FY2020-FY2025.
--
-- Sources:
--   analysis.v_assistance_geographic_attribution
--   analysis.v_wa_funding_decomposition_reconciliation
--
-- Funding decomposition is mutually exclusive:
--   COVID
--   IIJA
--   OTHER_EXTRAORDINARY
--   ORDINARY
--
-- Geographic reconciliation preserves:
--   WA_COUNTY
--   WA_UNSPECIFIED
--   GEOGRAPHY_CONFLICT
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_statewide_assistance_by_year AS

WITH geography AS (
    SELECT
        fiscal_year,

        SUM(transaction_count)
            AS transaction_count,

        SUM(federal_action_obligation)
            AS total_obligation,

        SUM(
            CASE
                WHEN geographic_attribution_class = 'WA_COUNTY'
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS wa_county_obligation,

        SUM(
            CASE
                WHEN geographic_attribution_class = 'WA_UNSPECIFIED'
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS wa_unspecified_obligation,

        SUM(
            CASE
                WHEN geographic_attribution_class = 'GEOGRAPHY_CONFLICT'
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS geography_conflict_obligation

    FROM analysis.v_wa_obligation_reconciliation

    GROUP BY fiscal_year
),

funding AS (
    SELECT
        fiscal_year,

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
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS iija_obligation,

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
                THEN federal_action_obligation
                ELSE 0
            END
        ) AS ordinary_obligation

    FROM analysis.v_wa_funding_decomposition_reconciliation

    GROUP BY fiscal_year
)

SELECT
    g.fiscal_year,

    g.transaction_count,

    g.total_obligation,

    f.covid_obligation,

    g.total_obligation - f.covid_obligation
        AS covid_excluded_obligation,

    f.iija_obligation,

    f.other_extraordinary_obligation,

    f.ordinary_obligation,

    f.covid_obligation
        + f.iija_obligation
        + f.other_extraordinary_obligation
        AS total_extraordinary_obligation,

    g.wa_county_obligation,

    g.wa_unspecified_obligation,

    g.geography_conflict_obligation,

    ROUND(
        100.0 * f.covid_obligation
        / NULLIF(g.total_obligation, 0),
        2
    ) AS covid_percent,

    ROUND(
        100.0 * f.iija_obligation
        / NULLIF(g.total_obligation, 0),
        2
    ) AS iija_percent,

    ROUND(
        100.0
        * (
            f.covid_obligation
            + f.iija_obligation
            + f.other_extraordinary_obligation
          )
        / NULLIF(g.total_obligation, 0),
        2
    ) AS extraordinary_percent,

    ROUND(
        100.0 * g.wa_county_obligation
        / NULLIF(g.total_obligation, 0),
        2
    ) AS county_resolved_percent,

    ROUND(
        100.0 * g.wa_unspecified_obligation
        / NULLIF(g.total_obligation, 0),
        2
    ) AS wa_unspecified_percent

FROM geography g

JOIN funding f
  ON f.fiscal_year = g.fiscal_year

ORDER BY g.fiscal_year
;

COMMENT ON VIEW analysis.v_statewide_assistance_by_year IS
    'AP-002A certified annual Washington State Assistance summary for '
    'FY2020-FY2025, using mutually exclusive extraordinary-funding '
    'classification and explicit geographic reconciliation.';

COMMIT;