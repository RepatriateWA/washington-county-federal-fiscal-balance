BEGIN;

-- ============================================================================
-- AP-001B.2 — Washington County Obligation Measurements
-- File: analysis/AP-001/sql/012_create_wa_county_obligations.sql
--
-- Source:
--   analysis.v_wa_county_transactions
--
-- Grain:
--   One row per fiscal year x Washington county.
--
-- Fiscal measure:
--   SUM(federal_action_obligation)
--
-- Extraordinary-funding treatment:
--   COVID, IIJA, and other extraordinary categories are transaction-level
--   classifications inherited from the certified AP-001A ledger.
--
-- Important:
--   WA_UNSPECIFIED transactions are intentionally excluded from county rows.
--   A separate reconciliation view preserves WA_UNSPECIFIED and geography
--   conflicts so statewide totals remain fully auditable.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_county_obligations AS
SELECT
    t.action_date_fiscal_year AS fiscal_year,

    t.reference_county_id AS county_id,
    t.county_full_fips,
    t.reference_county_name AS county_name,

    COUNT(*) AS transaction_count,

    SUM(t.federal_action_obligation)
        AS federal_action_obligation,

    SUM(
        CASE
            WHEN t.is_covid
            THEN t.federal_action_obligation
            ELSE 0
        END
    ) AS covid_obligation,

    SUM(
        CASE
            WHEN NOT t.is_covid
            THEN t.federal_action_obligation
            ELSE 0
        END
    ) AS covid_excluded_obligation,

    SUM(
        CASE
            WHEN t.is_iija
            THEN t.federal_action_obligation
            ELSE 0
        END
    ) AS iija_obligation,

    SUM(
        CASE
            WHEN t.is_extraordinary
             AND NOT t.is_covid
             AND NOT t.is_iija
            THEN t.federal_action_obligation
            ELSE 0
        END
    ) AS other_extraordinary_obligation,

    SUM(
        CASE
            WHEN NOT t.is_extraordinary
            THEN t.federal_action_obligation
            ELSE 0
        END
    ) AS ordinary_obligation,

    COUNT(*) FILTER (WHERE t.is_covid)
        AS covid_transaction_count,

    COUNT(*) FILTER (WHERE t.is_iija)
        AS iija_transaction_count,

    COUNT(*) FILTER (
        WHERE t.is_extraordinary
          AND NOT t.is_covid
          AND NOT t.is_iija
    ) AS other_extraordinary_transaction_count,

    COUNT(*) FILTER (WHERE NOT t.is_extraordinary)
        AS ordinary_transaction_count

FROM analysis.v_wa_county_transactions t

GROUP BY
    t.action_date_fiscal_year,
    t.reference_county_id,
    t.county_full_fips,
    t.reference_county_name
;

COMMENT ON VIEW analysis.v_wa_county_obligations IS
    'AP-001B.2 certified county-year Washington Assistance obligation view. '
    'One row per fiscal year and Washington county. WA_UNSPECIFIED and '
    'geography-conflict transactions are excluded from county rows and '
    'preserved in the reconciliation view.';


-- ============================================================================
-- Statewide reconciliation by fiscal year and geographic attribution class.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_obligation_reconciliation AS
SELECT
    action_date_fiscal_year AS fiscal_year,
    geographic_attribution_class,

    COUNT(*) AS transaction_count,

    SUM(federal_action_obligation)
        AS federal_action_obligation,

    SUM(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS covid_obligation,

    SUM(
        CASE
            WHEN NOT is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS covid_excluded_obligation,

    SUM(
        CASE
            WHEN is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS iija_obligation,

    SUM(
        CASE
            WHEN is_extraordinary
             AND NOT is_covid
             AND NOT is_iija
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS other_extraordinary_obligation,

    SUM(
        CASE
            WHEN NOT is_extraordinary
            THEN federal_action_obligation
            ELSE 0
        END
    ) AS ordinary_obligation

FROM analysis.v_assistance_geographic_attribution

WHERE geographic_attribution_class IN (
    'WA_COUNTY',
    'WA_UNSPECIFIED',
    'GEOGRAPHY_CONFLICT'
)

GROUP BY
    action_date_fiscal_year,
    geographic_attribution_class
;

COMMENT ON VIEW analysis.v_wa_obligation_reconciliation IS
    'AP-001B.2 fiscal-year reconciliation of Washington county-resolved, '
    'Washington-unspecified, and geography-conflict Assistance obligations.';


-- ============================================================================
-- County total across all certified fiscal years.
-- ============================================================================

CREATE OR REPLACE VIEW analysis.v_wa_county_obligations_all_years AS
SELECT
    county_id,
    county_full_fips,
    county_name,

    SUM(transaction_count)
        AS transaction_count,

    SUM(federal_action_obligation)
        AS federal_action_obligation,

    SUM(covid_obligation)
        AS covid_obligation,

    SUM(covid_excluded_obligation)
        AS covid_excluded_obligation,

    SUM(iija_obligation)
        AS iija_obligation,

    SUM(other_extraordinary_obligation)
        AS other_extraordinary_obligation,

    SUM(ordinary_obligation)
        AS ordinary_obligation

FROM analysis.v_wa_county_obligations

GROUP BY
    county_id,
    county_full_fips,
    county_name
;

COMMENT ON VIEW analysis.v_wa_county_obligations_all_years IS
    'AP-001B.2 certified all-years Washington county Assistance obligation '
    'summary derived from v_wa_county_obligations.';

COMMIT;