/*
================================================================================
MIGRATION 184
SEED HUD HOUSING CHOICE VOUCHER ASSISTANCE ACCOUNTING POLICY
================================================================================

ETL branch
----------
ETL-174B-5Y

Methodology version
-------------------
ANALYSIS-174B-5Y-v1

Program
-------
14.871  Housing Choice Voucher Program

Purpose
-------
Persist the statewide accounting policy for Assistance Listing 14.871 after
completion of:

    ETL-174B-5Y
    ETL-174B-5Y-1
    ETL-174B-5Y-2A
    ETL-174B-5Y-2B
    ETL-174B-5Y-2C
    ETL-174B-5Y-2C.1
    ETL-174B-5Y-2D-1
    ETL-174B-5Y-2D-2
    ETL-174B-5Y-2D-3

Accounting conclusion
---------------------
Assistance Listing 14.871 represents genuine federal housing-assistance
inflow to Washington.

Disposition:
    INCLUDE_ADDITIVE

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Preferred accounting source:
    USASPENDING_ASSISTANCE

HUD Voucher Management System (VMS):
    VALIDATION / RECONCILIATION EVIDENCE ONLY.

HUD VMS HAP Total measures reported Housing Assistance Payment expenditure/use
at the PHA level. It is not added independently to USAspending AL 14.871
obligations.

The completed VMS reconciliation established that USAspending obligations and
VMS HAP Total represent materially different accounting stages and temporal
patterns. Exact reconciliation between those measures is therefore not
required for statewide ledger inclusion.

COVID / extraordinary funding:
    PROVENANCE ONLY.

COVID and extraordinary status do not change the underlying additive
classification. Those dimensions remain separately identifiable so that
ordinary, COVID-inclusive, COVID-excluded, and other analytical views can be
constructed.

County incidence:
    DEFERRED.

PHA administrative/headquarters geography is not certified as beneficiary or
economic-incidence geography. This migration makes no county allocation
decision.

Certified pre-migration focal controls
--------------------------------------
Transactions       5,248
Awards             5,088
Recipients            30

Net obligations:
    $4,308,080,637.65

Fiscal-year controls:
    FY2020   $722,577,370.00
    FY2021   $785,519,054.00
    FY2022   $802,217,748.00
    FY2023   $990,811,243.74
    FY2024 $1,006,955,221.91
             ----------------
    Total  $4,308,080,637.65

COVID and extraordinary classifications are preserved but are not used as
hard-coded migration gates here. Their accounting disposition remains
INCLUDE_ADDITIVE; they are provenance dimensions rather than separate
additive pathways.

Expected post-migration assistance bridge effect
------------------------------------------------
Prior INCLUDE_ADDITIVE:
    $51,497,106,903.04

14.871 increment:
     $4,308,080,637.65

Expected INCLUDE_ADDITIVE:
    $55,805,187,540.69

Prior UNCLASSIFIED_REVIEW:
    $61,504,044,044.56

14.871 decrement:
     $4,308,080,637.65

Expected UNCLASSIFIED_REVIEW:
    $57,195,963,406.91

Migration behavior
------------------
FAIL CLOSED.

The migration:
1. verifies the certified AL 14.871 source population;
2. verifies exact FY2020-FY2024 controls;
3. verifies 14.871 remains unresolved;
4. refuses to overwrite existing classifications or mappings;
5. inserts one source policy;
6. inserts one program classification;
7. inserts one program-policy mapping;
8. reconstructs effective assistance disposition;
9. verifies the exact post-migration bridge;
10. commits only if all controls pass.

NO:
    county allocation,
    VMS addition,
    separate COVID addition,
    separate extraordinary-funding addition.

================================================================================
*/

BEGIN;

\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 184 - HUD HOUSING CHOICE VOUCHER ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo 'Methodology: ANALYSIS-174B-5Y-v1'
\echo ''


-- ================================================================================================
-- 1. MATERIALIZE CERTIFIED WA ASSISTANCE UNIVERSE
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m184_ledger;

CREATE TEMP TABLE m184_ledger AS
SELECT
    assistance_transaction_id,
    action_date_fiscal_year,
    federal_action_obligation,
    cfda_number,
    cfda_title,
    award_id_fain,
    award_id_uri,
    recipient_name,
    funding_agency_name,
    defc_codes,
    funding_families,
    is_covid,
    is_iija,
    is_extraordinary,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier

FROM analysis.v_certified_assistance_ledger

WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024;


CREATE INDEX ON m184_ledger (cfda_number);
CREATE INDEX ON m184_ledger (source_award_identifier);
CREATE INDEX ON m184_ledger (action_date_fiscal_year);


-- ================================================================================================
-- 2. CERTIFIED AL 14.871 SOURCE POPULATION
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m184_focal;

CREATE TEMP TABLE m184_focal AS
SELECT *
FROM m184_ledger
WHERE cfda_number = '14.871';


\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION AL 14.871 SOURCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,
    COUNT(DISTINCT recipient_name) AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m184_focal;


DO $$
DECLARE
    v_transactions bigint;
    v_awards       bigint;
    v_recipients   bigint;
    v_total        numeric;
BEGIN
    SELECT
        COUNT(*),
        COUNT(DISTINCT source_award_identifier),
        COUNT(DISTINCT recipient_name),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_transactions,
        v_awards,
        v_recipients,
        v_total

    FROM m184_focal;

    IF v_transactions <> 5248
       OR v_awards <> 5088
       OR v_recipients <> 30
       OR ABS(
            v_total
            - 4308080637.65::numeric
       ) > 0.01
    THEN
        RAISE EXCEPTION
            'M184 SOURCE CONTROL FAILED: tx=% awards=% recipients=% total=%',
            v_transactions,
            v_awards,
            v_recipients,
            v_total;
    END IF;

    RAISE NOTICE
        'M184 SOURCE CONTROL PASS: tx=% awards=% recipients=% total=%',
        v_transactions,
        v_awards,
        v_recipients,
        v_total;
END
$$;


-- ================================================================================================
-- 3. FISCAL-YEAR CONTROLS
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. AL 14.871 FISCAL-YEAR CONTROLS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m184_focal

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


DO $$
DECLARE
    v_2020 numeric;
    v_2021 numeric;
    v_2022 numeric;
    v_2023 numeric;
    v_2024 numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE action_date_fiscal_year = 2020
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE action_date_fiscal_year = 2021
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE action_date_fiscal_year = 2022
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE action_date_fiscal_year = 2023
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE action_date_fiscal_year = 2024
            ),
            0
        )

    INTO
        v_2020,
        v_2021,
        v_2022,
        v_2023,
        v_2024

    FROM m184_focal;

    IF ABS(v_2020 - 722577370.00::numeric) > 0.01
       OR ABS(v_2021 - 785519054.00::numeric) > 0.01
       OR ABS(v_2022 - 802217748.00::numeric) > 0.01
       OR ABS(v_2023 - 990811243.74::numeric) > 0.01
       OR ABS(v_2024 - 1006955221.91::numeric) > 0.01
    THEN
        RAISE EXCEPTION
            'M184 FY CONTROL FAILED: FY2020=% FY2021=% FY2022=% FY2023=% FY2024=%',
            v_2020,
            v_2021,
            v_2022,
            v_2023,
            v_2024;
    END IF;

    RAISE NOTICE
        'M184 FISCAL-YEAR CONTROL PASS';
END
$$;


-- ================================================================================================
-- 4. PRE-MIGRATION UNRESOLVED CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PRE-MIGRATION UNRESOLVED CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_program_classifications bigint;
    v_award_classifications   bigint;
    v_program_mappings        bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_program_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';

    SELECT COUNT(*)
    INTO v_award_classifications
    FROM reference.federal_inflow_award_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';

    SELECT COUNT(*)
    INTO v_program_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '14.871';

    IF v_program_classifications <> 0
       OR v_award_classifications <> 0
       OR v_program_mappings <> 0
    THEN
        RAISE EXCEPTION
            'M184 EXISTING-STATE GUARD FAILED: program_classifications=% award_classifications=% mappings=%',
            v_program_classifications,
            v_award_classifications,
            v_program_mappings;
    END IF;

    RAISE NOTICE
        'M184 EXISTING-STATE GUARD PASS: AL 14.871 has no prior classifications or mappings';
END
$$;


-- ================================================================================================
-- 5. INSERT SOURCE POLICY
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. INSERT HUD HCV SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

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
VALUES (
    'HOUSING_ASSISTANCE',
    'HOUSING_CHOICE_VOUCHERS',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY['HUD_VMS']::text[],
    'INCLUDE',
    'Housing Choice Voucher Program (14.871) is a genuine federal economic inflow to Washington. USAspending net federal action obligations are retained as the statewide accounting measure. HUD Voucher Management System HAP Total is retained as program-specific validation and reconciliation evidence but is not independently additive because it measures a different accounting stage of substantially overlapping HCV activity. COVID and extraordinary classifications remain provenance dimensions and do not alter additive disposition. County allocation is deferred because PHA administrative geography is not certified as beneficiary or economic-incidence geography.',
    'ANALYSIS-174B-5Y-v1',
    2020,
    2024
);


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-174B-5Y-v1'
      AND inflow_family =
          'HOUSING_ASSISTANCE'
      AND inflow_subfamily =
          'HOUSING_CHOICE_VOUCHERS';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'M184 SOURCE POLICY INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M184 SOURCE POLICY INSERT PASS: 1 policy';
END
$$;


-- ================================================================================================
-- 6. INSERT PROGRAM CLASSIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INSERT AL 14.871 PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_classification (
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
VALUES (
    'USASPENDING_ASSISTANCE',
    '14.871',
    'Housing Choice Voucher Program',
    'HOUSING_ASSISTANCE',
    'HOUSING_CHOICE_VOUCHERS',
    'NONE',
    TRUE,
    TRUE,
    'ETL-174B-5Y established AL 14.871 as genuine additive Washington federal housing assistance. ETL-174B-5Y-2C.1 independently certified HUD VMS HAP Total semantics and arithmetic. ETL-174B-5Y-2D-1 through 2D-3 established that USAspending obligations and VMS HAP expenditure/use exhibit materially different accounting-stage and temporal behavior. VMS is retained as validation evidence and is not separately additive. COVID and extraordinary classifications remain provenance dimensions. County incidence is deferred.',
    'ANALYSIS-174B-5Y-v1',
    2020,
    2024
);


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND source_program_code =
          '14.871'
      AND methodology_version =
          'ANALYSIS-174B-5Y-v1';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'M184 PROGRAM CLASSIFICATION INSERT FAILED: expected 1 row, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M184 PROGRAM CLASSIFICATION INSERT PASS: 1 classification';
END
$$;


-- ================================================================================================
-- 7. INSERT PROGRAM-POLICY MAPPING
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT AL 14.871 PROGRAM-POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    '14.871',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'ETL-174B-5Y certified Housing Choice Voucher Program assistance as additive statewide federal inflow. USAspending net obligations are the accounting measure; HUD VMS is retained as non-additive validation evidence; COVID/extraordinary status remains provenance; county incidence is deferred.',
    'ANALYSIS-174B-5Y-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.methodology_version =
      'ANALYSIS-174B-5Y-v1'
  AND p.inflow_family =
      'HOUSING_ASSISTANCE'
  AND p.inflow_subfamily =
      'HOUSING_CHOICE_VOUCHERS';


DO $$
DECLARE
    v_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND source_program_code =
          '14.871'
      AND methodology_version =
          'ANALYSIS-174B-5Y-v1'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'M184 PROGRAM MAPPING INSERT FAILED: expected 1 INCLUDE_ADDITIVE row, found %',
            v_count;
    END IF;

    RAISE NOTICE
        'M184 PROGRAM MAPPING INSERT PASS: 1 mapping';
END
$$;


-- ================================================================================================
-- 8. RECONSTRUCT POST-MIGRATION EFFECTIVE DISPOSITION
--
-- Award classification retains precedence over program mapping.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.m184_award_matches;

CREATE TEMP TABLE m184_award_matches AS
SELECT
    l.assistance_transaction_id,
    a.accounting_disposition

FROM m184_ledger l

JOIN reference.federal_inflow_award_classification a
  ON a.source_system =
     'USASPENDING_ASSISTANCE'
 AND a.source_program_code =
     l.cfda_number
 AND a.source_award_identifier =
     l.source_award_identifier
 AND (
        a.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
           a.valid_from_fiscal_year
 )
 AND (
        a.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
           a.valid_through_fiscal_year
 );


DROP TABLE IF EXISTS pg_temp.m184_program_matches;

CREATE TEMP TABLE m184_program_matches AS
SELECT
    l.assistance_transaction_id,
    m.resolved_accounting_disposition

FROM m184_ledger l

JOIN reference.federal_inflow_program_policy_mapping m
  ON m.source_system =
     'USASPENDING_ASSISTANCE'
 AND m.source_program_code =
     l.cfda_number
 AND (
        m.valid_from_fiscal_year IS NULL
        OR l.action_date_fiscal_year >=
           m.valid_from_fiscal_year
 )
 AND (
        m.valid_through_fiscal_year IS NULL
        OR l.action_date_fiscal_year <=
           m.valid_through_fiscal_year
 );


DO $$
DECLARE
    v_award_duplicates   bigint;
    v_program_duplicates bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_award_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m184_award_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*)
    INTO v_program_duplicates
    FROM (
        SELECT assistance_transaction_id
        FROM m184_program_matches
        GROUP BY assistance_transaction_id
        HAVING COUNT(*) > 1
    ) x;

    IF v_award_duplicates <> 0
       OR v_program_duplicates <> 0
    THEN
        RAISE EXCEPTION
            'M184 POST-MIGRATION RESOLUTION UNIQUENESS FAILED: award_duplicates=% program_duplicates=%',
            v_award_duplicates,
            v_program_duplicates;
    END IF;

    RAISE NOTICE
        'M184 POST-MIGRATION RESOLUTION UNIQUENESS PASS';
END
$$;


DROP TABLE IF EXISTS pg_temp.m184_resolved;

CREATE TEMP TABLE m184_resolved AS
SELECT
    l.*,

    CASE
        WHEN a.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'
        WHEN p.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'
        ELSE 'UNCLASSIFIED'
    END AS resolution_level,

    COALESCE(
        a.accounting_disposition,
        p.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS effective_accounting_disposition

FROM m184_ledger l

LEFT JOIN m184_award_matches a
  ON a.assistance_transaction_id =
     l.assistance_transaction_id

LEFT JOIN m184_program_matches p
  ON p.assistance_transaction_id =
     l.assistance_transaction_id;


-- ================================================================================================
-- 9. POST-MIGRATION FOCAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. POST-MIGRATION AL 14.871 DISPOSITION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m184_resolved

WHERE cfda_number = '14.871'

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


DO $$
DECLARE
    v_include       numeric;
    v_unclassified numeric;
    v_other         numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition NOT IN (
                    'INCLUDE_ADDITIVE',
                    'UNCLASSIFIED_REVIEW'
                )
            ),
            0
        )

    INTO
        v_include,
        v_unclassified,
        v_other

    FROM m184_resolved

    WHERE cfda_number = '14.871';

    IF ABS(
           v_include
           - 4308080637.65::numeric
       ) > 0.01
       OR ABS(v_unclassified) > 0.01
       OR ABS(v_other) > 0.01
    THEN
        RAISE EXCEPTION
            'M184 FOCAL POST-MIGRATION CONTROL FAILED: include=% unclassified=% other=%',
            v_include,
            v_unclassified,
            v_other;
    END IF;

    RAISE NOTICE
        'M184 FOCAL POST-MIGRATION CONTROL PASS: INCLUDE_ADDITIVE=%',
        v_include;
END
$$;


-- ================================================================================================
-- 10. FULL POST-MIGRATION ASSISTANCE BRIDGE
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. FULL POST-MIGRATION ASSISTANCE BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    effective_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS obligation_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_iija
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS iija_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m184_resolved

GROUP BY effective_accounting_disposition

ORDER BY effective_accounting_disposition;


DO $$
DECLARE
    v_gross         numeric;
    v_exclude       numeric;
    v_include       numeric;
    v_reference     numeric;
    v_withhold      numeric;
    v_unclassified numeric;
    v_closure       numeric;
BEGIN
    SELECT
        COALESCE(
            SUM(federal_action_obligation),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'EXCLUDE_DUPLICATE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'REFERENCE_ONLY'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'WITHHOLD_UNRESOLVED'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        )

    INTO
        v_gross,
        v_exclude,
        v_include,
        v_reference,
        v_withhold,
        v_unclassified

    FROM m184_resolved;

    v_closure :=
        v_gross
        - v_exclude
        - v_include
        - v_reference
        - v_withhold
        - v_unclassified;

    IF ABS(
           v_gross
           - 348524407674.34::numeric
       ) > 0.01
       OR ABS(
           v_exclude
           - 234974673851.81::numeric
       ) > 0.01
       OR ABS(
           v_include
           - 55805187540.69::numeric
       ) > 0.01
       OR ABS(
           v_reference
           - 7799088.00::numeric
       ) > 0.01
       OR ABS(
           v_withhold
           - 540783786.93::numeric
       ) > 0.01
       OR ABS(
           v_unclassified
           - 57195963406.91::numeric
       ) > 0.01
       OR ABS(v_closure) > 0.01
    THEN
        RAISE EXCEPTION
            'M184 FULL BRIDGE CONTROL FAILED: gross=% exclude=% include=% reference=% withhold=% unclassified=% closure=%',
            v_gross,
            v_exclude,
            v_include,
            v_reference,
            v_withhold,
            v_unclassified,
            v_closure;
    END IF;

    RAISE NOTICE
        'M184 FULL BRIDGE CONTROL PASS: gross=% include=% unclassified=% closure=%',
        v_gross,
        v_include,
        v_unclassified,
        v_closure;
END
$$;


-- ================================================================================================
-- 11. POST-MIGRATION AL 14.871 ANNUAL CONTROL
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. AL 14.871 ADDITIVE AMOUNT BY FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    action_date_fiscal_year AS fiscal_year,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS additive_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_amount,

    ROUND(
        SUM(
            CASE
                WHEN is_extraordinary
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS extraordinary_amount

FROM m184_resolved

WHERE cfda_number = '14.871'
  AND effective_accounting_disposition =
      'INCLUDE_ADDITIVE'

GROUP BY action_date_fiscal_year

ORDER BY action_date_fiscal_year;


-- ================================================================================================
-- 12. FINAL PERSISTED-STATE CERTIFICATION
-- ================================================================================================

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. FINAL PERSISTED-STATE CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_policies        bigint;
    v_classifications bigint;
    v_mappings        bigint;
    v_include         numeric;
    v_unclassified    numeric;
BEGIN
    SELECT COUNT(*)
    INTO v_policies
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version =
          'ANALYSIS-174B-5Y-v1'
      AND inflow_family =
          'HOUSING_ASSISTANCE'
      AND inflow_subfamily =
          'HOUSING_CHOICE_VOUCHERS';

    SELECT COUNT(*)
    INTO v_classifications
    FROM reference.federal_inflow_program_classification
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND methodology_version =
          'ANALYSIS-174B-5Y-v1'
      AND source_program_code =
          '14.871';

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system =
          'USASPENDING_ASSISTANCE'
      AND methodology_version =
          'ANALYSIS-174B-5Y-v1'
      AND source_program_code =
          '14.871'
      AND resolved_accounting_disposition =
          'INCLUDE_ADDITIVE';

    SELECT
        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'INCLUDE_ADDITIVE'
            ),
            0
        ),

        COALESCE(
            SUM(federal_action_obligation)
            FILTER (
                WHERE effective_accounting_disposition =
                      'UNCLASSIFIED_REVIEW'
            ),
            0
        )

    INTO
        v_include,
        v_unclassified

    FROM m184_resolved;

    IF v_policies <> 1
       OR v_classifications <> 1
       OR v_mappings <> 1
       OR ABS(
           v_include
           - 55805187540.69::numeric
       ) > 0.01
       OR ABS(
           v_unclassified
           - 57195963406.91::numeric
       ) > 0.01
    THEN
        RAISE EXCEPTION
            'M184 FINAL CERTIFICATION FAILED: policies=% classifications=% mappings=% include=% unclassified=%',
            v_policies,
            v_classifications,
            v_mappings,
            v_include,
            v_unclassified;
    END IF;

    RAISE NOTICE
        'M184 FINAL CERTIFICATION PASS: policies=1 classifications=1 mappings=1 INCLUDE_ADDITIVE=% UNCLASSIFIED_REVIEW=%',
        v_include,
        v_unclassified;
END
$$;


COMMIT;


\echo ''
\echo '===================================================================================================='
\echo 'MIGRATION 184 COMPLETE'
\echo '===================================================================================================='
\echo 'ANALYSIS-174B-5Y-v1'
\echo 'HUD HOUSING CHOICE VOUCHER ASSISTANCE POLICY COMMITTED'