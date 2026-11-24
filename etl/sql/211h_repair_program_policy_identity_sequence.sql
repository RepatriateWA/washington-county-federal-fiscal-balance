-- ============================================================
-- ETL-211H
-- Repair program-policy mapping identity sequence
-- Does not modify mapping records
-- ============================================================

\set ON_ERROR_STOP on
\pset pager off

BEGIN;

LOCK TABLE reference.federal_inflow_program_policy_mapping
    IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    v_max_id bigint;
    v_sequence text;
    v_last_value bigint;
    v_is_called boolean;
BEGIN
    SELECT MAX(federal_inflow_program_policy_mapping_id)
    INTO v_max_id
    FROM reference.federal_inflow_program_policy_mapping;

    SELECT pg_get_serial_sequence(
        'reference.federal_inflow_program_policy_mapping',
        'federal_inflow_program_policy_mapping_id'
    )
    INTO v_sequence;

    IF v_sequence IS NULL THEN
        RAISE EXCEPTION 'Identity sequence not found';
    END IF;

    EXECUTE format(
        'SELECT last_value, is_called FROM %s',
        v_sequence
    )
    INTO v_last_value, v_is_called;

    RAISE NOTICE
        'Before repair: sequence %, last_value %, is_called %, maximum table ID %',
        v_sequence, v_last_value, v_is_called, v_max_id;

    IF v_max_id IS NULL THEN
        RAISE EXCEPTION 'Mapping table unexpectedly empty';
    END IF;

    IF v_last_value < v_max_id
       OR (v_last_value = v_max_id AND NOT v_is_called)
    THEN
        PERFORM setval(v_sequence::regclass, v_max_id, true);

        RAISE NOTICE
            'Sequence advanced to %, next generated ID should be %',
            v_max_id, v_max_id + 1;
    ELSE
        RAISE NOTICE
            'Sequence already positioned beyond existing mapping IDs; no repair necessary';
    END IF;
END $$;

COMMIT;

\echo 'ETL-211H IDENTITY SEQUENCE REPAIR COMPLETE'