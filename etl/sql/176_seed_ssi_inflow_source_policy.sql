/* =====================================================================
   ETL-176
   ETL-174B-5B

   SEED SUPPLEMENTAL SECURITY INCOME (SSI)
   FEDERAL INFLOW SOURCE POLICY

   Purpose:
     Establish Assistance Listing 96.006 as the preferred WCFFBP
     accounting source for Supplemental Security Income benefits for
     the empirically reconciled FY2020-FY2024 period.

   Accounting finding:
     WCFFBP's existing SSA benefit-payment accounting path represents
     OASDI retirement, survivors, and disability benefits.

     Supplemental Security Income (SSI) is not represented in that
     existing OASDI ledger.

     USAspending Assistance Listing 96.006 therefore represents an
     economically distinct federal benefit stream and is additive to
     the principal Washington federal-inflow ledger for FY2020-FY2024.

   Certified ETL-174B-5B profile:
     Transactions                4,535
     Net federal obligations     $5,676,088,795.00
     COVID obligations           $0.00
     Recipient                   MULTIPLE RECIPIENTS
     Assistance type             Direct Payment With Unrestricted Use
     Description                 Aggregate Supplemental Security
                                 Income (SSI) Benefits

   IMPORTANT:
     This policy establishes FY2020-FY2024 only.

     It does NOT impute SSI values for FY2015-FY2019.

     COVID remains an independent funding characteristic.

   ===================================================================== */

BEGIN;


/* =====================================================================
   1. FAIL-CLOSED SCHEMA PRECONDITION
   ===================================================================== */

DO $$
DECLARE
    missing_columns TEXT;
BEGIN

    SELECT string_agg(required.column_name, ', ' ORDER BY required.column_name)
      INTO missing_columns

    FROM (
        VALUES
            ('inflow_family'),
            ('inflow_subfamily'),
            ('accounting_measure'),
            ('preferred_source'),
            ('allocation_source'),
            ('overlapping_sources'),
            ('ledger_treatment'),
            ('source_selection_basis'),
            ('methodology_version'),
            ('valid_from_fiscal_year'),
            ('valid_through_fiscal_year')
    ) AS required(column_name)

    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns actual
        WHERE actual.table_schema = 'reference'
          AND actual.table_name =
              'federal_inflow_source_policy'
          AND actual.column_name = required.column_name
    );

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION
            'ETL-176 expected reference.federal_inflow_source_policy columns are missing: %',
            missing_columns;
    END IF;

END
$$;


/* =====================================================================
   2. SEED SSI SOURCE POLICY
   ===================================================================== */

INSERT INTO reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)

SELECT
    'SOCIAL_SECURITY',
    'SUPPLEMENTAL_SECURITY_INCOME',
    'ANNUAL_SSI_BENEFIT_PAYMENTS',
    'USASPENDING_ASSISTANCE_96.006',
    'USASPENDING_ASSISTANCE_96.006',
    ARRAY[]::TEXT[],
    'INCLUDE',

    $basis$
WCFFBP no-double-counting accounting invariant: the same underlying federal
economic resource may appear in multiple federal reporting systems but may
enter the principal federal-inflow ledger only once.

WCFFBP's existing preferred Social Security benefit-payment accounting path
covers OASDI retirement, survivors, and disability benefits. Review of
reporting.v_washington_ssa_summary established that Supplemental Security
Income (SSI) is not included in that OASDI accounting stream.

ETL-174B-5B separately profiled USAspending Assistance Listing 96.006 for
Washington during FY2020-FY2024. The certified assistance ledger contains
4,535 observations with $5,676,088,795.00 in net federal action obligations.

All profiled observations identify Assistance Listing 96.006 as Supplemental
Security Income; Social Security Administration is both the awarding and
funding agency; the recipient is MULTIPLE RECIPIENTS; the assistance type is
Direct Payment With Unrestricted Use; and the canonical award and transaction
descriptions identify the observations as AGGREGATE SUPPLEMENTAL SECURITY
INCOME (SSI) BENEFITS.

No FY2020-FY2024 96.006 obligation carries the WCFFBP COVID funding
characteristic.

Because SSI is economically distinct from the OASDI benefit stream already
represented in the WCFFBP ledger, Assistance Listing 96.006 is additive for
the empirically reconciled FY2020-FY2024 period.

This policy does not authorize extrapolation or imputation of SSI amounts for
FY2015-FY2019. Those years require an independently documented source before
inclusion in the principal historical ledger.
$basis$,

    'ANALYSIS-174B-5B-SSI-v1',
    2020,
    2024

WHERE NOT EXISTS (

    SELECT 1
    FROM reference.federal_inflow_source_policy existing

    WHERE existing.inflow_family = 'SOCIAL_SECURITY'
      AND existing.inflow_subfamily =
          'SUPPLEMENTAL_SECURITY_INCOME'
      AND existing.methodology_version =
          'ANALYSIS-174B-5B-SSI-v1'
);


/* =====================================================================
   3. POLICY CERTIFICATION
   ===================================================================== */

DO $$
DECLARE
    policy_count INTEGER;
    policy_treatment TEXT;
    policy_start INTEGER;
    policy_end INTEGER;
BEGIN

    SELECT
        COUNT(*),
        MIN(ledger_treatment),
        MIN(valid_from_fiscal_year),
        MAX(valid_through_fiscal_year)

    INTO
        policy_count,
        policy_treatment,
        policy_start,
        policy_end

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'SOCIAL_SECURITY'
      AND inflow_subfamily = 'SUPPLEMENTAL_SECURITY_INCOME'
      AND methodology_version =
          'ANALYSIS-174B-5B-SSI-v1';


    IF policy_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-176 certification failed: expected exactly 1 SSI policy row, found %',
            policy_count;
    END IF;


    IF policy_treatment <> 'INCLUDE' THEN
    RAISE EXCEPTION
        'ETL-176 certification failed: expected INCLUDE, found %',
        policy_treatment;
    END IF;


    IF policy_start <> 2020
       OR policy_end <> 2024 THEN

        RAISE EXCEPTION
            'ETL-176 certification failed: expected FY2020-FY2024 validity, found FY%-FY%',
            policy_start,
            policy_end;
    END IF;

END
$$;


/* =====================================================================
   4. EMPIRICAL SOURCE CERTIFICATION
   ===================================================================== */

DO $$
DECLARE
    v_transaction_count BIGINT;
    v_obligation NUMERIC;
    v_covid_obligation NUMERIC;
    v_description_count BIGINT;
    v_recipient_count BIGINT;
BEGIN

    SELECT
        COUNT(*),

        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

        COALESCE(
            SUM(
                CASE
                    WHEN is_covid
                    THEN federal_action_obligation
                    ELSE 0
                END
            ),
            0
        ),

        COUNT(
            DISTINCT canonical_award_description
        ),

        COUNT(
            DISTINCT recipient_name
        )

    INTO
        v_transaction_count,
        v_obligation,
        v_covid_obligation,
        v_description_count,
        v_recipient_count

    FROM analysis.v_certified_assistance_ledger

    WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
      AND reference_state_abbreviation = 'WA'
      AND cfda_number = '96.006';


    IF v_transaction_count <> 4535 THEN
        RAISE EXCEPTION
            'ETL-176 source certification failed: expected 4535 SSI transactions, found %',
            v_transaction_count;
    END IF;


    IF ROUND(v_obligation, 2) <> 5676088795.00 THEN
        RAISE EXCEPTION
            'ETL-176 source certification failed: expected $5676088795.00, found $%',
            ROUND(v_obligation, 2);
    END IF;


    IF ROUND(v_covid_obligation, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-176 COVID certification failed: expected $0.00, found $%',
            ROUND(v_covid_obligation, 2);
    END IF;


    IF v_description_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-176 source certification failed: expected one SSI canonical description, found %',
            v_description_count;
    END IF;


    IF v_recipient_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-176 source certification failed: expected one aggregate SSI recipient representation, found %',
            v_recipient_count;
    END IF;


    RAISE NOTICE
       'ETL-176 PASS: SSI 96.006 certified INCLUDE for FY2020-FY2024; 4535 transactions; $% net obligations; $% COVID.',
        ROUND(v_obligation, 2),
        ROUND(v_covid_obligation, 2);

END
$$;


COMMIT;


/* =====================================================================
   5. POST-MIGRATION INSPECTION
   ===================================================================== */

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year,
    source_selection_basis

FROM reference.federal_inflow_source_policy

WHERE inflow_family = 'SOCIAL_SECURITY'
  AND inflow_subfamily = 'SUPPLEMENTAL_SECURITY_INCOME'
  AND methodology_version =
      'ANALYSIS-174B-5B-SSI-v1';