BEGIN;

ALTER TABLE procurement.place
    ADD COLUMN IF NOT EXISTS place_identity_key TEXT
    GENERATED ALWAYS AS (
        COALESCE(
            LENGTH(country_code)::TEXT
                || ':' || country_code,
            '-1:'
        )
        || '|'
        || COALESCE(
            LENGTH(state_fips)::TEXT
                || ':' || state_fips,
            '-1:'
        )
        || '|'
        || COALESCE(
            LENGTH(county_fips)::TEXT
                || ':' || county_fips,
            '-1:'
        )
        || '|'
        || COALESCE(
            LENGTH(city_name)::TEXT
                || ':' || city_name,
            '-1:'
        )
        || '|'
        || COALESCE(
            LENGTH(zip4)::TEXT
                || ':' || zip4,
            '-1:'
        )
    ) STORED;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_procurement_place_identity_key
ON procurement.place (
    place_identity_key
);

COMMIT;