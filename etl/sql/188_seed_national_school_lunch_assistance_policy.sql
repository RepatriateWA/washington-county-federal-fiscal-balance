/*
====================================================================================================
ETL-188
SEED NATIONAL SCHOOL LUNCH PROGRAM ASSISTANCE ACCOUNTING POLICY
AL 10.555
====================================================================================================

Purpose:
    Persist the WCFFBP statewide accounting treatment for USAspending
    AL 10.555, National School Lunch Program.

Evidence basis:
    ETL-187B PASS.

Certified FY2020-FY2024 Washington control:
        transactions          68
        awards                16
        recipients             1
        net obligation        $2,149,804,327.66
        COVID                 $178,329,137.37
        IIJA                  $0.00
        extraordinary         $178,329,137.37

Accounting decision:
    INCLUDE_ADDITIVE

Preferred statewide accounting source:
    USASPENDING_ASSISTANCE

Accounting measure:
    NET_FEDERAL_ACTION_OBLIGATION

Overlap finding:
    No identified overlap pathway with an existing independent
    WCFFBP principal accounting source.

County allocation:
    UNRESOLVED

Important double-count safeguard:
    Subsequent state/local expenditure, reimbursement, distribution,
    or pass-through of these already-counted federal National School
    Lunch Program dollars must not be counted as a second federal inflow.

Methodology:
    ANALYSIS-188-v1

Expected post-migration bridge:

    EXCLUDE_DUPLICATE
        70,782 transactions
        44 programs
        $234,974,673,851.81

    INCLUDE_ADDITIVE
        56,282 transactions
        21 programs
        $65,298,521,862.29

    REFERENCE_ONLY
        2,443 transactions
        4 programs
        $7,799,088.00

    UNCLASSIFIED_REVIEW
        811,546 transactions
        1,270 programs
        $47,702,629,085.31

    WITHHOLD_UNRESOLVED
        1,190 transactions
        13 programs
        $540,783,786.93

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-188 - SEED NATIONAL SCHOOL LUNCH PROGRAM ASSISTANCE ACCOUNTING POLICY'
\echo '===================================================================================================='
\echo ''

BEGIN;


/*
====================================================================================================
1. PRE-MIGRATION FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '1. PRE-MIGRATION NATIONAL SCHOOL LUNCH PROGRAM CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m188_lunch;

CREATE TEMP TABLE m188_lunch AS

SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '10.555';


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

FROM m188_lunch;


DO $$
DECLARE
    v_tx        bigint;
    v_awards    bigint;
    v_recip     bigint;
    v_amount    numeric;
    v_covid     numeric;
    v_iija      numeric;
    v_extra     numeric;
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
            CASE
                WHEN is_covid
                    THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_iija
                    THEN federal_action_obligation
                ELSE 0
            END
        ), 0),

        COALESCE(SUM(
            CASE
                WHEN is_extraordinary
                    THEN federal_action_obligation
                ELSE 0
            END
        ), 0)

    INTO
        v_tx,
        v_awards,
        v_recip,
        v_amount,
        v_covid,
        v_iija,
        v_extra

    FROM m188_lunch;


    IF v_tx <> 68
       OR v_awards <> 16
       OR v_recip <> 1
       OR ROUND(v_amount, 2) <> 2149804327.66
       OR ROUND(v_covid, 2) <> 178329137.37
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 178329137.37 THEN

        RAISE EXCEPTION
            'ETL-188 focal control mismatch: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-188 PRE-MIGRATION NATIONAL SCHOOL LUNCH CONTROL PASS';

END
$$;


/*
====================================================================================================
2. PRECONDITION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. PRECONDITION CHECK'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_count bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_count

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.555'
      AND methodology_version = 'ANALYSIS-188-v1';


    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-188 precondition failed: ANALYSIS-188-v1 mapping already exists for 10.555';
    END IF;


    RAISE NOTICE
        'ETL-188 PRECONDITION PASS';

END
$$;


/*
====================================================================================================
3. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. INSERT NATIONAL SCHOOL LUNCH SOURCE POLICY'
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
VALUES
(
    'NUTRITION_ASSISTANCE',
    'NATIONAL_SCHOOL_LUNCH_PROGRAM',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 10.555 is USDA federal school-nutrition assistance to Washington. '
    || 'ETL-187B established 68 FY2020-FY2024 transactions, 16 awards, '
    || 'one recipient, and $2,149,804,327.66 net federal action obligations. '
    || 'No identified overlap pathway exists with an independent WCFFBP '
    || 'principal accounting source. USAspending assistance is therefore '
    || 'the preferred statewide accounting source. Subsequent state/local '
    || 'expenditure, reimbursement, distribution, or pass-through of these '
    || 'already-counted federal dollars must not be counted as a second '
    || 'federal inflow.',

    'ANALYSIS-188-v1',
    2020,
    2024
)
RETURNING
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    ledger_treatment,
    methodology_version;


/*
====================================================================================================
4. INSERT PROGRAM CLASSIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. INSERT NATIONAL SCHOOL LUNCH PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_classification
(
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
VALUES
(
    'USASPENDING_ASSISTANCE',
    '10.555',
    'National School Lunch Program',
    'NUTRITION_ASSISTANCE',
    'NATIONAL_SCHOOL_LUNCH_PROGRAM',
    'NONE',
    TRUE,
    TRUE,

    'ETL-187B certified $2,149,804,327.66 of FY2020-FY2024 Washington '
    || 'net federal action obligations for AL 10.555. USDA funded all '
    || '68 transactions; the Superintendent of Public Instruction was '
    || 'the sole recipient. COVID/extraordinary provenance totals '
    || '$178,329,137.37; IIJA is $0.00. No independent WCFFBP principal '
    || 'source was identified as an overlapping accounting pathway.',

    'ANALYSIS-188-v1',
    2020,
    2024
)
RETURNING
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version;


/*
====================================================================================================
5. INSERT PROGRAM-POLICY MAPPING
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. INSERT NATIONAL SCHOOL LUNCH PROGRAM-POLICY MAPPING'
\echo '----------------------------------------------------------------------------------------------------'

INSERT INTO reference.federal_inflow_program_policy_mapping
(
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
    '10.555',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 10.555 is included as additive federal inflow using '
    || 'USAspending net federal action obligations. No identified '
    || 'overlap pathway with an independent WCFFBP principal accounting '
    || 'source requires exclusion or reconciliation.',

    'ANALYSIS-188-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'NUTRITION_ASSISTANCE'
  AND p.inflow_subfamily = 'NATIONAL_SCHOOL_LUNCH_PROGRAM'
  AND p.methodology_version = 'ANALYSIS-188-v1';


/*
====================================================================================================
6. POLICY PERSISTENCE CHECK
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. POLICY PERSISTENCE CHECK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.methodology_version,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.accounting_measure,
    p.preferred_source,
    p.allocation_source,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
    ON p.federal_inflow_source_policy_id
       = m.federal_inflow_source_policy_id

WHERE m.source_system = 'USASPENDING_ASSISTANCE'
  AND m.source_program_code = '10.555'
  AND m.methodology_version = 'ANALYSIS-188-v1';


DO $$
DECLARE
    v_policy bigint;
    v_class  bigint;
    v_map    bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy

    FROM reference.federal_inflow_source_policy

    WHERE inflow_family = 'NUTRITION_ASSISTANCE'
      AND inflow_subfamily = 'NATIONAL_SCHOOL_LUNCH_PROGRAM'
      AND methodology_version = 'ANALYSIS-188-v1';


    SELECT COUNT(*)
    INTO v_class

    FROM reference.federal_inflow_program_classification

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.555'
      AND methodology_version = 'ANALYSIS-188-v1';


    SELECT COUNT(*)
    INTO v_map

    FROM reference.federal_inflow_program_policy_mapping

    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '10.555'
      AND methodology_version = 'ANALYSIS-188-v1';


    IF v_policy <> 1
       OR v_class <> 1
       OR v_map <> 1 THEN

        RAISE EXCEPTION
            'ETL-188 persistence failed: policy %, classification %, mapping %',
            v_policy,
            v_class,
            v_map;
    END IF;


    RAISE NOTICE
        'ETL-188 POLICY PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
7. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m188_effective_resolution;

CREATE TEMP TABLE m188_effective_resolution AS

WITH ledger AS
(
    SELECT
        assistance_transaction_id,
        action_date_fiscal_year,
        federal_action_obligation,

        cfda_number,
        cfda_title,

        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS source_award_identifier

    FROM analysis.v_certified_assistance_ledger

    WHERE reference_state_abbreviation = 'WA'
      AND action_date_fiscal_year BETWEEN 2020 AND 2024
),

award_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        a.accounting_disposition
            AS resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                a.federal_inflow_award_classification_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_award_classification a
        ON a.source_system = 'USASPENDING_ASSISTANCE'
       AND a.source_award_identifier = l.source_award_identifier
       AND a.valid_from_fiscal_year <= 2024
       AND
       (
           a.valid_through_fiscal_year IS NULL
           OR a.valid_through_fiscal_year >= 2020
       )
),

program_resolution AS
(
    SELECT
        l.assistance_transaction_id,

        m.resolved_accounting_disposition,

        ROW_NUMBER() OVER
        (
            PARTITION BY l.assistance_transaction_id

            ORDER BY
                m.federal_inflow_program_policy_mapping_id DESC
        ) AS rn

    FROM ledger l

    JOIN reference.federal_inflow_program_policy_mapping m
        ON m.source_system = 'USASPENDING_ASSISTANCE'
       AND m.source_program_code = l.cfda_number
       AND m.valid_from_fiscal_year <= 2024
       AND
       (
           m.valid_through_fiscal_year IS NULL
           OR m.valid_through_fiscal_year >= 2020
       )
)

SELECT
    l.assistance_transaction_id,
    l.action_date_fiscal_year,
    l.federal_action_obligation,
    l.cfda_number,
    l.cfda_title,

    CASE
        WHEN ar.assistance_transaction_id IS NOT NULL
            THEN 'AWARD'

        WHEN pr.assistance_transaction_id IS NOT NULL
            THEN 'PROGRAM'

        ELSE 'NONE'
    END AS resolution_level,

    COALESCE(
        ar.resolved_accounting_disposition,
        pr.resolved_accounting_disposition,
        'UNCLASSIFIED_REVIEW'
    ) AS resolved_accounting_disposition

FROM ledger l

LEFT JOIN award_resolution ar
    ON ar.assistance_transaction_id
       = l.assistance_transaction_id
   AND ar.rn = 1

LEFT JOIN program_resolution pr
    ON pr.assistance_transaction_id
       = l.assistance_transaction_id
   AND pr.rn = 1;


/*
====================================================================================================
8. RESOLUTION UNIQUENESS / LEDGER CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. RESOLUTION UNIQUENESS / LEDGER CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS resolved_transaction_count,

    COUNT(
        DISTINCT assistance_transaction_id
    ) AS distinct_transaction_count

FROM m188_effective_resolution;


DO $$
DECLARE
    v_rows     bigint;
    v_distinct bigint;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT assistance_transaction_id)

    INTO
        v_rows,
        v_distinct

    FROM m188_effective_resolution;


    IF v_rows <> 942243 THEN
        RAISE EXCEPTION
            'ETL-188 ledger closure failed: expected 942243 rows, found %',
            v_rows;
    END IF;


    IF v_rows <> v_distinct THEN
        RAISE EXCEPTION
            'ETL-188 resolution uniqueness failed: rows %, distinct %',
            v_rows,
            v_distinct;
    END IF;


    RAISE NOTICE
        'ETL-188 RESOLUTION UNIQUENESS / LEDGER CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. POST-ETL-188 ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. POST-ETL-188 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m188_effective_resolution

GROUP BY resolved_accounting_disposition

ORDER BY resolved_accounting_disposition;


/*
====================================================================================================
10. NATIONAL SCHOOL LUNCH EFFECTIVE RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. NATIONAL SCHOOL LUNCH EFFECTIVE RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    resolved_accounting_disposition,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT cfda_number)
        AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m188_effective_resolution

WHERE cfda_number = '10.555'

GROUP BY
    resolution_level,
    resolved_accounting_disposition

ORDER BY
    resolution_level,
    resolved_accounting_disposition;


/*
====================================================================================================
11. HARD POST-MIGRATION CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. HARD POST-MIGRATION CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_tx       bigint;
    v_programs bigint;
    v_amount   numeric;
BEGIN

    /*
    Focal program
    */

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_amount

    FROM m188_effective_resolution

    WHERE cfda_number = '10.555'
      AND resolved_accounting_disposition
          = 'INCLUDE_ADDITIVE';


    IF v_tx <> 68
       OR ROUND(v_amount, 2) <> 2149804327.66 THEN

        RAISE EXCEPTION
            'ETL-188 focal certification failed: tx %, amount %',
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    /*
    INCLUDE_ADDITIVE
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m188_effective_resolution

    WHERE resolved_accounting_disposition
          = 'INCLUDE_ADDITIVE';


    IF v_tx <> 56282
       OR v_programs <> 21
       OR ROUND(v_amount, 2) <> 65298521862.29 THEN

        RAISE EXCEPTION
            'ETL-188 INCLUDE_ADDITIVE bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    UNCLASSIFIED_REVIEW
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m188_effective_resolution

    WHERE resolved_accounting_disposition
          = 'UNCLASSIFIED_REVIEW';


    IF v_tx <> 811546
       OR v_programs <> 1270
       OR ROUND(v_amount, 2) <> 47702629085.31 THEN

        RAISE EXCEPTION
            'ETL-188 UNCLASSIFIED bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    Other bridge categories must remain unchanged.
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m188_effective_resolution

    WHERE resolved_accounting_disposition
          = 'EXCLUDE_DUPLICATE';


    IF v_tx <> 70782
       OR v_programs <> 44
       OR ROUND(v_amount, 2) <> 234974673851.81 THEN

        RAISE EXCEPTION
            'ETL-188 EXCLUDE_DUPLICATE bridge mismatch';
    END IF;


    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m188_effective_resolution

    WHERE resolved_accounting_disposition
          = 'REFERENCE_ONLY';


    IF v_tx <> 2443
       OR v_programs <> 4
       OR ROUND(v_amount, 2) <> 7799088.00 THEN

        RAISE EXCEPTION
            'ETL-188 REFERENCE_ONLY bridge mismatch';
    END IF;


    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m188_effective_resolution

    WHERE resolved_accounting_disposition
          = 'WITHHOLD_UNRESOLVED';


    IF v_tx <> 1190
       OR v_programs <> 13
       OR ROUND(v_amount, 2) <> 540783786.93 THEN

        RAISE EXCEPTION
            'ETL-188 WITHHOLD_UNRESOLVED bridge mismatch';
    END IF;


    RAISE NOTICE
        'ETL-188 HARD POST-MIGRATION CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
12. CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-188 CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'AL 10.555 National School Lunch Program'
\echo 'Statewide disposition : INCLUDE_ADDITIVE'
\echo 'Preferred source       : USASPENDING_ASSISTANCE'
\echo 'Accounting measure     : NET_FEDERAL_ACTION_OBLIGATION'
\echo 'FY2020-FY2024 amount   : $2,149,804,327.66'
\echo 'COVID / extraordinary : $178,329,137.37'
\echo 'IIJA                    : $0.00'
\echo 'County allocation       : UNRESOLVED'
\echo ''
\echo 'IMPORTANT: subsequent state/local expenditure, reimbursement, distribution,'
\echo 'or pass-through of already-counted AL 10.555 federal funds must not be'
\echo 'counted as a second federal inflow.'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'ETL-188 PASS - COMMITTING'
\echo '===================================================================================================='
\echo ''

COMMIT;