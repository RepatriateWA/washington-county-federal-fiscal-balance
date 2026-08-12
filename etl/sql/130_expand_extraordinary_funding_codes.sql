BEGIN;

-- ============================================================================
-- Migration 130
-- Expand reference.extraordinary_funding_code using RP-002 approved
-- classifications for DEFC values observed in USAspending Assistance data.
--
-- Source package:
--   evidence/assistance/deferred_reference_reconciliation/
--       RP-002_research_notes.md
--       RP-002_classification_matrix.xlsx
--       RP-002_recommendation.md
--
-- Methodology:
--   * Classify at the DEFC-code level.
--   * Do not infer COVID status from Public Law alone.
--   * All 12 RP-002 codes are extraordinary, non-COVID, and non-IIJA.
--   * Upsert by defc_code for idempotent execution.
-- ============================================================================

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
VALUES
    (
        '2',
        'Emergency P.L. 117-70',
        'P.L. 117-70',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        '5',
        'Wildfire Suppression P.L. 117-103',
        'P.L. 117-103',
        'WILDFIRE_SUPPRESSION',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Wildfire-suppression-designated funding; not classified as COVID or IIJA.'
    ),
    (
        '7',
        'Emergency P.L. 117-159',
        'P.L. 117-159',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'A',
        'Emergency P.L. 115-56',
        'P.L. 115-56',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'AAA',
        'Emergency P.L. 117-180',
        'P.L. 117-180',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'AAF',
        'Emergency P.L. 118-42',
        'P.L. 118-42',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'AAJ',
        'Emergency P.L. 118-50',
        'P.L. 118-50',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'I',
        'Emergency P.L. 116-94',
        'P.L. 116-94',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'K',
        'Emergency P.L. 116-113',
        'P.L. 116-113',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    ),
    (
        'R',
        'Emergency P.L. 116-260',
        'P.L. 116-260',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Distinct from DEFC U, which is COVID-related under the same Public Law.'
    ),
    (
        'T',
        'Wildfire Suppression P.L. 116-260',
        'P.L. 116-260',
        'WILDFIRE_SUPPRESSION',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Wildfire-suppression-designated funding; distinct from DEFC U under the same Public Law.'
    ),
    (
        'W',
        'Emergency P.L. 117-31',
        'P.L. 117-31',
        'OTHER_EMERGENCY',
        TRUE,
        FALSE,
        FALSE,
        'HIGH',
        'RP-002; USAspending source description; U.S. Treasury DEFC definition',
        'https://tfx.treasury.gov/taxonomy/term/16131',
        'RP-002 approved classification. Emergency-designated funding; not classified as COVID or IIJA.'
    )
ON CONFLICT (defc_code)
DO UPDATE SET
    official_description = EXCLUDED.official_description,
    public_law_reference = EXCLUDED.public_law_reference,
    funding_family = EXCLUDED.funding_family,
    extraordinary_flag = EXCLUDED.extraordinary_flag,
    covid_flag = EXCLUDED.covid_flag,
    iija_flag = EXCLUDED.iija_flag,
    confidence = EXCLUDED.confidence,
    classification_source = EXCLUDED.classification_source,
    citation = EXCLUDED.citation,
    notes = EXCLUDED.notes,
    updated_at = CURRENT_TIMESTAMP;

-- ============================================================================
-- Validation
-- ============================================================================

DO $$
DECLARE
    expected_count INTEGER := 12;
    actual_count INTEGER;
    invalid_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO actual_count
    FROM reference.extraordinary_funding_code
    WHERE defc_code IN (
        '2','5','7','A','AAA','AAF','AAJ','I','K','R','T','W'
    );

    IF actual_count <> expected_count THEN
        RAISE EXCEPTION
            'Migration 130 validation failed: expected % RP-002 DEFC rows, found %.',
            expected_count,
            actual_count;
    END IF;

    SELECT COUNT(*)
    INTO invalid_count
    FROM reference.extraordinary_funding_code
    WHERE defc_code IN (
        '2','5','7','A','AAA','AAF','AAJ','I','K','R','T','W'
    )
      AND (
          extraordinary_flag IS DISTINCT FROM TRUE
          OR covid_flag IS DISTINCT FROM FALSE
          OR iija_flag IS DISTINCT FROM FALSE
          OR confidence IS DISTINCT FROM 'HIGH'
          OR funding_family IS DISTINCT FROM CASE defc_code
              WHEN '5' THEN 'WILDFIRE_SUPPRESSION'
              WHEN 'T' THEN 'WILDFIRE_SUPPRESSION'
              ELSE 'OTHER_EMERGENCY'
          END
      );

    IF invalid_count <> 0 THEN
        RAISE EXCEPTION
            'Migration 130 validation failed: % RP-002 rows have unexpected classifications.',
            invalid_count;
    END IF;
END
$$;

COMMIT;