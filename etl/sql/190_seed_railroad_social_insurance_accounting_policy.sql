/*
====================================================================================================
ETL-190
RAILROAD SOCIAL INSURANCE ACCOUNTING POLICY
AL 57.001
====================================================================================================

Purpose:
    Resolve Washington FY2020-FY2024 USAspending Assistance Listing 57.001
    after ETL-189A through ETL-189D established that the listing is a
    heterogeneous collection of Railroad Retirement Board benefit streams.

Evidence established by ETL-189D:
    Total population:
        transactions                    12,511
        awards                          12,511
        net obligation          $1,357,308,008.42
        COVID                         $752,151.14
        IIJA                                $0.00
        extraordinary                 $752,151.14

    High-level semantic partition:
        Railroad Retirement        $1,338,494,529.25
        RUIA unemployment/sickness     $18,813,479.17

Accounting decision:
    - USAspending/RRB benefit-payment observations are additive federal inflow.
    - AL 57.001 is heterogeneous and therefore is NOT resolved through a
      program-level INCLUDE_ADDITIVE mapping.
    - Award-level classifications are authoritative for this listing.
    - Existing program classification remains KNOWN_OVERLAP, preserving the
      reason reconciliation was required.
    - SSA/OASDI program mappings remain unchanged.
    - County incidence is not decided by this migration.

Methodology:
    ANALYSIS-190-v1

Fail-closed:
    Any focal award whose semantic description does not match an approved
    partition aborts the migration.

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-190 - RAILROAD SOCIAL INSURANCE ACCOUNTING POLICY'
\echo 'AL 57.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m190_rr;

CREATE TEMP TABLE m190_rr AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '57.001';


SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT recipient_id)
        AS recipient_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation,

    ROUND(SUM(
        CASE WHEN is_covid
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS covid_amount,

    ROUND(SUM(
        CASE WHEN is_iija
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS iija_amount,

    ROUND(SUM(
        CASE WHEN is_extraordinary
             THEN federal_action_obligation ELSE 0 END
    )::numeric, 2) AS extraordinary_amount

FROM m190_rr;


DO $$
DECLARE
    v_tx      bigint;
    v_awards  bigint;
    v_recip   bigint;
    v_amount  numeric;
    v_covid   numeric;
    v_iija    numeric;
    v_extra   numeric;
BEGIN

    SELECT
        COUNT(*),

        COUNT(
            DISTINCT COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            )
        ),

        COUNT(DISTINCT recipient_id),

        COALESCE(SUM(federal_action_obligation), 0),

        COALESCE(SUM(
            CASE WHEN is_covid
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_iija
                 THEN federal_action_obligation ELSE 0 END
        ), 0),

        COALESCE(SUM(
            CASE WHEN is_extraordinary
                 THEN federal_action_obligation ELSE 0 END
        ), 0)

    INTO
        v_tx,
        v_awards,
        v_recip,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m190_rr;


    IF v_tx <> 12511
       OR v_awards <> 12511
       OR v_recip <> 1
       OR ROUND(v_amount, 2) <> 1357308008.42
       OR ROUND(v_covid, 2) <> 752151.14
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 752151.14 THEN

        RAISE EXCEPTION
            'ETL-190 focal control failed: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-190 PRE-MIGRATION FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
2. RECONSTRUCT CERTIFIED ETL-189D SEMANTIC PARTITION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. RECONSTRUCT ETL-189D SEMANTIC PARTITION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m190_partition;

CREATE TEMP TABLE m190_partition AS

SELECT
    assistance_transaction_id,

    COALESCE(
        NULLIF(award_id_fain, ''),
        NULLIF(award_id_uri, '')
    ) AS source_award_identifier,

    action_date_fiscal_year,

    federal_action_obligation,

    is_covid,
    is_iija,
    is_extraordinary,

    canonical_award_description,

    CASE

        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE SOCIAL SECURITY EQUIVALENT ACCOUNT%'
            THEN 'RR_RETIREMENT_SSEB_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE RAILROAD RETIREMENT ACCOUNT%'
            THEN 'RR_RETIREMENT_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%PENSION PAID FROM THE VESTED DUAL BENEFIT ACCOUNT%'
            THEN 'RR_VESTED_DUAL_BENEFIT_ACCOUNT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD RETIREMENT ACT PENSION RECIPIENT%'
            THEN 'RR_RETIREMENT_PENSION_RECIPIENT'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%SUPPLEMENTAL FUNDING FOR THE CARES ACT%'
            THEN 'RUIA_COVID_SUPPLEMENTAL_FUNDING'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%ENHANCED BENEFIT%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_ENHANCED_BENEFIT'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%EXTENDED%'
            AND
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%BENEFIT%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_EXTENDED_BENEFIT'


        WHEN
            UPPER(
                COALESCE(canonical_award_description, '')
            ) LIKE '%WAITING PERIOD%'
            AND
            (
                   UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARES%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%CARWA%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%AMERICAN RESCUE PLAN%'
                OR UPPER(
                       COALESCE(canonical_award_description, '')
                   ) LIKE '%ARPA%'
            )
            THEN 'RUIA_COVID_WAITING_PERIOD_WAIVER'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD UNEMPLOYMENT INSURANCE TRUST FUND BENEFIT PAYMENTS%'
            THEN 'RUIA_TRUST_FUND_BENEFITS'


        WHEN UPPER(
            COALESCE(canonical_award_description, '')
        ) LIKE '%RAILROAD UNEMPLOYMENT INSURANCE ACT BENEFIT CLAIMANT%'
            THEN 'RUIA_BENEFIT_CLAIMANT'


        ELSE 'UNCLASSIFIED_REVIEW'

    END AS accounting_partition

FROM m190_rr;


/*
====================================================================================================
3. PARTITION HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. PARTITION HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    accounting_partition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT source_award_identifier) AS award_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190_partition

GROUP BY accounting_partition

ORDER BY net_obligation DESC;


DO $$
DECLARE
    v_rows          bigint;
    v_distinct      bigint;
    v_unclassified bigint;
    v_amount        numeric;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),
        COUNT(*) FILTER (
            WHERE accounting_partition = 'UNCLASSIFIED_REVIEW'
        ),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_rows,
        v_distinct,
        v_unclassified,
        v_amount

    FROM m190_partition;


    IF v_rows <> 12511
       OR v_distinct <> 12511
       OR v_unclassified <> 0
       OR ROUND(v_amount, 2) <> 1357308008.42 THEN

        RAISE EXCEPTION
            'ETL-190 partition control failed: rows %, distinct %, unclassified %, amount %',
            v_rows,
            v_distinct,
            v_unclassified,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-190 PARTITION HARD CONTROL PASS';

END
$$;


/*
====================================================================================================
4. PRESERVE EXISTING 57.001 PROGRAM CLASSIFICATION

We require the pre-existing classification and require it to remain
KNOWN_OVERLAP. We do NOT convert it to NONE.

ETL-189B established the relevant existing record:
    source_system       USASPENDING_ASSISTANCE
    source_program_code 57.001
    overlap_risk        KNOWN_OVERLAP
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. VERIFY EXISTING PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
      AND overlap_risk = 'KNOWN_OVERLAP';


    IF v_count <> 1 THEN

        RAISE EXCEPTION
            'ETL-190 expected exactly one KNOWN_OVERLAP program classification for 57.001; found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-190 EXISTING 57.001 KNOWN_OVERLAP CLASSIFICATION PRESERVED';

END
$$;


/*
====================================================================================================
5. PROHIBIT PROGRAM-LEVEL ACCOUNTING MAPPING

AL 57.001 is heterogeneous. Award-level treatment is authoritative.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. VERIFY NO PROGRAM-LEVEL 57.001 ACCOUNTING MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-190 refuses to proceed: 57.001 already has % program-policy mapping row(s)',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-190 NO PROGRAM-LEVEL 57.001 MAPPING PASS';

END
$$;


/*
====================================================================================================
6. INSERT RAILROAD RETIREMENT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. INSERT / VERIFY RAILROAD RETIREMENT SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_source_policy
(
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
    'RAILROAD_RETIREMENT',
    'RAILROAD_RETIREMENT_BENEFITS',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE_57.001',
    'USASPENDING_ASSISTANCE_57.001',
    ARRAY['SSA']::text[],
    'INCLUDE_AFTER_RECONCILIATION',

    'ETL-189A through ETL-189D reconciled USAspending Assistance Listing 57.001 against WCFFBP''s independently acquired SSA OASDI accounting path. Railroad Retirement Board pension payments are economically coordinated with Social Security, including Social Security Equivalent Benefit Account payments, but the profiled USAspending observations represent RRB-paid beneficiary payments rather than a second observation of SSA-paid OASDI benefits. AL 57.001 is heterogeneous; award-level semantic classification is authoritative. Existing program overlap risk remains KNOWN_OVERLAP. No county-incidence inference is authorized by this policy.',

    'ANALYSIS-190-v1',
    2020,
    2024

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'RAILROAD_RETIREMENT'
      AND inflow_subfamily = 'RAILROAD_RETIREMENT_BENEFITS'
      AND methodology_version = 'ANALYSIS-190-v1'
);


/*
====================================================================================================
7. INSERT RUIA SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. INSERT / VERIFY RUIA SOURCE POLICY'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_source_policy
(
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
    'RAILROAD_SOCIAL_INSURANCE',
    'RAILROAD_UNEMPLOYMENT_SICKNESS',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE_57.001',
    'USASPENDING_ASSISTANCE_57.001',
    ARRAY[]::text[],
    'INCLUDE',

    'ETL-189C and ETL-189D established that Assistance Listing 57.001 contains Railroad Unemployment Insurance Act unemployment/sickness benefit payments in addition to Railroad Retirement Act pension payments. Ordinary RUIA benefits and separately identified CARES/CARWA/ARPA-related RUIA benefits are additive federal inflow. COVID and extraordinary provenance remains attached to the underlying certified assistance observations. AL 57.001 is heterogeneous; award-level semantic classification is authoritative. No county-incidence inference is authorized by this policy.',

    'ANALYSIS-190-v1',
    2020,
    2024

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'RAILROAD_SOCIAL_INSURANCE'
      AND inflow_subfamily = 'RAILROAD_UNEMPLOYMENT_SICKNESS'
      AND methodology_version = 'ANALYSIS-190-v1'
);


/*
====================================================================================================
8. SOURCE POLICY PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. SOURCE POLICY PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_source_policy

WHERE methodology_version = 'ANALYSIS-190-v1'

ORDER BY federal_inflow_source_policy_id;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_source_policy

    WHERE methodology_version = 'ANALYSIS-190-v1';


    IF v_count <> 2 THEN

        RAISE EXCEPTION
            'ETL-190 expected exactly two source-policy rows; found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-190 SOURCE POLICY PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
9. BUILD AWARD-LEVEL CLASSIFICATION PAYLOAD

All 12,511 awards are unique in the focal population.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. BUILD AWARD-LEVEL CLASSIFICATION PAYLOAD'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m190_award_payload;

CREATE TEMP TABLE m190_award_payload AS

SELECT
    source_award_identifier,

    CASE
        WHEN accounting_partition IN
        (
            'RR_RETIREMENT_SSEB_ACCOUNT',
            'RR_RETIREMENT_ACCOUNT',
            'RR_RETIREMENT_PENSION_RECIPIENT',
            'RR_VESTED_DUAL_BENEFIT_ACCOUNT'
        )
        THEN 'RAILROAD_RETIREMENT'

        WHEN accounting_partition LIKE 'RUIA_%'
        THEN 'RAILROAD_SOCIAL_INSURANCE'

        ELSE 'UNCLASSIFIED_REVIEW'
    END AS inflow_family,

    CASE
        WHEN accounting_partition = 'RR_RETIREMENT_SSEB_ACCOUNT'
            THEN 'SOCIAL_SECURITY_EQUIVALENT_BENEFIT_ACCOUNT'

        WHEN accounting_partition = 'RR_RETIREMENT_ACCOUNT'
            THEN 'RAILROAD_RETIREMENT_ACCOUNT'

        WHEN accounting_partition = 'RR_RETIREMENT_PENSION_RECIPIENT'
            THEN 'RAILROAD_RETIREMENT_PENSION_RECIPIENT'

        WHEN accounting_partition = 'RR_VESTED_DUAL_BENEFIT_ACCOUNT'
            THEN 'VESTED_DUAL_BENEFIT_ACCOUNT'

        WHEN accounting_partition = 'RUIA_TRUST_FUND_BENEFITS'
            THEN 'RUIA_TRUST_FUND_BENEFITS'

        WHEN accounting_partition = 'RUIA_BENEFIT_CLAIMANT'
            THEN 'RUIA_BENEFIT_CLAIMANT'

        WHEN accounting_partition = 'RUIA_COVID_SUPPLEMENTAL_FUNDING'
            THEN 'RUIA_COVID_SUPPLEMENTAL_FUNDING'

        WHEN accounting_partition = 'RUIA_COVID_ENHANCED_BENEFIT'
            THEN 'RUIA_COVID_ENHANCED_BENEFIT'

        WHEN accounting_partition = 'RUIA_COVID_EXTENDED_BENEFIT'
            THEN 'RUIA_COVID_EXTENDED_BENEFIT'

        WHEN accounting_partition = 'RUIA_COVID_WAITING_PERIOD_WAIVER'
            THEN 'RUIA_COVID_WAITING_PERIOD_WAIVER'

        ELSE 'UNCLASSIFIED_REVIEW'
    END AS inflow_subfamily,

    'INCLUDE_ADDITIVE'
        AS accounting_disposition,

    accounting_partition,

    MIN(action_date_fiscal_year)
        AS valid_from_fiscal_year,

    MAX(action_date_fiscal_year)
        AS valid_through_fiscal_year,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190_partition

GROUP BY
    source_award_identifier,
    accounting_partition;


/*
====================================================================================================
10. AWARD PAYLOAD HARD CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. AWARD PAYLOAD HARD CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    inflow_family,
    COUNT(*) AS award_count,
    SUM(transaction_count) AS transaction_count,

    ROUND(
        SUM(net_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190_award_payload

GROUP BY inflow_family

ORDER BY net_obligation DESC;


DO $$
DECLARE
    v_awards       bigint;
    v_tx           bigint;
    v_amount       numeric;
    v_unclassified bigint;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(SUM(transaction_count), 0),
        COALESCE(SUM(net_obligation), 0),
        COUNT(*) FILTER (
            WHERE inflow_family = 'UNCLASSIFIED_REVIEW'
               OR inflow_subfamily = 'UNCLASSIFIED_REVIEW'
        )

    INTO
        v_awards,
        v_tx,
        v_amount,
        v_unclassified

    FROM m190_award_payload;


    IF v_awards <> 12511
       OR v_tx <> 12511
       OR ROUND(v_amount, 2) <> 1357308008.42
       OR v_unclassified <> 0 THEN

        RAISE EXCEPTION
            'ETL-190 award payload control failed: awards %, tx %, amount %, unclassified %',
            v_awards,
            v_tx,
            ROUND(v_amount, 2),
            v_unclassified;

    END IF;


    RAISE NOTICE
        'ETL-190 AWARD PAYLOAD HARD CONTROL PASS';

END
$$;


/*
====================================================================================================
11. COLLISION CONTROL

Fail if an AL 57.001 award already has a classification under another
methodology. We do not silently overwrite prior accounting decisions.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. PRE-EXISTING AWARD CLASSIFICATION COLLISION CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_collision_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_collision_count

    FROM reference.federal_inflow_award_classification a

    JOIN m190_award_payload p
      ON p.source_award_identifier
         = a.source_award_identifier

    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = '57.001'
      AND a.methodology_version <> 'ANALYSIS-190-v1';


    IF v_collision_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-190 found % pre-existing 57.001 award classification collisions',
            v_collision_count;

    END IF;


    RAISE NOTICE
        'ETL-190 AWARD COLLISION CONTROL PASS';

END
$$;


/*
====================================================================================================
12. INSERT AWARD-LEVEL CLASSIFICATIONS
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. INSERT AWARD-LEVEL CLASSIFICATIONS'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_award_classification
(
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
    '57.001',
    source_award_identifier,
    inflow_family,
    inflow_subfamily,
    accounting_disposition,

    'ETL-189A through ETL-189D established the semantic composition of USAspending Assistance Listing 57.001. Award-level classification is required because the listing contains heterogeneous Railroad Retirement Act pension and Railroad Unemployment Insurance Act benefit streams. The award description deterministically identifies the applicable substream. ANALYSIS-190-v1 treats the RRB-paid benefit as additive federal inflow after reconciliation with WCFFBP SSA OASDI accounting; this classification does not authorize county-incidence inference.',

    'ANALYSIS-190-v1',
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM m190_award_payload p

WHERE NOT EXISTS
(
    SELECT 1
    FROM reference.federal_inflow_award_classification a

    WHERE a.source_system = 'USASPENDING_ASSISTANCE'
      AND a.source_program_code = '57.001'
      AND a.source_award_identifier
          = p.source_award_identifier
      AND a.methodology_version = 'ANALYSIS-190-v1'
);


/*
====================================================================================================
13. AWARD CLASSIFICATION PERSISTENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '13. AWARD CLASSIFICATION PERSISTENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    inflow_family,
    inflow_subfamily,
    accounting_disposition,
    COUNT(*) AS award_count

FROM reference.federal_inflow_award_classification

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '57.001'
  AND methodology_version = 'ANALYSIS-190-v1'

GROUP BY
    inflow_family,
    inflow_subfamily,
    accounting_disposition

ORDER BY
    inflow_family,
    inflow_subfamily;


DO $$
DECLARE
    v_count        bigint;
    v_distinct     bigint;
    v_nonadditive  bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT source_award_identifier),

        COUNT(*) FILTER (
            WHERE accounting_disposition <> 'INCLUDE_ADDITIVE'
        )

    INTO
        v_count,
        v_distinct,
        v_nonadditive

    FROM reference.federal_inflow_award_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001'
      AND methodology_version = 'ANALYSIS-190-v1';


    IF v_count <> 12511
       OR v_distinct <> 12511
       OR v_nonadditive <> 0 THEN

        RAISE EXCEPTION
            'ETL-190 award persistence failed: rows %, distinct %, nonadditive %',
            v_count,
            v_distinct,
            v_nonadditive;

    END IF;


    RAISE NOTICE
        'ETL-190 AWARD CLASSIFICATION PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
14. VERIFY SSA/OASDI PROGRAM MAPPINGS REMAIN UNCHANGED

Existing mappings:
    96.001 EXCLUDE_DUPLICATE
    96.002 EXCLUDE_DUPLICATE
    96.004 EXCLUDE_DUPLICATE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '14. SSA/OASDI NON-INTERFERENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    source_program_code,
    resolved_accounting_disposition,
    methodology_version

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code IN
      (
          '96.001',
          '96.002',
          '96.004'
      )

ORDER BY source_program_code;


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code IN
          (
              '96.001',
              '96.002',
              '96.004'
          )
      AND resolved_accounting_disposition = 'EXCLUDE_DUPLICATE';


    IF v_count <> 3 THEN

        RAISE EXCEPTION
            'ETL-190 SSA/OASDI non-interference control failed: expected 3 EXCLUDE_DUPLICATE mappings, found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-190 SSA/OASDI NON-INTERFERENCE PASS';

END
$$;


/*
====================================================================================================
15. EFFECTIVE 57.001 RESOLUTION

Prove every focal transaction resolves through award-level authority.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '15. EFFECTIVE 57.001 RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m190_effective;

CREATE TEMP TABLE m190_effective AS

SELECT
    r.assistance_transaction_id,
    r.source_award_identifier,
    r.federal_action_obligation,

    a.inflow_family,
    a.inflow_subfamily,
    a.accounting_disposition

FROM m190_partition r

LEFT JOIN reference.federal_inflow_award_classification a
  ON a.source_system = 'USASPENDING_ASSISTANCE'
 AND a.source_program_code = '57.001'
 AND a.source_award_identifier
     = r.source_award_identifier
 AND a.methodology_version = 'ANALYSIS-190-v1';


SELECT
    accounting_disposition,
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m190_effective

GROUP BY accounting_disposition

ORDER BY accounting_disposition;


DO $$
DECLARE
    v_rows       bigint;
    v_distinct   bigint;
    v_additive   bigint;
    v_null       bigint;
    v_amount     numeric;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id),

        COUNT(*) FILTER (
            WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
        ),

        COUNT(*) FILTER (
            WHERE accounting_disposition IS NULL
        ),

        COALESCE(SUM(
            CASE
                WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
                THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_rows,
        v_distinct,
        v_additive,
        v_null,
        v_amount

    FROM m190_effective;


    IF v_rows <> 12511
       OR v_distinct <> 12511
       OR v_additive <> 12511
       OR v_null <> 0
       OR ROUND(v_amount, 2) <> 1357308008.42 THEN

        RAISE EXCEPTION
            'ETL-190 effective resolution failed: rows %, distinct %, additive %, null %, additive amount %',
            v_rows,
            v_distinct,
            v_additive,
            v_null,
            ROUND(v_amount, 2);

    END IF;


    RAISE NOTICE
        'ETL-190 EFFECTIVE 57.001 RESOLUTION PASS';

END
$$;


/*
====================================================================================================
16. FINAL PROGRAM-LEVEL MAPPING ABSENCE CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '16. FINAL PROGRAM-LEVEL MAPPING ABSENCE CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS program_mapping_count

FROM reference.federal_inflow_program_policy_mapping

WHERE source_system = 'USASPENDING_ASSISTANCE'
  AND source_program_code = '57.001';


DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '57.001';


    IF v_count <> 0 THEN

        RAISE EXCEPTION
            'ETL-190 program-level mapping absence control failed: found %',
            v_count;

    END IF;


    RAISE NOTICE
        'ETL-190 PROGRAM-LEVEL MAPPING ABSENCE PASS';

END
$$;


/*
====================================================================================================
17. FINAL CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '17. FINAL CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS focal_transactions,

    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_focal_transactions,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS focal_net_obligation,

    COUNT(*) FILTER (
        WHERE accounting_disposition = 'INCLUDE_ADDITIVE'
    ) AS additive_transactions,

    ROUND(SUM(
        CASE
            WHEN accounting_disposition = 'INCLUDE_ADDITIVE'
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric, 2) AS additive_net_obligation

FROM m190_effective;


DO $$
BEGIN

    RAISE NOTICE
        'ETL-190 HARD CERTIFICATION PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-190 COMPLETE'
\echo ''
\echo 'Expected accounting result:'
\echo '  AL 57.001 focal amount          $1,357,308,008.42'
\echo '  Award-level INCLUDE_ADDITIVE    $1,357,308,008.42'
\echo '  Program-level mapping           NONE'
\echo '  Existing overlap risk           KNOWN_OVERLAP preserved'
\echo '  SSA/OASDI mappings              unchanged'
\echo '  County-incidence decision       NONE'
\echo '===================================================================================================='
\echo ''

COMMIT;