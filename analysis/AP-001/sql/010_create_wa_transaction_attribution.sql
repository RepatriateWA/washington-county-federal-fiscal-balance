BEGIN;

CREATE OR REPLACE VIEW analysis.v_assistance_geographic_attribution AS
SELECT
    l.*,
    CASE
        WHEN l.place_identity_key = '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN 'GEOGRAPHY_CONFLICT'
        WHEN l.reference_state_abbreviation = 'WA'
         AND l.reference_county_id IS NOT NULL
            THEN 'WA_COUNTY'
        WHEN l.reference_state_abbreviation = 'WA'
            THEN 'WA_UNSPECIFIED'
        ELSE 'NON_WASHINGTON'
    END AS geographic_attribution_class,

    CASE
        WHEN l.place_identity_key = '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN 'DQ-001_STATE_ZIP_CONFLICT'
        WHEN l.reference_state_abbreviation = 'WA'
         AND l.reference_county_id IS NOT NULL
            THEN 'REFERENCE_STATE_AND_COUNTY_MATCH'
        WHEN l.reference_state_abbreviation = 'WA'
         AND l.place_source_condition = 'WASHINGTON_UNSPECIFIED'
            THEN 'SOURCE_CONDITION_WASHINGTON_UNSPECIFIED'
        WHEN l.reference_state_abbreviation = 'WA'
            THEN 'WASHINGTON_COUNTY_UNRESOLVED'
        ELSE 'NOT_WASHINGTON'
    END AS geographic_attribution_reason,

    CASE
        WHEN l.place_identity_key = '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN FALSE
        WHEN l.reference_state_abbreviation = 'WA'
            THEN TRUE
        ELSE FALSE
    END AS is_washington_attributed,

    CASE
        WHEN l.reference_state_abbreviation = 'WA'
         AND l.reference_county_id IS NOT NULL
         AND l.place_identity_key <> '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN TRUE
        ELSE FALSE
    END AS is_washington_county_attributed,

    CASE
        WHEN l.place_identity_key = '3:USA|2:53|-1:|8:LEWISTON|5:83501'
            THEN TRUE
        ELSE FALSE
    END AS is_geography_conflict
FROM analysis.v_certified_assistance_ledger l;

COMMENT ON VIEW analysis.v_assistance_geographic_attribution IS
    'AP-001B certified national Assistance geographic attribution view. Every certified transaction receives exactly one of WA_COUNTY, WA_UNSPECIFIED, GEOGRAPHY_CONFLICT, or NON_WASHINGTON. DQ-001 Lewiston state/ZIP conflicts are explicitly excluded from ordinary Washington attribution.';

CREATE OR REPLACE VIEW analysis.v_wa_transactions AS
SELECT *
FROM analysis.v_assistance_geographic_attribution
WHERE geographic_attribution_class IN ('WA_COUNTY', 'WA_UNSPECIFIED');

COMMENT ON VIEW analysis.v_wa_transactions IS
    'Certified Washington Assistance transaction universe. Includes WA_COUNTY and WA_UNSPECIFIED only; geography conflicts are excluded and separately reportable.';

CREATE OR REPLACE VIEW analysis.v_wa_geography_conflicts AS
SELECT *
FROM analysis.v_assistance_geographic_attribution
WHERE geographic_attribution_class = 'GEOGRAPHY_CONFLICT';

COMMENT ON VIEW analysis.v_wa_geography_conflicts IS
    'Certified Assistance geography conflicts relevant to Washington attribution, including DQ-001 Lewiston state/ZIP conflicts.';

CREATE OR REPLACE VIEW analysis.v_wa_county_transactions AS
SELECT *
FROM analysis.v_assistance_geographic_attribution
WHERE geographic_attribution_class = 'WA_COUNTY';

COMMENT ON VIEW analysis.v_wa_county_transactions IS
    'Certified Washington county-resolved Assistance transactions. Only transactions with a validated Washington county assignment and no geography-conflict condition are included.';

COMMIT;