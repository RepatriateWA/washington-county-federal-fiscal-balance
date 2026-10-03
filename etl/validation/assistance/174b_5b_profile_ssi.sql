/* =====================================================================
   ETL-174B-5B
   SUPPLEMENTAL SECURITY INCOME — AL 96.006
   RECONCILIATION PROFILE

   READ ONLY
   NO DATABASE WRITES

   Purpose:
     Profile Washington USAspending Assistance Listing 96.006 before
     determining whether it represents an additive federal inflow.

   Established fact:
     reporting.v_washington_ssa_summary contains OASDI programs but does
     not contain SSI.

   This query does NOT make the additive accounting decision.
   ===================================================================== */


/* ---------------------------------------------------------------------
   A. ANNUAL CONTROL
   --------------------------------------------------------------------- */

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT award_id_uri)
        AS distinct_uri_count,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


/* ---------------------------------------------------------------------
   B. STRUCTURAL PROFILE
   --------------------------------------------------------------------- */

SELECT
    cfda_number,
    cfda_title,

    recipient_name,
    recipient_type_code,

    assistance_type_code,
    assistance_type_description,

    awarding_agency_name,
    awarding_subagency_name,

    funding_agency_name,
    funding_subagency_name,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_dollars,

    MIN(action_date) AS first_action_date,
    MAX(action_date) AS last_action_date

FROM analysis.v_certified_assistance_ledger

WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006'

GROUP BY
    cfda_number,
    cfda_title,
    recipient_name,
    recipient_type_code,
    assistance_type_code,
    assistance_type_description,
    awarding_agency_name,
    awarding_subagency_name,
    funding_agency_name,
    funding_subagency_name

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC;


/* ---------------------------------------------------------------------
   C. DESCRIPTION PROFILE

   Group rather than emit all 4,535 transactions.
   --------------------------------------------------------------------- */

SELECT
    canonical_award_description,
    transaction_description,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_dollars,

    MIN(action_date_fiscal_year)
        AS first_fiscal_year,

    MAX(action_date_fiscal_year)
        AS last_fiscal_year

FROM analysis.v_certified_assistance_ledger

WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006'

GROUP BY
    canonical_award_description,
    transaction_description

ORDER BY
    ABS(SUM(federal_action_obligation)) DESC;


/* ---------------------------------------------------------------------
   D. OVERALL CONTROL
   --------------------------------------------------------------------- */

SELECT
    COUNT(*) AS transaction_count,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT award_id_uri)
        AS distinct_uri_count,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger

WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '96.006';