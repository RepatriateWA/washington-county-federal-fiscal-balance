\set ON_ERROR_STOP on
\pset pager off

\echo 'ETL-221U6B - PROGRAM MAPPING SEQUENCE REPAIR'

BEGIN;

LOCK TABLE reference.federal_inflow_program_policy_mapping
IN ACCESS EXCLUSIVE MODE;

DO $$
DECLARE
    v_seq regclass;
    v_max_id bigint;
    v_last_value bigint;
    v_is_called boolean;
    v_increment bigint;
    v_next_value bigint;
    v_target bigint;
BEGIN
    SELECT pg_get_serial_sequence(
        'reference.federal_inflow_program_policy_mapping',
        'federal_inflow_program_policy_mapping_id'
    )::regclass
    INTO v_seq;

    IF v_seq IS NULL THEN
        RAISE EXCEPTION 'No associated mapping sequence found';
    END IF;

    SELECT MAX(federal_inflow_program_policy_mapping_id)
    INTO v_max_id
    FROM reference.federal_inflow_program_policy_mapping;

    SELECT seqincrement
    INTO v_increment
    FROM pg_sequence
    WHERE seqrelid = v_seq;

    IF v_increment <> 1 THEN
        RAISE EXCEPTION
            'Unexpected sequence increment: %', v_increment;
    END IF;

    EXECUTE format(
        'SELECT last_value, is_called FROM %s',
        v_seq
    )
    INTO v_last_value, v_is_called;

    v_next_value :=
        v_last_value + CASE WHEN v_is_called THEN 1 ELSE 0 END;

    v_target := GREATEST(
        COALESCE(v_max_id, 0) + 1,
        v_next_value
    );

    IF v_target > v_next_value THEN
        PERFORM setval(v_seq, v_target, false);

        RAISE NOTICE
            'Sequence advanced: next ID % -> %; table max ID %',
            v_next_value, v_target, v_max_id;
    ELSE
        RAISE NOTICE
            'Sequence already safe: next ID %, table max ID %',
            v_next_value, v_max_id;
    END IF;
END $$;

COMMIT;

\echo 'ETL-221U6B COMPLETE'