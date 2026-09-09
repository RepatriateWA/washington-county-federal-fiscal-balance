-- ============================================================================
-- ETL-163 — Add USAspending DEFC AAP reference classification
-- ============================================================================
--
-- Purpose
-- -------
-- Add newly observed USAspending Disaster Emergency Fund Code (DEFC) AAP
-- to reference.extraordinary_funding_code using the established WCFFBP
-- extraordinary-funding reference schema and provenance conventions.
--
-- Discovery evidence
-- ------------------
-- Assistance load batch 19 produced:
--   defc_code .................... AAP
--   observation_count ............ 253
--   transaction_count ............ 253
--   distinct_description_count ... 1
--   observed_description ......... Disaster P.L. 119-86
--
-- WCFFBP classification
-- ---------------------
-- AAP is disaster-designated funding and is classified consistently with
-- existing disaster DEFCs H, S, and Y:
--
--   official_description = Disaster P.L. 119-86
--   public_law_reference = P.L. 119-86
--   funding_family       = OTHER_DISASTER
--   extraordinary_flag  = TRUE
--   covid_flag           = FALSE
--   iija_flag            = FALSE
--   confidence           = HIGH
--
-- Classification provenance follows the established reference-table pattern
-- for disaster-designated DEFCs.
--
-- Idempotency / fail-closed behavior
-- ----------------------------------
-- * Insert AAP only if absent.
-- * If AAP already exists with the exact expected classification/provenance,
--   do nothing.
-- * If AAP exists with conflicting values, raise an exception.
--
-- After successful execution, rerun:
--   python -m etl.loaders.link_assistance_extraordinary_funding --load-batch-id 19
--
-- Expected improvement:
--   Unknown code observations ...... 0
--   Distinct unknown DEFC codes .... 0
-- ============================================================================

BEGIN;

INSERT INTO reference.extraordinary_funding_code (
    defc_code,
    official_description,
    public_law_reference,
    funding_family,
    extraordinary_flag,
    covid_flag,
    iija_flag,
    confidence,
    classification_source,
    citation,
    notes
)
SELECT
    'AAP',
    'Disaster P.L. 119-86',
    'P.L. 119-86',
    'OTHER_DISASTER',
    TRUE,
    FALSE,
    FALSE,
    'HIGH',
    'USAspending source domain description; Treasury DEFC definition',
    'https://tfx.treasury.gov/taxonomy/term/16131',
    'Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'
WHERE NOT EXISTS (
    SELECT 1
    FROM reference.extraordinary_funding_code
    WHERE defc_code = 'AAP'
);

DO $$
DECLARE
    v_count integer;
    v_matching integer;
BEGIN
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE official_description = 'Disaster P.L. 119-86'
              AND public_law_reference = 'P.L. 119-86'
              AND funding_family = 'OTHER_DISASTER'
              AND extraordinary_flag IS TRUE
              AND covid_flag IS FALSE
              AND iija_flag IS FALSE
              AND confidence = 'HIGH'
              AND classification_source =
                  'USAspending source domain description; Treasury DEFC definition'
              AND citation = 'https://tfx.treasury.gov/taxonomy/term/16131'
              AND notes =
                  'Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'
        )
    INTO
        v_count,
        v_matching
    FROM reference.extraordinary_funding_code
    WHERE defc_code = 'AAP';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'ETL-163 validation failed: expected exactly one AAP row, found %',
            v_count;
    END IF;

    IF v_matching <> 1 THEN
        RAISE EXCEPTION
            'ETL-163 validation failed: AAP row conflicts with the expected WCFFBP classification/provenance';
    END IF;
END
$$;

COMMIT;

SELECT
    extraordinary_funding_code_id,
    defc_code,
    official_description,
    public_law_reference,
    funding_family,
    extraordinary_flag,
    covid_flag,
    iija_flag,
    confidence,
    classification_source,
    citation,
    notes
FROM reference.extraordinary_funding_code
WHERE defc_code = 'AAP';
