/*
ETL-166
Create Assistance Observation-Grain Geographic Attribution View

Purpose
-------
Provide geographic attribution at the Assistance source-observation grain
for batch certification and provenance analysis.

This view intentionally does NOT replace:

    analysis.v_assistance_geographic_attribution

The existing view remains canonical-transaction grain and continues to
support additive fiscal analysis and its existing downstream consumers.

This view is based on:

    analysis.v_assistance_transaction_observation_ledger

and therefore contains exactly one row per raw Assistance observation.

IMPORTANT
---------
observation_load_batch_id identifies the source observation batch.

canonical_load_batch_id identifies the batch in which the globally
canonical transaction was created.

Batch certification must use observation_load_batch_id.

This view must not be summed across overlapping observation batches as
though repeated observations were independent fiscal transactions.
*/

BEGIN;


CREATE OR REPLACE VIEW
analysis.v_assistance_observation_geographic_attribution AS

SELECT
    l.*,

    CASE
        WHEN l.place_identity_key =
             '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN 'GEOGRAPHY_CONFLICT'

        WHEN l.reference_state_abbreviation = 'WA'
             AND l.reference_county_id IS NOT NULL
            THEN 'WA_COUNTY'

        WHEN l.reference_state_abbreviation = 'WA'
            THEN 'WA_UNSPECIFIED'

        ELSE 'NON_WASHINGTON'
    END AS geographic_attribution_class,


    CASE
        WHEN l.place_identity_key =
             '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN 'DQ-001_STATE_ZIP_CONFLICT'

        WHEN l.reference_state_abbreviation = 'WA'
             AND l.reference_county_id IS NOT NULL
            THEN 'REFERENCE_STATE_AND_COUNTY_MATCH'

        WHEN l.reference_state_abbreviation = 'WA'
             AND l.place_source_condition =
                 'WASHINGTON_UNSPECIFIED'
            THEN 'SOURCE_CONDITION_WASHINGTON_UNSPECIFIED'

        WHEN l.reference_state_abbreviation = 'WA'
            THEN 'WASHINGTON_COUNTY_UNRESOLVED'

        ELSE 'NOT_WASHINGTON'
    END AS geographic_attribution_reason,


    CASE
        WHEN l.place_identity_key =
             '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN false

        WHEN l.reference_state_abbreviation = 'WA'
            THEN true

        ELSE false
    END AS is_washington_attributed,


    CASE
        WHEN l.reference_state_abbreviation = 'WA'
             AND l.reference_county_id IS NOT NULL
             AND l.place_identity_key <>
                 '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN true

        ELSE false
    END AS is_washington_county_attributed,


    CASE
        WHEN l.place_identity_key =
             '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN true

        ELSE false
    END AS is_geography_conflict

FROM analysis.v_assistance_transaction_observation_ledger AS l;


/*
======================================================================
GLOBAL GRAIN VALIDATION
======================================================================

The observation geographic view must contain exactly one row for every
row in the observation ledger.
*/

DO $$
DECLARE
    v_ledger_count       bigint;
    v_geo_count          bigint;
    v_distinct_raw_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_ledger_count
    FROM analysis.v_assistance_transaction_observation_ledger;

    SELECT
        COUNT(*),
        COUNT(DISTINCT raw_assistance_transaction_id)
    INTO
        v_geo_count,
        v_distinct_raw_count
    FROM analysis.v_assistance_observation_geographic_attribution;

    IF v_geo_count <> v_ledger_count
       OR v_distinct_raw_count <> v_ledger_count THEN

        RAISE EXCEPTION
            'ETL-166 global validation failed. ledger=%, geography=%, distinct_raw=%',
            v_ledger_count,
            v_geo_count,
            v_distinct_raw_count;
    END IF;

    RAISE NOTICE
        'ETL-166 GLOBAL PASS: ledger=%, geography=%, distinct_raw=%',
        v_ledger_count,
        v_geo_count,
        v_distinct_raw_count;
END
$$;


/*
======================================================================
GEOGRAPHIC CLASS VALIDATION
======================================================================
*/

DO $$
DECLARE
    v_invalid_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_invalid_count
    FROM analysis.v_assistance_observation_geographic_attribution
    WHERE geographic_attribution_class NOT IN (
        'WA_COUNTY',
        'WA_UNSPECIFIED',
        'GEOGRAPHY_CONFLICT',
        'NON_WASHINGTON'
    );

    IF v_invalid_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-166 geographic-class validation failed: % invalid rows',
            v_invalid_count;
    END IF;

    RAISE NOTICE
        'ETL-166 GEOGRAPHIC CLASS PASS: invalid rows=%',
        v_invalid_count;
END
$$;


/*
======================================================================
CANONICAL/OBSERVATION RULE-EQUIVALENCE VALIDATION
======================================================================

Because the new view intentionally reproduces the classification rules
of analysis.v_assistance_geographic_attribution, every observation must
receive the same geographic classification as its corresponding
canonical transaction.
*/

DO $$
DECLARE
    v_mismatch_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_mismatch_count
    FROM analysis.v_assistance_observation_geographic_attribution AS o
    JOIN analysis.v_assistance_geographic_attribution AS c
      ON c.assistance_transaction_id =
         o.assistance_transaction_id
    WHERE o.geographic_attribution_class
              IS DISTINCT FROM c.geographic_attribution_class
       OR o.geographic_attribution_reason
              IS DISTINCT FROM c.geographic_attribution_reason
       OR o.is_washington_attributed
              IS DISTINCT FROM c.is_washington_attributed
       OR o.is_washington_county_attributed
              IS DISTINCT FROM c.is_washington_county_attributed
       OR o.is_geography_conflict
              IS DISTINCT FROM c.is_geography_conflict;

    IF v_mismatch_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-166 canonical/observation geography mismatch: % rows',
            v_mismatch_count;
    END IF;

    RAISE NOTICE
        'ETL-166 RULE EQUIVALENCE PASS: mismatches=%',
        v_mismatch_count;
END
$$;


/*
======================================================================
BATCH 19 REGRESSION ASSERTION
======================================================================

Batch 19 must expose all 74,171 source observations rather than only
the 63 canonical transactions first created in that batch.
*/

DO $$
DECLARE
    v_batch19_count bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_batch19_count
    FROM analysis.v_assistance_observation_geographic_attribution
    WHERE observation_load_batch_id = 19;

    IF v_batch19_count <> 74171 THEN
        RAISE EXCEPTION
            'ETL-166 Batch 19 regression failed. expected 74171, found %',
            v_batch19_count;
    END IF;

    RAISE NOTICE
        'ETL-166 BATCH 19 PASS: geographic observations=%',
        v_batch19_count;
END
$$;


COMMIT;