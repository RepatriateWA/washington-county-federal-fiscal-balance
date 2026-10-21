
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo 'ETL-223N2 - FIVE HISTORICAL ADDITIVE PROGRAM POLICIES'
\echo 'WRITE ENABLED - FY2018-FY2019 ONLY'

BEGIN;

LOCK TABLE reference.federal_inflow_source_policy,
           reference.federal_inflow_program_policy_mapping
IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    v_conflicts integer;
    v_sequence text;
BEGIN
    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_program_policy_mapping
    WHERE source_system = 'USASPENDING_ASSISTANCE'
      AND BTRIM(source_program_code) IN
          ('10.557','10.561','10.924','93.527','93.563');

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'Existing target mappings found: %; migration stopped',
            v_conflicts;
    END IF;

    SELECT COUNT(*) INTO v_conflicts
    FROM reference.federal_inflow_source_policy
    WHERE
        (inflow_family, inflow_subfamily) IN (
            ('NUTRITION_ASSISTANCE','WIC'),
            ('NUTRITION_ASSISTANCE','SNAP_STATE_ADMINISTRATION'),
            ('AGRICULTURAL_ASSISTANCE','CONSERVATION_STEWARDSHIP'),
            ('PUBLIC_HEALTH_ASSISTANCE','HEALTH_CENTER_ACA_GRANTS'),
            ('FAMILY_SUPPORT_ASSISTANCE','CHILD_SUPPORT_SERVICES')
        );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            'Existing target source policies found: %; migration stopped',
            v_conflicts;
    END IF;

    SELECT pg_get_serial_sequence(
        'reference.federal_inflow_program_policy_mapping',
        'federal_inflow_program_policy_mapping_id'
    ) INTO v_sequence;

    IF v_sequence IS NULL THEN
        RAISE EXCEPTION
            'Program mapping ID sequence not found';
    END IF;

    RAISE NOTICE 'ETL-223N2 preconditions PASS';
END $$;

WITH proposed (
    program_code, family, subfamily, program_name
) AS (
    VALUES
      ('10.557','NUTRITION_ASSISTANCE','WIC',
       'WIC nutrition grants'),
      ('10.561','NUTRITION_ASSISTANCE','SNAP_STATE_ADMINISTRATION',
       'SNAP state administrative matching grants'),
      ('10.924','AGRICULTURAL_ASSISTANCE','CONSERVATION_STEWARDSHIP',
       'Conservation Stewardship Program'),
      ('93.527','PUBLIC_HEALTH_ASSISTANCE','HEALTH_CENTER_ACA_GRANTS',
       'ACA Health Center Program grants'),
      ('93.563','FAMILY_SUPPORT_ASSISTANCE','CHILD_SUPPORT_SERVICES',
       'Child Support Services')
)
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
    family,
    subfamily,
    'ANNUAL_NET_FEDERAL_ACTION_OBLIGATIONS',
    'USASPENDING_ASSISTANCE',
    'USASPENDING_ASSISTANCE_PERFORMANCE_GEOGRAPHY',
    ARRAY[]::text[],
    'INCLUDE',
    'ETL-223I through ETL-223M: ' || program_name ||
    '. Distinct federal assistance program; no duplicate preferred ' ||
    'source identified in the WCFFBP policy inventory. ' ||
    'Historical FY2018-FY2019 transactions reconcile to the ' ||
    'certified assistance ledger, and raw performance-state FIPS ' ||
    'identifies Washington for all target transactions. ' ||
    'Residual risk: an unregistered broader federal expenditure ' ||
    'source may overlap this program. Obligations are not outlays. ' ||
    'This policy does not authorize double counting, imputation, ' ||
    'or automatic extension beyond FY2019.',
    'ANALYSIS-223N-v1',
    2018,
    2019
FROM proposed;

WITH proposed (
    program_code, family, subfamily
) AS (
    VALUES
      ('10.557','NUTRITION_ASSISTANCE','WIC'),
      ('10.561','NUTRITION_ASSISTANCE','SNAP_STATE_ADMINISTRATION'),
      ('10.924','AGRICULTURAL_ASSISTANCE','CONSERVATION_STEWARDSHIP'),
      ('93.527','PUBLIC_HEALTH_ASSISTANCE','HEALTH_CENTER_ACA_GRANTS'),
      ('93.563','FAMILY_SUPPORT_ASSISTANCE','CHILD_SUPPORT_SERVICES')
)
INSERT INTO reference.federal_inflow_program_policy_mapping (
    federal_inflow_program_policy_mapping_id,
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
    nextval(pg_get_serial_sequence(
        'reference.federal_inflow_program_policy_mapping',
        'federal_inflow_program_policy_mapping_id'
    )),
    'USASPENDING_ASSISTANCE',
    p.program_code,
    s.federal_inflow_source_policy_id,
    'INCLUDE_ADDITIVE',
    'Explicit FY2018-FY2019 historical additive policy. ' ||
    'ETL-223I through ETL-223M; award-specific accounting ' ||
    'classifications retain precedence. Residual overlap ' ||
    'risk documented in source policy.',
    'ANALYSIS-223N-v1',
    2018,
    2019
FROM proposed p
JOIN reference.federal_inflow_source_policy s
  ON s.inflow_family = p.family
 AND s.inflow_subfamily = p.subfamily
 AND s.methodology_version = 'ANALYSIS-223N-v1'
 AND s.valid_from_fiscal_year = 2018
 AND s.valid_through_fiscal_year = 2019;

DO $$
DECLARE
    v_sources integer;
    v_mappings integer;
    v_bad integer;
BEGIN
    SELECT COUNT(*) INTO v_sources
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-223N-v1'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019
      AND ledger_treatment = 'INCLUDE';

    SELECT COUNT(*) INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-223N-v1'
      AND source_system = 'USASPENDING_ASSISTANCE'
      AND resolved_accounting_disposition = 'INCLUDE_ADDITIVE'
      AND valid_from_fiscal_year = 2018
      AND valid_through_fiscal_year = 2019;

    SELECT COUNT(*) INTO v_bad
    FROM reference.federal_inflow_program_policy_mapping p
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         p.federal_inflow_source_policy_id
    WHERE p.methodology_version = 'ANALYSIS-223N-v1'
      AND (
          s.methodology_version <> 'ANALYSIS-223N-v1'
          OR s.valid_from_fiscal_year <> 2018
          OR s.valid_through_fiscal_year <> 2019
          OR s.ledger_treatment <> 'INCLUDE'
      );

    IF v_sources <> 5 OR v_mappings <> 5 OR v_bad <> 0 THEN
        RAISE EXCEPTION
            'Certification failed: sources %, mappings %, invalid %',
            v_sources, v_mappings, v_bad;
    END IF;

    RAISE NOTICE
        'PASS: five source policies and five mappings certified';
END $$;

COMMIT;

\echo 'ETL-223N2 COMPLETE'
