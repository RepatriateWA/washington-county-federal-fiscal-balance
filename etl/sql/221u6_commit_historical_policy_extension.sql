\set ON_ERROR_STOP on
\pset pager off

BEGIN;

LOCK TABLE
    reference.federal_inflow_source_policy,
    reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

\echo 'ETL-221U6 - HISTORICAL POLICY EXTENSION'
\echo 'FY2018-FY2019 - CONTROLLED DATABASE MIGRATION'

CREATE TEMP TABLE etl221u6_candidates
ON COMMIT DROP AS
SELECT p.*
FROM reference.federal_inflow_program_policy_mapping p
WHERE p.source_system = 'USASPENDING_ASSISTANCE'
  AND p.valid_from_fiscal_year = 2020
  AND p.source_program_code <> '86.001'
  AND EXISTS (
      SELECT 1
      FROM analysis.v_certified_assistance_ledger t
      WHERE t.load_batch_id IN (20, 21)
        AND t.cfda_number = p.source_program_code
  )
  AND NOT EXISTS (
      SELECT 1
      FROM reference.federal_inflow_program_policy_mapping old
      WHERE old.source_system = p.source_system
        AND old.source_program_code = p.source_program_code
        AND COALESCE(old.valid_from_fiscal_year, -9999) <= 2019
        AND COALESCE(old.valid_through_fiscal_year, 9999) >= 2018
  );

DO $$
DECLARE
    v_total integer;
    v_sources integer;
    v_add integer;
    v_exclude integer;
    v_reference integer;
    v_withhold integer;
BEGIN
    SELECT COUNT(*),
           COUNT(DISTINCT federal_inflow_source_policy_id),
           COUNT(*) FILTER (
               WHERE resolved_accounting_disposition = 'INCLUDE_ADDITIVE'),
           COUNT(*) FILTER (
               WHERE resolved_accounting_disposition = 'EXCLUDE_DUPLICATE'),
           COUNT(*) FILTER (
               WHERE resolved_accounting_disposition = 'REFERENCE_ONLY'),
           COUNT(*) FILTER (
               WHERE resolved_accounting_disposition = 'WITHHOLD_UNRESOLVED')
    INTO v_total, v_sources, v_add, v_exclude,
         v_reference, v_withhold
    FROM etl221u6_candidates;

    IF v_total <> 33
       OR v_sources <> 17
       OR v_add <> 14
       OR v_exclude <> 7
       OR v_reference <> 3
       OR v_withhold <> 9
    THEN
        RAISE EXCEPTION
            'ETL-221U6 candidate population differs from certified gate';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reference.federal_inflow_source_policy
        WHERE methodology_version LIKE 'ANALYSIS-221U-HIST-v1%'
    ) OR EXISTS (
        SELECT 1
        FROM reference.federal_inflow_program_policy_mapping
        WHERE methodology_version = 'ANALYSIS-221U-HIST-v1'
    ) THEN
        RAISE EXCEPTION
            'ETL-221U6 historical methodology already exists';
    END IF;

    RAISE NOTICE 'ETL-221U6 PRE-MIGRATION CONTROLS PASS';
END $$;

\echo '1. INSERT HISTORICAL SOURCE POLICIES'

INSERT INTO reference.federal_inflow_source_policy (
    inflow_family,
    inflow_subfamily,
    accounting_measure,
    preferred_source,
    allocation_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    s.inflow_family,
    s.inflow_subfamily,
    s.accounting_measure,
    s.preferred_source,
    s.allocation_source,
    s.overlapping_sources,
    s.ledger_treatment,
    s.source_selection_basis
        || E'\n\nETL-221U6 HISTORICAL EXTENSION:'
        || ' FY2018-FY2019 only.'
        || ' Original source policy ID: '
        || s.federal_inflow_source_policy_id::text
        || '. Historical authorization is separately'
        || ' scoped and based on ETL-221R through'
        || ' ETL-221U5 program continuity,'
        || ' overlap-risk classification, and'
        || ' historical transaction evidence.'
        || ' Later-period empirical amounts are'
        || ' not imputed into historical years.'
        || ' USAspending obligation measures'
        || ' remain distinct from cash expenditures.'
        || ' Unresolved programs remain withheld.',
    'ANALYSIS-221U-HIST-v1-SRC-'
        || s.federal_inflow_source_policy_id::text,
    2018,
    2019
FROM reference.federal_inflow_source_policy s
WHERE s.federal_inflow_source_policy_id IN (
    SELECT DISTINCT federal_inflow_source_policy_id
    FROM etl221u6_candidates
);

\echo '2. INSERT HISTORICAL PROGRAM MAPPINGS'

INSERT INTO reference.federal_inflow_program_policy_mapping (
    source_system,
    source_program_code,
    federal_inflow_source_policy_id,
    resolved_accounting_disposition,
    mapping_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    c.source_system,
    c.source_program_code,
    historical.federal_inflow_source_policy_id,
    c.resolved_accounting_disposition,
    c.mapping_basis
        || ' ETL-221U6: FY2018-FY2019'
        || ' historical classification extension.'
        || ' Original later methodology: '
        || c.methodology_version
        || '. Original mapping ID: '
        || c.federal_inflow_program_policy_mapping_id::text
        || '. Historical obligations and'
        || ' overlap risks reviewed under'
        || ' ETL-221R through ETL-221U5.'
        || ' County incidence is not inferred.',
    'ANALYSIS-221U-HIST-v1',
    2018,
    2019
FROM etl221u6_candidates c
JOIN reference.federal_inflow_source_policy historical
  ON historical.methodology_version =
     'ANALYSIS-221U-HIST-v1-SRC-'
     || c.federal_inflow_source_policy_id::text
 AND historical.valid_from_fiscal_year = 2018
 AND historical.valid_through_fiscal_year = 2019;

\echo '3. POST-MIGRATION CERTIFICATION'

DO $$
DECLARE
    v_sources integer;
    v_mappings integer;
    v_bad_links integer;
    v_overlaps integer;
BEGIN
    SELECT COUNT(*)
    INTO v_sources
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version LIKE
          'ANALYSIS-221U-HIST-v1-SRC-%'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-221U-HIST-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*)
    INTO v_bad_links
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.methodology_version = 'ANALYSIS-221U-HIST-v1'
      AND (
          s.valid_from_fiscal_year <> 2018
          OR s.valid_through_fiscal_year <> 2019
          OR s.methodology_version NOT LIKE
             'ANALYSIS-221U-HIST-v1-SRC-%'
      );

    SELECT COUNT(*)
    INTO v_overlaps
    FROM reference.federal_inflow_program_policy_mapping a
    JOIN reference.federal_inflow_program_policy_mapping b
      ON b.source_system = a.source_system
     AND b.source_program_code = a.source_program_code
     AND b.federal_inflow_program_policy_mapping_id <>
         a.federal_inflow_program_policy_mapping_id
     AND COALESCE(b.valid_from_fiscal_year, -9999) <= 2019
     AND COALESCE(b.valid_through_fiscal_year, 9999) >= 2018
    WHERE a.methodology_version = 'ANALYSIS-221U-HIST-v1';

    IF v_sources <> 17
       OR v_mappings <> 33
       OR v_bad_links <> 0
       OR v_overlaps <> 0
    THEN
        RAISE EXCEPTION
            'ETL-221U6 POST-MIGRATION FAILURE: sources %, mappings %, bad links %, overlaps %',
            v_sources, v_mappings, v_bad_links, v_overlaps;
    END IF;

    RAISE NOTICE
        'ETL-221U6 POST-MIGRATION CONTROLS PASS: 17 source policies, 33 mappings, zero bad links, zero overlaps';
END $$;

COMMIT;

\echo 'ETL-221U6 COMPLETE'