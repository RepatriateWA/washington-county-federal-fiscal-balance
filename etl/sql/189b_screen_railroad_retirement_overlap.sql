/*
====================================================================================================
ETL-189B
RAILROAD RETIREMENT / SSA-OASDI OVERLAP SCREEN
====================================================================================================

Purpose:
    Determine whether WCFFBP already contains an accounting pathway
    capable of capturing Railroad Retirement Board benefit payments.

No writes.
====================================================================================================
*/

\echo ''
\echo '===================================================================================================='
\echo 'ETL-189B - RAILROAD RETIREMENT / SSA-OASDI OVERLAP SCREEN'
\echo '===================================================================================================='


/*
----------------------------------------------------------------------------------------------------
1. EXISTING SOCIAL-INSURANCE SOURCE POLICIES
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '1. EXISTING SOCIAL-INSURANCE SOURCE POLICIES'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_source_policy_id,
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

FROM reference.federal_inflow_source_policy

WHERE
       UPPER(COALESCE(inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(preferred_source, '')) LIKE '%SSA%'
    OR UPPER(COALESCE(source_selection_basis, '')) LIKE '%SOCIAL SECURITY%'
    OR UPPER(COALESCE(source_selection_basis, '')) LIKE '%RAILROAD%'

ORDER BY federal_inflow_source_policy_id;


/*
----------------------------------------------------------------------------------------------------
2. EXISTING PROGRAM CLASSIFICATIONS RELEVANT TO SSA / RRB / RETIREMENT
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '2. EXISTING PROGRAM CLASSIFICATIONS RELEVANT TO SSA / RRB / RETIREMENT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year

FROM reference.federal_inflow_program_classification

WHERE
       UPPER(COALESCE(source_program_title, '')) LIKE '%SOCIAL SECURITY%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%RETIREMENT%'
    OR UPPER(COALESCE(source_program_title, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(inflow_family, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RETIRE%'

ORDER BY
    source_system,
    source_program_code,
    federal_inflow_program_classification_id;


/*
----------------------------------------------------------------------------------------------------
3. EXISTING PROGRAM-POLICY MAPPINGS FOR SSA-LIKE PROGRAMS
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '3. EXISTING PROGRAM-POLICY MAPPINGS FOR SSA-LIKE PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,

    p.federal_inflow_source_policy_id,
    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.accounting_measure,
    p.overlapping_sources,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
    ON p.federal_inflow_source_policy_id
       = m.federal_inflow_source_policy_id

WHERE
       UPPER(COALESCE(p.preferred_source, '')) LIKE '%SSA%'
    OR UPPER(COALESCE(p.inflow_family, '')) LIKE '%SOCIAL%'
    OR UPPER(COALESCE(p.inflow_subfamily, '')) LIKE '%OASDI%'
    OR UPPER(COALESCE(p.inflow_subfamily, '')) LIKE '%RETIRE%'
    OR UPPER(COALESCE(m.mapping_basis, '')) LIKE '%SOCIAL SECURITY%'
    OR UPPER(COALESCE(m.mapping_basis, '')) LIKE '%RAILROAD%'

ORDER BY
    m.source_system,
    m.source_program_code,
    m.federal_inflow_program_policy_mapping_id;


/*
----------------------------------------------------------------------------------------------------
4. DIRECT SEARCH FOR RAILROAD TERMINOLOGY ACROSS POLICY TEXT
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '4. DIRECT RAILROAD TERMINOLOGY SEARCH'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_source_policy_id,
    inflow_family,
    inflow_subfamily,
    preferred_source,
    overlapping_sources,
    ledger_treatment,
    source_selection_basis,
    methodology_version

FROM reference.federal_inflow_source_policy

WHERE
       UPPER(COALESCE(inflow_family, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(inflow_subfamily, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(preferred_source, '')) LIKE '%RAILROAD%'
    OR UPPER(COALESCE(array_to_string(overlapping_sources, ' '), ''))
           LIKE '%RAILROAD%'
    OR UPPER(COALESCE(source_selection_basis, '')) LIKE '%RAILROAD%'

ORDER BY federal_inflow_source_policy_id;


/*
----------------------------------------------------------------------------------------------------
5. DIRECT SEARCH FOR RAILROAD PROGRAM CLASSIFICATION
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '5. DIRECT RAILROAD PROGRAM CLASSIFICATION SEARCH'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    federal_inflow_program_classification_id,
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    classification_basis,
    methodology_version

FROM reference.federal_inflow_program_classification

WHERE source_program_code = '57.001'
   OR UPPER(COALESCE(source_program_title, '')) LIKE '%RAILROAD%'
   OR UPPER(COALESCE(classification_basis, '')) LIKE '%RAILROAD%'

ORDER BY federal_inflow_program_classification_id;


/*
----------------------------------------------------------------------------------------------------
6. EXISTING 57.001 POLICY MAPPING CHECK
----------------------------------------------------------------------------------------------------
*/

\echo ''
\echo '6. EXISTING 57.001 POLICY MAPPING CHECK'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    m.federal_inflow_program_policy_mapping_id,
    m.source_system,
    m.source_program_code,
    m.resolved_accounting_disposition,
    m.mapping_basis,
    m.methodology_version,

    p.inflow_family,
    p.inflow_subfamily,
    p.preferred_source,
    p.accounting_measure,
    p.overlapping_sources,
    p.ledger_treatment

FROM reference.federal_inflow_program_policy_mapping m

JOIN reference.federal_inflow_source_policy p
    ON p.federal_inflow_source_policy_id
       = m.federal_inflow_source_policy_id

WHERE m.source_program_code = '57.001'

ORDER BY m.federal_inflow_program_policy_mapping_id;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-189B COMPLETE'
\echo 'Read-only overlap screen.'
\echo 'No database writes.'
\echo '===================================================================================================='