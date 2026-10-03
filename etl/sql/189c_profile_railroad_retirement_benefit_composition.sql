/*
====================================================================================================
ETL-189C
RAILROAD RETIREMENT BENEFIT COMPOSITION / SSA OVERLAP RECONCILIATION
AL 57.001
====================================================================================================

Purpose:
    Determine what the USAspending AL 57.001 observations actually represent
    before resolving their relationship to WCFFBP's independently acquired
    SSA OASDI benefit-payment source.

Questions:
    1. What assistance type is reported?
    2. What do award / transaction descriptions say?
    3. What structure is encoded in the RRB award identifiers?
    4. Are the observations consistent with beneficiary-payment aggregates,
       financial-interchange transfers, or another RRB accounting construct?
    5. Does more than one semantic payment class appear?

Known certified control:
    transactions       12,511
    awards             12,511
    recipients              1
    net obligation     $1,357,308,008.42
    COVID              $752,151.14
    IIJA               $0.00
    extraordinary      $752,151.14

Diagnostic only.
No persistent database writes.
No accounting classification.
No county-incidence inference.
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189C - RAILROAD RETIREMENT BENEFIT COMPOSITION / SSA OVERLAP RECONCILIATION'
\echo 'AL 57.001'
\echo '===================================================================================================='

BEGIN;


/*
====================================================================================================
1. FOCAL POPULATION
====================================================================================================
*/

DROP TABLE IF EXISTS pg_temp.m189c_rr;

CREATE TEMP TABLE m189c_rr AS
SELECT *
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND cfda_number = '57.001';


/*
====================================================================================================
2. HARD FOCAL CONTROL
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '2. HARD FOCAL CONTROL'
\echo '----------------------------------------------------------------------------------------------------'

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
    ) AS net_obligation

FROM m189c_rr;


DO $$
DECLARE
    v_tx      bigint;
    v_awards  bigint;
    v_recip   bigint;
    v_amount  numeric;
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

        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_tx,
        v_awards,
        v_recip,
        v_amount

    FROM m189c_rr;


    IF v_tx <> 12511
       OR v_awards <> 12511
       OR v_recip <> 1
       OR ROUND(v_amount, 2) <> 1357308008.42 THEN

        RAISE EXCEPTION
            'ETL-189C focal mismatch: tx %, awards %, recipients %, amount %',
            v_tx,
            v_awards,
            v_recip,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-189C FOCAL CONTROL PASS';

END
$$;


/*
====================================================================================================
3. AVAILABLE COLUMN INVENTORY

Do this first so the diagnostic remains transparent about what semantic fields
the certified ledger actually exposes.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '3. CERTIFIED LEDGER SEMANTIC COLUMN INVENTORY'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
  AND
  (
         column_name ILIKE '%description%'
      OR column_name ILIKE '%assistance%'
      OR column_name ILIKE '%award%'
      OR column_name ILIKE '%recipient%'
      OR column_name ILIKE '%cfda%'
      OR column_name ILIKE '%action%'
      OR column_name ILIKE '%funding%'
      OR column_name ILIKE '%agency%'
      OR column_name ILIKE '%type%'
  )

ORDER BY ordinal_position;


/*
====================================================================================================
4. ASSISTANCE-TYPE PROFILE

The certified view has previously exposed assistance_type_description.
If the column is absent in the current schema, report that rather than fail.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '4. ASSISTANCE-TYPE PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_exists boolean;
    r record;
BEGIN

    SELECT EXISTS
    (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'analysis'
          AND table_name = 'v_certified_assistance_ledger'
          AND column_name = 'assistance_type_description'
    )
    INTO v_exists;


    IF NOT v_exists THEN

        RAISE NOTICE
            'assistance_type_description is not exposed by analysis.v_certified_assistance_ledger';

    ELSE

        RAISE NOTICE
            'assistance_type_description is available; profile follows';

        FOR r IN
            EXECUTE $sql$
                SELECT
                    COALESCE(
                        NULLIF(assistance_type_description, ''),
                        '[NULL]'
                    ) AS assistance_type_description,

                    COUNT(*) AS transaction_count,

                    ROUND(
                        SUM(federal_action_obligation)::numeric,
                        2
                    ) AS net_obligation

                FROM m189c_rr

                GROUP BY 1

                ORDER BY net_obligation DESC
            $sql$

        LOOP

            RAISE NOTICE
                'ASSISTANCE TYPE | % | tx=% | amount=%',
                r.assistance_type_description,
                r.transaction_count,
                r.net_obligation;

        END LOOP;

    END IF;

END
$$;


/*
====================================================================================================
5. AWARD IDENTIFIER STRUCTURE

The award identifiers observed in ETL-189A resemble:
    RRB_20240115_8010_WA**063

Profile:
    - apparent embedded account/program token
    - apparent geographic suffix
    - frequency of identifier forms
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '5. AWARD IDENTIFIER STRUCTURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH ids AS
(
    SELECT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier,

        federal_action_obligation

    FROM m189c_rr
),

parsed AS
(
    SELECT
        award_identifier,

        split_part(award_identifier, '_', 1)
            AS token_1,

        split_part(award_identifier, '_', 2)
            AS token_2,

        split_part(award_identifier, '_', 3)
            AS token_3,

        split_part(award_identifier, '_', 4)
            AS token_4,

        federal_action_obligation

    FROM ids

    WHERE award_identifier IS NOT NULL
)

SELECT
    token_1,
    token_3,

    COUNT(*) AS transaction_count,

    COUNT(DISTINCT token_4)
        AS distinct_token_4,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM parsed

GROUP BY
    token_1,
    token_3

ORDER BY net_obligation DESC;


/*
====================================================================================================
6. GEOGRAPHIC-SUFFIX PROFILE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '6. AWARD IDENTIFIER GEOGRAPHIC-SUFFIX PROFILE'
\echo '----------------------------------------------------------------------------------------------------'

WITH ids AS
(
    SELECT
        COALESCE(
            NULLIF(award_id_fain, ''),
            NULLIF(award_id_uri, '')
        ) AS award_identifier,

        federal_action_obligation

    FROM m189c_rr
),

parsed AS
(
    SELECT
        split_part(award_identifier, '_', 4)
            AS geographic_token,

        federal_action_obligation

    FROM ids

    WHERE award_identifier IS NOT NULL
)

SELECT
    geographic_token,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM parsed

GROUP BY geographic_token

ORDER BY net_obligation DESC

LIMIT 100;


/*
====================================================================================================
7. DESCRIPTION FIELD INVENTORY

List only the description-like columns actually available. This avoids
guessing field names.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '7. AVAILABLE DESCRIPTION FIELDS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    ordinal_position,
    column_name,
    data_type

FROM information_schema.columns

WHERE table_schema = 'analysis'
  AND table_name = 'v_certified_assistance_ledger'
  AND column_name ILIKE '%description%'

ORDER BY ordinal_position;


/*
====================================================================================================
8. SEMANTIC SEARCH ACROSS AVAILABLE DESCRIPTION FIELDS

Dynamically inspect every description-like text field exposed by the certified
ledger. Search for terms capable of distinguishing beneficiary payments from
financial-interchange or administrative transfers.

No assumed description-column names.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '8. DESCRIPTION SEMANTIC SEARCH'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m189c_semantic_hits;

CREATE TEMP TABLE m189c_semantic_hits
(
    column_name       text,
    semantic_term     text,
    transaction_count bigint,
    net_obligation    numeric
);


DO $$
DECLARE
    c record;
    term text;
    v_sql text;

    v_terms text[] :=
        ARRAY[
            'BENEFIT',
            'ANNUITY',
            'RETIRE',
            'SURVIV',
            'DISAB',
            'TIER',
            'SOCIAL SECURITY',
            'SSA',
            'INTERCHANGE',
            'SSEB',
            'TRUST FUND',
            'PENSION',
            'UNEMPLOY',
            'SICKNESS'
        ];

BEGIN

    FOR c IN

        SELECT column_name

        FROM information_schema.columns

        WHERE table_schema = 'analysis'
          AND table_name = 'v_certified_assistance_ledger'
          AND column_name ILIKE '%description%'
          AND data_type IN
              (
                  'text',
                  'character varying',
                  'character'
              )

        ORDER BY ordinal_position

    LOOP

        FOREACH term IN ARRAY v_terms

        LOOP

            v_sql := format(
                $sql$

                INSERT INTO m189c_semantic_hits
                (
                    column_name,
                    semantic_term,
                    transaction_count,
                    net_obligation
                )

                SELECT
                    %L,
                    %L,
                    COUNT(*),
                    ROUND(
                        COALESCE(
                            SUM(federal_action_obligation),
                            0
                        )::numeric,
                        2
                    )

                FROM m189c_rr

                WHERE UPPER(
                    COALESCE(%I, '')
                ) LIKE %L

                HAVING COUNT(*) > 0

                $sql$,

                c.column_name,
                term,
                c.column_name,
                '%' || term || '%'
            );


            EXECUTE v_sql;

        END LOOP;

    END LOOP;

END
$$;


SELECT
    column_name,
    semantic_term,
    transaction_count,
    net_obligation

FROM m189c_semantic_hits

ORDER BY
    column_name,
    semantic_term;


/*
====================================================================================================
9. DISTINCT DESCRIPTION VALUES

Print compact distinct values from every available description-like field,
but only for fields with <= 50 distinct non-null values. This gives us actual
semantics without flooding the console with thousands of transaction strings.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '9. LOW-CARDINALITY DESCRIPTION VALUES'
\echo '----------------------------------------------------------------------------------------------------'

DROP TABLE IF EXISTS pg_temp.m189c_description_values;

CREATE TEMP TABLE m189c_description_values
(
    column_name        text,
    description_value  text,
    transaction_count  bigint,
    net_obligation     numeric
);


DO $$
DECLARE
    c record;
    v_distinct bigint;
    v_sql text;
BEGIN

    FOR c IN

        SELECT column_name

        FROM information_schema.columns

        WHERE table_schema = 'analysis'
          AND table_name = 'v_certified_assistance_ledger'
          AND column_name ILIKE '%description%'
          AND data_type IN
              (
                  'text',
                  'character varying',
                  'character'
              )

        ORDER BY ordinal_position

    LOOP

        v_sql := format(
            $sql$

            SELECT COUNT(
                DISTINCT NULLIF(%I, '')
            )

            FROM m189c_rr

            $sql$,
            c.column_name
        );

        EXECUTE v_sql
        INTO v_distinct;


        IF v_distinct BETWEEN 1 AND 50 THEN

            v_sql := format(
                $sql$

                INSERT INTO m189c_description_values
                (
                    column_name,
                    description_value,
                    transaction_count,
                    net_obligation
                )

                SELECT
                    %L,

                    LEFT(
                        COALESCE(
                            NULLIF(%I, ''),
                            '[NULL]'
                        ),
                        500
                    ),

                    COUNT(*),

                    ROUND(
                        SUM(federal_action_obligation)::numeric,
                        2
                    )

                FROM m189c_rr

                GROUP BY 1, 2

                ORDER BY 4 DESC

                $sql$,

                c.column_name,
                c.column_name
            );


            EXECUTE v_sql;

        END IF;

    END LOOP;

END
$$;


SELECT
    column_name,
    description_value,
    transaction_count,
    net_obligation

FROM m189c_description_values

ORDER BY
    column_name,
    net_obligation DESC;


/*
====================================================================================================
10. IDENTIFIER TOKEN x FISCAL YEAR

Tests whether the apparent 8010 token persists through all five years.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '10. IDENTIFIER TOKEN x FISCAL YEAR'
\echo '----------------------------------------------------------------------------------------------------'

WITH parsed AS
(
    SELECT
        action_date_fiscal_year,

        split_part(
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ),
            '_',
            3
        ) AS identifier_token,

        federal_action_obligation

    FROM m189c_rr
)

SELECT
    action_date_fiscal_year AS fiscal_year,
    identifier_token,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM parsed

GROUP BY
    action_date_fiscal_year,
    identifier_token

ORDER BY
    action_date_fiscal_year,
    net_obligation DESC;


/*
====================================================================================================
11. MONTHLY / DATE-TOKEN STRUCTURE

If token 2 is a YYYYMM or YYYYMMDD date-like value, profile its length and
leading year. This helps establish whether the observations are periodic
beneficiary-payment aggregates.
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '11. DATE-TOKEN STRUCTURE'
\echo '----------------------------------------------------------------------------------------------------'

WITH parsed AS
(
    SELECT
        split_part(
            COALESCE(
                NULLIF(award_id_fain, ''),
                NULLIF(award_id_uri, '')
            ),
            '_',
            2
        ) AS date_token,

        federal_action_obligation

    FROM m189c_rr
)

SELECT
    LENGTH(date_token) AS token_length,

    LEFT(date_token, 4)
        AS apparent_year,

    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation

FROM parsed

GROUP BY
    LENGTH(date_token),
    LEFT(date_token, 4)

ORDER BY
    apparent_year,
    token_length;


/*
====================================================================================================
12. CLOSURE
====================================================================================================
*/

\echo ''
\echo '----------------------------------------------------------------------------------------------------'
\echo '12. CLOSURE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    COUNT(*) AS closure_transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS closure_net_obligation

FROM m189c_rr;


DO $$
DECLARE
    v_tx     bigint;
    v_amount numeric;
BEGIN

    SELECT
        COUNT(*),
        COALESCE(
            SUM(federal_action_obligation),
            0
        )

    INTO
        v_tx,
        v_amount

    FROM m189c_rr;


    IF v_tx <> 12511
       OR ROUND(v_amount, 2) <> 1357308008.42 THEN

        RAISE EXCEPTION
            'ETL-189C closure failed: tx %, amount %',
            v_tx,
            ROUND(v_amount, 2);
    END IF;


    RAISE NOTICE
        'ETL-189C FOCAL CLOSURE PASS';

END
$$;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-189C COMPLETE'
\echo 'AL 57.001 Social Insurance for Railroad Workers'
\echo 'Benefit-composition / SSA-overlap diagnostic only.'
\echo 'No persistent database writes.'
\echo 'No accounting classification.'
\echo 'No county-incidence inference.'
\echo '===================================================================================================='
\echo ''

ROLLBACK;