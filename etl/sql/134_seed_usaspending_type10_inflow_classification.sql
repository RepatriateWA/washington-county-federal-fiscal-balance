-- ============================================================================
-- ETL-134 — Seed USAspending Type-10 Federal Inflow Program Classifications
-- ============================================================================
--
-- Purpose
-- -------
-- Populate reference.federal_inflow_program_classification from observed
-- USAspending Assistance Type-10 programs.
--
-- This migration CLASSIFIES programs only.
-- It does NOT decide which source is authoritative for final ledger inclusion.
--
-- Core principle:
--
--     Preservation != ledger inclusion.
--
-- Programs with obvious cross-source duplication risk (SSA, VA, Railroad
-- social insurance) are explicitly tagged KNOWN_OVERLAP.
--
-- Classification is data-driven from the certified assistance ledger.
-- ============================================================================

BEGIN;


-- ============================================================================
-- 1. SEED OBSERVED TYPE-10 PROGRAMS
-- ============================================================================

WITH observed_type10 AS (
    SELECT
        cfda_number AS source_program_code,

        MAX(cfda_title) AS source_program_title,

        MIN(action_date_fiscal_year) AS first_fiscal_year,
        MAX(action_date_fiscal_year) AS last_fiscal_year,

        BOOL_OR(is_covid) AS covid_relevance,
        BOOL_OR(is_extraordinary) AS extraordinary_relevance

    FROM analysis.v_assistance_geographic_attribution

    WHERE geographic_attribution_class IN (
        'WA_COUNTY',
        'WA_UNSPECIFIED',
        'GEOGRAPHY_CONFLICT'
    )

      AND assistance_type_code = '10'

      AND NULLIF(BTRIM(cfda_number), '') IS NOT NULL

    GROUP BY cfda_number
),

classified AS (
    SELECT
        source_program_code,
        source_program_title,

        CASE
            WHEN source_program_code LIKE '96.%'
                THEN 'SOCIAL_SECURITY'

            WHEN source_program_code LIKE '64.%'
                THEN 'VETERANS'

            WHEN source_program_code LIKE '57.%'
                THEN 'RAILROAD_SOCIAL_INSURANCE'

            WHEN source_program_code LIKE '10.%'
                THEN 'AGRICULTURE_SUPPORT'

            WHEN source_program_code LIKE '15.%'
                THEN 'INTERIOR_TRIBAL'

            WHEN source_program_code LIKE '20.%'
                THEN 'TRANSPORTATION'

            ELSE 'OTHER_TYPE10_ASSISTANCE'
        END AS inflow_family,

        CASE
            WHEN source_program_code = '96.001'
                THEN 'DISABILITY_INSURANCE'

            WHEN source_program_code = '96.002'
                THEN 'RETIREMENT_INSURANCE'

            WHEN source_program_code = '96.004'
                THEN 'SURVIVORS_INSURANCE'

            WHEN source_program_code = '96.006'
                THEN 'SUPPLEMENTAL_SECURITY_INCOME'

            WHEN source_program_code = '57.001'
                THEN 'RAILROAD_SOCIAL_INSURANCE'

            WHEN source_program_code LIKE '64.%'
                THEN 'VETERANS_PROGRAM'

            WHEN source_program_code LIKE '10.%'
                THEN 'AGRICULTURE_PROGRAM'

            WHEN source_program_code LIKE '15.%'
                THEN 'INTERIOR_TRIBAL_PROGRAM'

            WHEN source_program_code LIKE '20.%'
                THEN 'TRANSPORTATION_PROGRAM'

            ELSE 'UNCLASSIFIED_TYPE10_PROGRAM'
        END AS inflow_subfamily,

        CASE
            WHEN source_program_code LIKE '96.%'
                THEN 'KNOWN_OVERLAP'

            WHEN source_program_code LIKE '64.%'
                THEN 'KNOWN_OVERLAP'

            WHEN source_program_code LIKE '57.%'
                THEN 'KNOWN_OVERLAP'

            WHEN source_program_code LIKE '10.%'
                THEN 'MODERATE'

            WHEN source_program_code LIKE '15.%'
                THEN 'MODERATE'

            WHEN source_program_code LIKE '20.%'
                THEN 'MODERATE'

            ELSE 'HIGH'
        END AS overlap_risk,

        covid_relevance,
        extraordinary_relevance,

        first_fiscal_year,
        last_fiscal_year

    FROM observed_type10
)

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

SELECT
    'USASPENDING_ASSISTANCE',

    source_program_code,
    source_program_title,

    inflow_family,
    inflow_subfamily,

    overlap_risk,

    covid_relevance,
    extraordinary_relevance,

    (
        'Observed in certified Washington USAspending Assistance Type 10. '
        || 'Broad inflow family assigned from Assistance Listing prefix; '
        || 'classification describes program identity and overlap risk only. '
        || 'No authoritative ledger source is selected by this record.'
    ),

    'ANALYSIS-116-v1',

    first_fiscal_year,
    last_fiscal_year

FROM classified

ON CONFLICT (
    source_system,
    source_program_code,
    methodology_version
)

DO UPDATE SET
    source_program_title =
        EXCLUDED.source_program_title,

    inflow_family =
        EXCLUDED.inflow_family,

    inflow_subfamily =
        EXCLUDED.inflow_subfamily,

    overlap_risk =
        EXCLUDED.overlap_risk,

    covid_relevance =
        EXCLUDED.covid_relevance,

    extraordinary_relevance =
        EXCLUDED.extraordinary_relevance,

    classification_basis =
        EXCLUDED.classification_basis,

    valid_from_fiscal_year =
        EXCLUDED.valid_from_fiscal_year,

    valid_through_fiscal_year =
        EXCLUDED.valid_through_fiscal_year,

    updated_at =
        CURRENT_TIMESTAMP;


-- ============================================================================
-- 2. VALIDATION
-- ============================================================================

DO $$
DECLARE
    observed_program_count BIGINT;
    classified_program_count BIGINT;
    unclassified_program_count BIGINT;
BEGIN

    SELECT COUNT(DISTINCT cfda_number)
    INTO observed_program_count
    FROM analysis.v_assistance_geographic_attribution
    WHERE geographic_attribution_class IN (
        'WA_COUNTY',
        'WA_UNSPECIFIED',
        'GEOGRAPHY_CONFLICT'
    )
      AND assistance_type_code = '10'
      AND NULLIF(BTRIM(cfda_number), '') IS NOT NULL;


    SELECT COUNT(*)
    INTO classified_program_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-116-v1';


    SELECT COUNT(*)
    INTO unclassified_program_count
    FROM reference.federal_inflow_program_classification
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND methodology_version = 'ANALYSIS-116-v1'
      AND (
          inflow_family IS NULL
          OR inflow_subfamily IS NULL
          OR overlap_risk IS NULL
      );


    IF classified_program_count <> observed_program_count THEN
        RAISE EXCEPTION
            'Type-10 classification count mismatch: observed=%, classified=%',
            observed_program_count,
            classified_program_count;
    END IF;


    IF unclassified_program_count <> 0 THEN
        RAISE EXCEPTION
            '% Type-10 programs remain incompletely classified.',
            unclassified_program_count;
    END IF;

END
$$;


COMMIT;