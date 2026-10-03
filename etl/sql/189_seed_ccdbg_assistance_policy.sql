/*
====================================================================================================
ETL-189
SEED CHILD CARE AND DEVELOPMENT BLOCK GRANT ACCOUNTING POLICY
AL 93.575
====================================================================================================

Purpose:
    Persist WCFFBP statewide accounting treatment for USAspending
    AL 93.575, Child Care and Development Block Grant (CCDBG).

Evidence basis:
    ETL-188A PASS.

Certified FY2020-FY2024 Washington control:
        transactions          509
        awards                184
        recipients             28
        net obligation        $1,381,594,511.08
        COVID                 $957,110,173.00
        IIJA                  $0.00
        extraordinary         $957,110,173.00

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

Double-count safeguard:
    Subsequent state, tribal, local, provider, or other downstream
    expenditure/distribution of these already-counted federal CCDBG
    dollars must not be counted as a second federal inflow.

Important related-program rule:
    This policy applies only to AL 93.575. It does not classify
    AL 93.596 Child Care Mandatory and Matching Funds, which remains
    a separate federal funding stream requiring its own determination.

Methodology:
    ANALYSIS-189-v1

Expected post-migration bridge:

    EXCLUDE_DUPLICATE
        70,782 transactions
        44 programs
        $234,974,673,851.81

    INCLUDE_ADDITIVE
        56,791 transactions
        22 programs
        $66,680,116,373.37

    REFERENCE_ONLY
        2,443 transactions
        4 programs
        $7,799,088.00

    UNCLASSIFIED_REVIEW
        811,037 transactions
        1,269 programs
        $46,321,034,574.23

    WITHHOLD_UNRESOLVED
        1,190 transactions
        13 programs
        $540,783,786.93

====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189 - SEED CCDBG ASSISTANCE ACCOUNTING POLICY'
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
\echo '1. PRE-MIGRATION CCDBG CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m189_ccdbg;

CREATE TEMP TABLE m189_ccdbg AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '93.575';


SELECT
    COUNT(*) AS transaction_count,

    COUNT(
        DISTINCT COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        )
    ) AS award_count,

    COUNT(DISTINCT recipient_id) AS recipient_count,

    ROUND(SUM(federal_action_obligation)::numeric, 2)
        AS net_obligation,

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

FROM m189_ccdbg;


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

    FROM m189_ccdbg;


    IF v_tx <> 509
       OR v_awards <> 184
       OR v_recip <> 28
       OR ROUND(v_amount, 2) <> 1381594511.08
       OR ROUND(v_covid, 2) <> 957110173.00
       OR ROUND(v_iija, 2) <> 0.00
       OR ROUND(v_extra, 2) <> 957110173.00 THEN

        RAISE EXCEPTION
            'ETL-189 focal control mismatch: tx %, awards %, recipients %, amount %, COVID %, IIJA %, extraordinary %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2),
            ROUND(v_covid, 2),
            ROUND(v_iija, 2),
            ROUND(v_extra, 2);
    END IF;


    RAISE NOTICE
        'ETL-189 PRE-MIGRATION CCDBG CONTROL PASS';

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
      AND source_program_code = '93.575'
      AND methodology_version = 'ANALYSIS-189-v1';


    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-189 precondition failed: ANALYSIS-189-v1 mapping already exists for 93.575';
    END IF;


    RAISE NOTICE
        'ETL-189 PRECONDITION PASS';

END
$$;


/*
====================================================================================================
3. INSERT SOURCE POLICY
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. INSERT CCDBG SOURCE POLICY'
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
    'CHILD_CARE_ASSISTANCE',
    'CHILD_CARE_DEVELOPMENT_BLOCK_GRANT',
    'NET_FEDERAL_ACTION_OBLIGATION',
    'USASPENDING_ASSISTANCE',
    'UNRESOLVED',
    ARRAY[]::text[],
    'INCLUDE',

    'AL 93.575 is federal Child Care and Development Block Grant '
    || 'assistance to Washington and tribal recipients. ETL-188A '
    || 'established 509 FY2020-FY2024 transactions, 184 awards, '
    || '28 recipients, and $1,381,594,511.08 net federal action '
    || 'obligations. COVID/extraordinary provenance totals '
    || '$957,110,173.00 and does not itself create duplication. '
    || 'No identified overlap pathway exists with an independent '
    || 'WCFFBP principal accounting source. Subsequent downstream '
    || 'expenditure or distribution of already-counted CCDBG funds '
    || 'must not be counted as a second federal inflow. AL 93.596 '
    || 'is outside this policy and requires separate classification.',

    'ANALYSIS-189-v1',
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
\echo '4. INSERT CCDBG PROGRAM CLASSIFICATION'
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
    '93.575',
    'Child Care and Development Block Grant',
    'CHILD_CARE_ASSISTANCE',
    'CHILD_CARE_DEVELOPMENT_BLOCK_GRANT',
    'NONE',
    TRUE,
    TRUE,

    'ETL-188A certified $1,381,594,511.08 of FY2020-FY2024 '
    || 'Washington net federal action obligations for AL 93.575. '
    || 'The profile contains $957,110,173.00 of COVID/extraordinary '
    || 'provenance and $0.00 IIJA. No independent WCFFBP principal '
    || 'accounting source was identified as an overlapping pathway.',

    'ANALYSIS-189-v1',
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
\echo '5. INSERT CCDBG PROGRAM-POLICY MAPPING'
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
    '93.575',
    p.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',

    'AL 93.575 is included as additive federal inflow using '
    || 'USAspending net federal action obligations. COVID provenance '
    || 'is preserved separately. No identified overlap pathway with '
    || 'an independent WCFFBP principal accounting source requires '
    || 'exclusion or reconciliation.',

    'ANALYSIS-189-v1',
    2020,
    2024

FROM reference.federal_inflow_source_policy p

WHERE p.inflow_family = 'CHILD_CARE_ASSISTANCE'
  AND p.inflow_subfamily = 'CHILD_CARE_DEVELOPMENT_BLOCK_GRANT'
  AND p.methodology_version = 'ANALYSIS-189-v1';


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
  AND m.source_program_code = '93.575'
  AND m.methodology_version = 'ANALYSIS-189-v1';


DO $$
DECLARE
    v_policy bigint;
    v_class  bigint;
    v_map    bigint;
BEGIN

    SELECT COUNT(*)
    INTO v_policy
    FROM reference.federal_inflow_source_policy
    WHERE inflow_family = 'CHILD_CARE_ASSISTANCE'
      AND inflow_subfamily = 'CHILD_CARE_DEVELOPMENT_BLOCK_GRANT'
      AND methodology_version = 'ANALYSIS-189-v1';


    SELECT COUNT(*)
    INTO v_class
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.575'
      AND methodology_version = 'ANALYSIS-189-v1';


    SELECT COUNT(*)
    INTO v_map
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND source_program_code = '93.575'
      AND methodology_version = 'ANALYSIS-189-v1';


    IF v_policy <> 1
       OR v_class <> 1
       OR v_map <> 1 THEN

        RAISE EXCEPTION
            'ETL-189 persistence failed: policy %, classification %, mapping %',
            v_policy,
            v_class,
            v_map;
    END IF;


    RAISE NOTICE
        'ETL-189 POLICY PERSISTENCE PASS';

END
$$;


/*
====================================================================================================
7. RECONSTRUCT EFFECTIVE RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. RECONSTRUCT EFFECTIVE ASSISTANCE ACCOUNTING RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m189_effective_resolution;

CREATE TEMP TABLE m189_effective_resolution AS

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
            ORDER BY a.federal_inflow_award_classification_id DESC
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
            ORDER BY m.federal_inflow_program_policy_mapping_id DESC
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
    ON ar.assistance_transaction_id = l.assistance_transaction_id
   AND ar.rn = 1

LEFT JOIN program_resolution pr
    ON pr.assistance_transaction_id = l.assistance_transaction_id
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
    COUNT(DISTINCT assistance_transaction_id)
        AS distinct_transaction_count
FROM m189_effective_resolution;


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

    FROM m189_effective_resolution;


    IF v_rows <> 942243 THEN
        RAISE EXCEPTION
            'ETL-189 ledger closure failed: expected 942243 rows, found %',
            v_rows;
    END IF;


    IF v_rows <> v_distinct THEN
        RAISE EXCEPTION
            'ETL-189 resolution uniqueness failed: rows %, distinct %',
            v_rows,
            v_distinct;
    END IF;


    RAISE NOTICE
        'ETL-189 RESOLUTION UNIQUENESS / LEDGER CLOSURE PASS';

END
$$;


/*
====================================================================================================
9. POST-ETL-189 ACCOUNTING BRIDGE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. POST-ETL-189 ACCOUNTING BRIDGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m189_effective_resolution

GROUP BY resolved_accounting_disposition

ORDER BY resolved_accounting_disposition;


/*
====================================================================================================
10. CCDBG EFFECTIVE RESOLUTION
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. CCDBG EFFECTIVE RESOLUTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    resolution_level,
    resolved_accounting_disposition,
    COUNT(*) AS transaction_count,
    COUNT(DISTINCT cfda_number) AS program_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM m189_effective_resolution

WHERE cfda_number = '93.575'

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
    Focal program.
    */

    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_amount

    FROM m189_effective_resolution

    WHERE cfda_number = '93.575'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE';


    IF v_tx <> 509
       OR ROUND(v_amount, 2) <> 1381594511.08 THEN

        RAISE EXCEPTION
            'ETL-189 focal certification failed: tx %, amount %',
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    /*
    INCLUDE_ADDITIVE.
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m189_effective_resolution

    WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE';


    IF v_tx <> 56791
       OR v_programs <> 22
       OR ROUND(v_amount, 2) <> 66680116373.37 THEN

        RAISE EXCEPTION
            'ETL-189 INCLUDE_ADDITIVE bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    UNCLASSIFIED_REVIEW.
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m189_effective_resolution

    WHERE resolved_accounting_disposition = 'UNCLASSIFIED_REVIEW';


    IF v_tx <> 811037
       OR v_programs <> 1269
       OR ROUND(v_amount, 2) <> 46321034574.23 THEN

        RAISE EXCEPTION
            'ETL-189 UNCLASSIFIED bridge mismatch: tx %, programs %, amount %',
            v_tx,
            v_programs,
            ROUND(v_amount, 2);
    END IF;


    /*
    Unchanged bridge categories.
    */

    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m189_effective_resolution

    WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE';


    IF v_tx <> 70782
       OR v_programs <> 44
       OR ROUND(v_amount, 2) <> 234974673851.81 THEN
        RAISE EXCEPTION
            'ETL-189 EXCLUDE_DUPLICATE bridge mismatch';
    END IF;


    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m189_effective_resolution

    WHERE resolved_accounting_disposition = 'REFERENCE_ONLY';


    IF v_tx <> 2443
       OR v_programs <> 4
       OR ROUND(v_amount, 2) <> 7799088.00 THEN
        RAISE EXCEPTION
            'ETL-189 REFERENCE_ONLY bridge mismatch';
    END IF;


    SELECT
        COUNT(*),
        COUNT(DISTINCT cfda_number),
        COALESCE(SUM(federal_action_obligation), 0)

    INTO
        v_tx,
        v_programs,
        v_amount

    FROM m189_effective_resolution

    WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED';


    IF v_tx <> 1190
       OR v_programs <> 13
       OR ROUND(v_amount, 2) <> 540783786.93 THEN
        RAISE EXCEPTION
            'ETL-189 WITHHOLD_UNRESOLVED bridge mismatch';
    END IF;


    RAISE NOTICE
        'ETL-189 HARD POST-MIGRATION CERTIFICATION PASS';

END
$$;


/*
====================================================================================================
12. CERTIFICATION
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189 CERTIFICATION'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'AL 93.575 Child Care and Development Block Grant'
\echo 'Statewide disposition : INCLUDE_ADDITIVE'
\echo 'Preferred source       : USASPENDING_ASSISTANCE'
\echo 'Accounting measure     : NET_FEDERAL_ACTION_OBLIGATION'
\echo 'FY2020-FY2024 amount   : $1,381,594,511.08'
\echo 'COVID / extraordinary : $957,110,173.00'
\echo 'IIJA                    : $0.00'
\echo 'County allocation       : UNRESOLVED'
\echo ''
\echo 'IMPORTANT: downstream expenditure or distribution of already-counted'
\echo 'AL 93.575 federal funds must not be counted as a second federal inflow.'
\echo 'AL 93.596 remains outside this policy and requires separate classification.'
\echo '----------------------------------------------------------------------------------------------------'
\echo 'ETL-189 PASS - COMMITTING'
\echo '===================================================================================================='
\echo ''

COMMIT;