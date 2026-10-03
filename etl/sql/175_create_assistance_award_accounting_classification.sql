/* =====================================================================
   ETL-175
   ETL-174B-4D

   CREATE ASSISTANCE AWARD ACCOUNTING CLASSIFICATION
   AND SEED WASHINGTON CHIP 93.767 RECONCILIATION

   Purpose:
     Create a durable award-level accounting-classification layer for
     USAspending assistance programs that cannot safely be classified
     solely at the Assistance Listing level.

   Initial use case:
     Assistance Listing 93.767
     Children's Health Insurance Program (CHIP)

   Empirical finding:
     Washington FY2020-FY2024 AL 93.767 contains two economically
     different award families:

       1. Washington State T21 entitlement financing
          -> overlaps CMS-native CHIP accounting
          -> EXCLUDE_DUPLICATE

       2. Healthy Kids Together
          FAIN 1Y1CMS331701
          -> structurally distinct from state T21 entitlement financing
          -> WITHHOLD_UNRESOLVED pending affirmative additive review

   IMPORTANT:
     This migration does NOT classify AL 93.767 wholesale.

     Accounting disposition and COVID/extraordinary funding
     characteristics remain independent dimensions.

   This migration:
     * creates reference.federal_inflow_award_classification
     * seeds seven observed Washington AL 93.767 FAINs
     * validates the classification against the certified assistance ledger
     * requires exact FY2020-FY2024 bridge closure

   It does NOT:
     * alter source transactions
     * alter CMS CHIP controls
     * alter existing source-policy rows
     * create final federal-inflow totals
   ===================================================================== */

BEGIN;


/* =====================================================================
   1. CREATE DURABLE AWARD-LEVEL CLASSIFICATION TABLE
   ===================================================================== */

CREATE TABLE IF NOT EXISTS reference.federal_inflow_award_classification (
    federal_inflow_award_classification_id BIGSERIAL PRIMARY KEY,

    source_system TEXT NOT NULL,
    source_program_code TEXT NOT NULL,
    source_award_identifier TEXT NOT NULL,

    inflow_family TEXT NOT NULL,
    inflow_subfamily TEXT NOT NULL,

    accounting_disposition TEXT NOT NULL,

    classification_basis TEXT NOT NULL,
    methodology_version TEXT NOT NULL,

    valid_from_fiscal_year INTEGER,
    valid_through_fiscal_year INTEGER,

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_federal_inflow_award_classification
        UNIQUE (
            source_system,
            source_program_code,
            source_award_identifier,
            methodology_version
        ),

    CONSTRAINT ck_federal_inflow_award_accounting_disposition
        CHECK (
            accounting_disposition IN (
                'INCLUDE_ADDITIVE',
                'EXCLUDE_DUPLICATE',
                'WITHHOLD_UNRESOLVED',
                'REFERENCE_ONLY'
            )
        ),

    CONSTRAINT ck_federal_inflow_award_fiscal_year_range
        CHECK (
            valid_from_fiscal_year IS NULL
            OR valid_through_fiscal_year IS NULL
            OR valid_from_fiscal_year <= valid_through_fiscal_year
        )
);


/* =====================================================================
   2. INDEXES
   ===================================================================== */

CREATE INDEX IF NOT EXISTS
    idx_federal_inflow_award_classification_program
ON reference.federal_inflow_award_classification (
    source_system,
    source_program_code
);


CREATE INDEX IF NOT EXISTS
    idx_federal_inflow_award_classification_award
ON reference.federal_inflow_award_classification (
    source_award_identifier
);


CREATE INDEX IF NOT EXISTS
    idx_federal_inflow_award_classification_disposition
ON reference.federal_inflow_award_classification (
    accounting_disposition
);


/* =====================================================================
   3. SEED SIX CORE WASHINGTON CHIP / T21 FAINs
   ===================================================================== */

INSERT INTO reference.federal_inflow_award_classification (
    source_system,
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    '93.767',
    source_award_identifier,
    'CHIP',
    'CORE_STATE_T21_FINANCING',
    'EXCLUDE_DUPLICATE',
    $basis$
ETL-174B-4C transaction-level reconciliation established that this FAIN
represents Washington State T21 entitlement financing under Assistance
Listing 93.767.

The certified USAspending observations are awarded to the Washington
Department of Social & Health Services and carry transaction/award
descriptions identifying Medicaid Entitlement / T21 financing. These
transactions represent the core state CHIP financing stream for which
WCFFBP independently maintains a CMS-native Washington CHIP federal
expenditure control.

The USAspending federal_action_obligation measure is not expected to equal
the CMS expenditure/payment measure dollar-for-dollar by fiscal year.
EXCLUDE_DUPLICATE reflects economic/program-stream overlap rather than
numerical equality between accounting systems.

The USAspending observations remain preserved for reconciliation,
provenance, audit, and funding-characteristic analysis. Their exclusion
from the additive assistance path does not delete or alter the underlying
source observations.
$basis$,
    'ANALYSIS-174B-4D-CHIP-v1',
    2020,
    2024
FROM (
    VALUES
        ('2005WA5021'),
        ('2105WA5021'),
        ('2205WA5021'),
        ('2305WA3002'),
        ('2305WA5021'),
        ('2405WA5021')
) AS core_chip(source_award_identifier)

WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_award_classification existing
    WHERE existing.source_system = 'USASPENDING_ASSISTANCE'
      AND existing.source_program_code = '93.767'
      AND existing.source_award_identifier =
          core_chip.source_award_identifier
      AND existing.methodology_version =
          'ANALYSIS-174B-4D-CHIP-v1'
);


/* =====================================================================
   4. SEED HEALTHY KIDS TOGETHER AS UNRESOLVED
   ===================================================================== */

INSERT INTO reference.federal_inflow_award_classification (
    source_system,
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    '93.767',
    '1Y1CMS331701',
    'CHIP',
    'HEALTHY_KIDS_TOGETHER',
    'WITHHOLD_UNRESOLVED',
    $basis$
ETL-174B-4C transaction-level reconciliation established that FAIN
1Y1CMS331701 is structurally distinct from Washington State T21 entitlement
financing recorded elsewhere under Assistance Listing 93.767.

The award recipient is Better Health Together and the award/transaction
description is Healthy Kids Together. The observed transactions include
formula-grant/cooperative-agreement records rather than the Washington
Department of Social & Health Services T21 entitlement award pattern.

For FY2020-FY2024, the certified USAspending ledger contains net federal
action obligations of $509,691.78 for this FAIN:

    +$349,103.00
    +$350,257.00
    -$189,668.22
    plus zero-dollar modifications
    = $509,691.78 net

No observed obligation for this FAIN is WCFFBP COVID-tagged.

The transaction evidence is sufficient to establish that this award should
NOT be automatically removed as part of the core state CHIP overlap.

The evidence is not, by itself, sufficient to certify the award as an
independent additive federal inflow. It therefore remains
WITHHOLD_UNRESOLVED pending affirmative confirmation that its economic
payment stream is not represented elsewhere in a preferred WCFFBP
accounting source.
$basis$,
    'ANALYSIS-174B-4D-CHIP-v1',
    2020,
    2024
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.federal_inflow_award_classification existing
    WHERE existing.source_system = 'USASPENDING_ASSISTANCE'
      AND existing.source_program_code = '93.767'
      AND existing.source_award_identifier = '1Y1CMS331701'
      AND existing.methodology_version =
          'ANALYSIS-174B-4D-CHIP-v1'
);


/* =====================================================================
   5. STRUCTURAL CERTIFICATION
   ===================================================================== */

DO $$
DECLARE
    classification_count INTEGER;
    duplicate_count INTEGER;
    unresolved_count INTEGER;
BEGIN

    SELECT COUNT(*)
      INTO classification_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND methodology_version = 'ANALYSIS-174B-4D-CHIP-v1';

    IF classification_count <> 7 THEN
        RAISE EXCEPTION
            'ETL-175 certification failed: expected 7 CHIP award classifications, found %',
            classification_count;
    END IF;


    SELECT COUNT(*)
      INTO duplicate_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND methodology_version = 'ANALYSIS-174B-4D-CHIP-v1'
      AND accounting_disposition = 'EXCLUDE_DUPLICATE';

    IF duplicate_count <> 6 THEN
        RAISE EXCEPTION
            'ETL-175 certification failed: expected 6 EXCLUDE_DUPLICATE CHIP FAINs, found %',
            duplicate_count;
    END IF;


    SELECT COUNT(*)
      INTO unresolved_count
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.767'
      AND methodology_version = 'ANALYSIS-174B-4D-CHIP-v1'
      AND accounting_disposition = 'WITHHOLD_UNRESOLVED';

    IF unresolved_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-175 certification failed: expected 1 WITHHOLD_UNRESOLVED CHIP FAIN, found %',
            unresolved_count;
    END IF;

END
$$;


/* =====================================================================
   6. EMPIRICAL RECONCILIATION AGAINST CERTIFIED ASSISTANCE LEDGER

   Required controls:

     total transactions       = 21
     gross/net AL 93.767      = $1,277,001,919.78

     EXCLUDE_DUPLICATE        = $1,276,492,228.00
     WITHHOLD_UNRESOLVED      =       $509,691.78

     bridge difference        = $0.00
   ===================================================================== */

DO $$
DECLARE
    v_transaction_count BIGINT;

    v_gross NUMERIC;
    v_duplicate NUMERIC;
    v_unresolved NUMERIC;
    v_unclassified NUMERIC;
    v_bridge_difference NUMERIC;

    v_distinct_fain_count BIGINT;
BEGIN

    WITH chip AS (
        SELECT
            l.assistance_transaction_id,
            l.award_id_fain,
            l.federal_action_obligation,

            c.accounting_disposition

        FROM analysis.v_certified_assistance_ledger l

        LEFT JOIN reference.federal_inflow_award_classification c
          ON c.source_system = 'USASPENDING_ASSISTANCE'
         AND c.source_program_code = l.cfda_number
         AND c.source_award_identifier = l.award_id_fain
         AND c.methodology_version =
             'ANALYSIS-174B-4D-CHIP-v1'

        WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
          AND l.reference_state_abbreviation = 'WA'
          AND l.cfda_number = '93.767'
    )

    SELECT
        COUNT(*),
        COUNT(DISTINCT award_id_fain),

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'EXCLUDE_DUPLICATE'
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'WITHHOLD_UNRESOLVED'
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition IS NULL
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_transaction_count,
        v_distinct_fain_count,
        v_gross,
        v_duplicate,
        v_unresolved,
        v_unclassified

    FROM chip;


    v_bridge_difference :=
        v_gross
        - v_duplicate
        - v_unresolved
        - v_unclassified;


    IF v_transaction_count <> 21 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: expected 21 transactions, found %',
            v_transaction_count;
    END IF;


    IF v_distinct_fain_count <> 7 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: expected 7 distinct FAINs, found %',
            v_distinct_fain_count;
    END IF;


    IF ROUND(v_gross, 2) <> 1277001919.78 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: gross 93.767 obligation expected 1277001919.78, found %',
            v_gross;
    END IF;


    IF ROUND(v_duplicate, 2) <> 1276492228.00 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: duplicate obligation expected 1276492228.00, found %',
            v_duplicate;
    END IF;


    IF ROUND(v_unresolved, 2) <> 509691.78 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: unresolved obligation expected 509691.78, found %',
            v_unresolved;
    END IF;


    IF ROUND(v_unclassified, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: unclassified CHIP obligation expected 0.00, found %',
            v_unclassified;
    END IF;


    IF ROUND(v_bridge_difference, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-175 empirical certification failed: bridge difference expected 0.00, found %',
            v_bridge_difference;
    END IF;


    RAISE NOTICE
        'ETL-175 PASS: CHIP 93.767 = 21 transactions / 7 FAINs / $% gross; $% EXCLUDE_DUPLICATE; $% WITHHOLD_UNRESOLVED; $% unclassified; $% bridge difference.',
        ROUND(v_gross, 2),
        ROUND(v_duplicate, 2),
        ROUND(v_unresolved, 2),
        ROUND(v_unclassified, 2),
        ROUND(v_bridge_difference, 2);

END
$$;


/* =====================================================================
   7. COVID INVARIANT

   All observed FY2020-FY2024 93.767 obligations were non-COVID.
   Accounting classification must not alter that funding characteristic.
   ===================================================================== */

DO $$
DECLARE
    v_covid_obligation NUMERIC;
BEGIN

    SELECT COALESCE(
               SUM(
                   CASE
                       WHEN is_covid
                       THEN federal_action_obligation
                       ELSE 0
                   END
               ),
               0
           )
      INTO v_covid_obligation

    FROM analysis.v_certified_assistance_ledger

    WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
      AND reference_state_abbreviation = 'WA'
      AND cfda_number = '93.767';


    IF ROUND(v_covid_obligation, 2) <> 0.00 THEN
        RAISE EXCEPTION
            'ETL-175 COVID certification failed: expected 0.00 COVID obligation, found %',
            v_covid_obligation;
    END IF;


    RAISE NOTICE
        'ETL-175 COVID PASS: FY2020-FY2024 AL 93.767 COVID obligation = $0.00.';

END
$$;


COMMIT;


/* =====================================================================
   8. POST-MIGRATION INSPECTION
   ===================================================================== */

SELECT
    source_program_code,
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_award_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '93.767'
  AND methodology_version = 'ANALYSIS-174B-4D-CHIP-v1'

ORDER BY
    accounting_disposition,
    source_award_identifier;


/* =====================================================================
   9. POST-MIGRATION ACCOUNTING BRIDGE
   ===================================================================== */

SELECT
    COALESCE(
        c.accounting_disposition,
        'UNCLASSIFIED'
    ) AS accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT l.award_id_fain)
        AS distinct_fain_count,

    ROUND(
        SUM(l.federal_action_obligation)::numeric,
        2
    ) AS obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN l.is_covid
                THEN l.federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_obligation_dollars

FROM analysis.v_certified_assistance_ledger l

LEFT JOIN reference.federal_inflow_award_classification c
  ON c.source_system = 'USASPENDING_ASSISTANCE'
 AND c.source_program_code = l.cfda_number
 AND c.source_award_identifier = l.award_id_fain
 AND c.methodology_version = 'ANALYSIS-174B-4D-CHIP-v1'

WHERE l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND l.reference_state_abbreviation = 'WA'
  AND l.cfda_number = '93.767'

GROUP BY
    COALESCE(
        c.accounting_disposition,
        'UNCLASSIFIED'
    )

ORDER BY
    accounting_disposition;