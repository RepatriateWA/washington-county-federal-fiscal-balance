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
VALUES
    ('4','Disaster P.L. 117-103','P.L. 117-103','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'),
    ('6','Emergency P.L. 117-128','P.L. 117-128','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('AAB','Emergency P.L. 117-328','P.L. 117-328','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('AAC','Wildfire Suppression P.L. 117-328','P.L. 117-328','WILDFIRE_SUPPRESSION',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; wildfire-suppression-designated funding. Not classified as COVID or IIJA.'),
    ('AAD','Disaster P.L. 117-328','P.L. 117-328','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'),
    ('AAE','Emergency P.L. 118-15','P.L. 118-15','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('AAI','Disaster P.L. 118-47','P.L. 118-47','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'),
    ('AAK','Emergency P.L. 118-158','P.L. 118-158','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('AAL','Emergency P.L. 119-4','P.L. 119-4','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('AAM','Wildfire Suppression P.L. 119-74','P.L. 119-74','WILDFIRE_SUPPRESSION',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; wildfire-suppression-designated funding. Not classified as COVID or IIJA.'),
    ('B','Emergency P.L. 115-72','P.L. 115-72','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('C','Emergency P.L. 115-123','P.L. 115-123','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('E','Emergency P.L. 116-20','P.L. 116-20','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('F','Emergency P.L. 116-26','P.L. 116-26','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('H','Disaster P.L. 116-93','P.L. 116-93','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.'),
    ('J','Wildfire Suppression P.L. 116-94','P.L. 116-94','WILDFIRE_SUPPRESSION',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; wildfire-suppression-designated funding. Not classified as COVID or IIJA.'),
    ('S','Disaster P.L. 116-260','P.L. 116-260','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Distinct from DEFC U, which is COVID-related emergency funding under the same public law.'),
    ('X','Emergency P.L. 117-43','P.L. 117-43','OTHER_EMERGENCY',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; emergency-designated funding. Not classified as COVID or IIJA.'),
    ('Y','Disaster P.L. 117-43','P.L. 117-43','OTHER_DISASTER',TRUE,FALSE,FALSE,'HIGH','USAspending source domain description; Treasury DEFC definition','https://tfx.treasury.gov/taxonomy/term/16131','Observed in USAspending Assistance source data; disaster-designated funding. Not classified as COVID or IIJA.')
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

DO $$
DECLARE
    expected_count INTEGER := 19;
    actual_count INTEGER;
    invalid_flag_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO actual_count
    FROM reference.extraordinary_funding_code
    WHERE defc_code IN (
        '4','6','AAB','AAC','AAD','AAE','AAI','AAK','AAL','AAM',
        'B','C','E','F','H','J','S','X','Y'
    );

    IF actual_count <> expected_count THEN
        RAISE EXCEPTION
            'Migration 129 validation failed: expected % DEFC rows, found %.',
            expected_count, actual_count;
    END IF;

    SELECT COUNT(*)
    INTO invalid_flag_count
    FROM reference.extraordinary_funding_code
    WHERE defc_code IN (
        '4','6','AAB','AAC','AAD','AAE','AAI','AAK','AAL','AAM',
        'B','C','E','F','H','J','S','X','Y'
    )
      AND (
          extraordinary_flag IS DISTINCT FROM TRUE
          OR covid_flag IS DISTINCT FROM FALSE
          OR iija_flag IS DISTINCT FROM FALSE
      );

    IF invalid_flag_count <> 0 THEN
        RAISE EXCEPTION
            'Migration 129 validation failed: % rows have unexpected extraordinary/COVID/IIJA flags.',
            invalid_flag_count;
    END IF;
END
$$;

COMMIT;