BEGIN;

DELETE FROM cms.medicaid_service_expenditures
WHERE fiscal_year = 2024
  AND state_id = 48
  AND federal_program_id = 11;

DO $$
DECLARE
    remaining_expenditure_rows INTEGER;
    remaining_control_rows INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO remaining_expenditure_rows
    FROM cms.medicaid_service_expenditures
    WHERE fiscal_year = 2024
      AND state_id = 48
      AND federal_program_id = 11;

    SELECT COUNT(*)
    INTO remaining_control_rows
    FROM cms.medicaid_state_control_total
    WHERE fiscal_year = 2024
      AND state_id = 48
      AND federal_program_id = 11;

    IF remaining_expenditure_rows <> 0 THEN
        RAISE EXCEPTION
            'Expected zero FY2024 curated Medicaid service rows; found %.',
            remaining_expenditure_rows;
    END IF;

    IF remaining_control_rows <> 1 THEN
        RAISE EXCEPTION
            'Expected one FY2024 Medicaid control total; found %.',
            remaining_control_rows;
    END IF;
END
$$;

COMMIT;