BEGIN;

-- ============================================================================
-- PRESERVE OBSERVED USAspending AGENCY IDENTIFIERS
-- ============================================================================

ALTER TABLE procurement.award
    ADD COLUMN IF NOT EXISTS awarding_agency_code TEXT,
    ADD COLUMN IF NOT EXISTS awarding_agency_name TEXT,
    ADD COLUMN IF NOT EXISTS awarding_subagency_code TEXT,
    ADD COLUMN IF NOT EXISTS awarding_subagency_name TEXT,
    ADD COLUMN IF NOT EXISTS awarding_office_code TEXT,
    ADD COLUMN IF NOT EXISTS awarding_office_name TEXT,
    ADD COLUMN IF NOT EXISTS funding_agency_code TEXT,
    ADD COLUMN IF NOT EXISTS funding_agency_name TEXT,
    ADD COLUMN IF NOT EXISTS funding_subagency_code TEXT,
    ADD COLUMN IF NOT EXISTS funding_subagency_name TEXT,
    ADD COLUMN IF NOT EXISTS funding_office_code TEXT,
    ADD COLUMN IF NOT EXISTS funding_office_name TEXT;

COMMENT ON COLUMN procurement.award.awarding_agency_code IS
    'USAspending source awarding-agency code as observed in the export.';

COMMENT ON COLUMN procurement.award.funding_agency_code IS
    'USAspending source funding-agency code as observed in the export.';


-- ============================================================================
-- PRESERVE TRANSACTION-LEVEL RECIPIENT
-- ============================================================================

ALTER TABLE procurement.award_transaction
    ADD COLUMN IF NOT EXISTS recipient_id BIGINT,
    ADD COLUMN IF NOT EXISTS action_type_code TEXT,
    ADD COLUMN IF NOT EXISTS action_type_description TEXT,
    ADD COLUMN IF NOT EXISTS transaction_number TEXT,
    ADD COLUMN IF NOT EXISTS usaspending_permalink TEXT,
    ADD COLUMN IF NOT EXISTS initial_report_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS last_modified_date TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE procurement.award_transaction
    ADD CONSTRAINT fk_procurement_transaction_recipient
    FOREIGN KEY (recipient_id)
    REFERENCES procurement.recipient(recipient_id);

CREATE INDEX IF NOT EXISTS idx_procurement_transaction_recipient
    ON procurement.award_transaction (recipient_id);

COMMENT ON COLUMN procurement.award_transaction.recipient_id IS
    'Recipient reported on the individual USAspending transaction; may differ across an award history.';

COMMENT ON COLUMN procurement.award_transaction.usaspending_transaction_id IS
    'USAspending contract_transaction_unique_key. This is the stable transaction-level source identifier.';

COMMENT ON COLUMN procurement.award.generated_unique_award_id IS
    'USAspending contract_award_unique_key. This is preferred over PIID as the globally stable award identifier.';

COMMENT ON COLUMN procurement.award_transaction.usaspending_permalink IS
    'USAspending award permalink. This is not a transaction-unique identifier.';


-- ============================================================================
-- PRESERVE OBSERVED TRANSACTION-LEVEL PERFORMANCE DETAILS
-- ============================================================================

ALTER TABLE procurement.place_of_performance
    ADD COLUMN IF NOT EXISTS county_fips TEXT,
    ADD COLUMN IF NOT EXISTS state_fips TEXT,
    ADD COLUMN IF NOT EXISTS country_name TEXT,
    ADD COLUMN IF NOT EXISTS state_name TEXT,
    ADD COLUMN IF NOT EXISTS county_name TEXT,
    ADD COLUMN IF NOT EXISTS congressional_district_original TEXT,
    ADD COLUMN IF NOT EXISTS congressional_district_current TEXT;

COMMENT ON COLUMN procurement.place_of_performance.county_fips IS
    'USAspending prime_award_transaction_place_of_performance_county_fips_code.';

COMMENT ON COLUMN procurement.place_of_performance.state_fips IS
    'USAspending prime_award_transaction_place_of_performance_state_fips_code.';


-- ============================================================================
-- SUPPORT SOURCE-CODE SEARCHES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_procurement_award_awarding_agency_code
    ON procurement.award (awarding_agency_code);

CREATE INDEX IF NOT EXISTS idx_procurement_award_awarding_subagency_code
    ON procurement.award (awarding_subagency_code);

CREATE INDEX IF NOT EXISTS idx_procurement_award_funding_agency_code
    ON procurement.award (funding_agency_code);

CREATE INDEX IF NOT EXISTS idx_procurement_award_funding_subagency_code
    ON procurement.award (funding_subagency_code);

CREATE INDEX IF NOT EXISTS idx_procurement_place_county_fips
    ON procurement.place_of_performance (county_fips);

CREATE INDEX IF NOT EXISTS idx_procurement_place_state_fips
    ON procurement.place_of_performance (state_fips);

COMMIT;