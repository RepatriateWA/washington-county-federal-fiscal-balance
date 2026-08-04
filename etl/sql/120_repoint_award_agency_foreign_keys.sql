-- Repoint procurement.award agency relationships to the canonical
-- procurement.agency hierarchy populated from USAspending.
--
-- The award enrichment loader resolves agency and subagency IDs from
-- procurement.agency. The original constraints referenced the older
-- reference.federal_agency dimension, causing valid procurement.agency
-- identifiers to fail foreign-key validation.

BEGIN;

ALTER TABLE procurement.award
    DROP CONSTRAINT IF EXISTS
        fk_procurement_award_awarding_agency,

    DROP CONSTRAINT IF EXISTS
        fk_procurement_award_awarding_subagency,

    DROP CONSTRAINT IF EXISTS
        fk_procurement_award_funding_agency,

    DROP CONSTRAINT IF EXISTS
        fk_procurement_award_funding_subagency;


ALTER TABLE procurement.award
    ADD CONSTRAINT fk_procurement_award_awarding_agency
        FOREIGN KEY (awarding_agency_id)
        REFERENCES procurement.agency(agency_id),

    ADD CONSTRAINT fk_procurement_award_awarding_subagency
        FOREIGN KEY (awarding_subagency_id)
        REFERENCES procurement.agency(agency_id),

    ADD CONSTRAINT fk_procurement_award_funding_agency
        FOREIGN KEY (funding_agency_id)
        REFERENCES procurement.agency(agency_id),

    ADD CONSTRAINT fk_procurement_award_funding_subagency
        FOREIGN KEY (funding_subagency_id)
        REFERENCES procurement.agency(agency_id);

COMMIT;