
\set ON_ERROR_STOP on
\pset pager off

\echo '============================================================'
\echo 'ETL-211L1 - HISTORICAL VA BENEFIT POLICY EXTENSION'
\echo 'FY2018-FY2019 | ANALYSIS-211L-v1'
\echo 'WRITE ENABLED - CONTROLLED TRANSACTION'
\echo '============================================================'

BEGIN;

-- ============================================================
-- 1. PRE-MIGRATION HARD CONTROLS
-- ============================================================

DO $$
DECLARE
    v_count bigint;
    v_amount numeric;
    v_bad bigint;
    v_precedent bigint;
    v_gdx bigint;
BEGIN
    -- Prevent repeated execution or partial prior installation.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211L-v1')
        +
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211L-v1')
        +
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211L-v1')
    INTO v_count;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-211L1 already installed or partially present';
    END IF;

    -- Verify exact certified historical source population.
    WITH targets(code) AS (
        VALUES
        ('64.104'), ('64.105'), ('64.110'),
        ('64.028'), ('64.032'), ('64.117'),
        ('64.120'), ('64.124')
    )
    SELECT
        COUNT(*),
        COALESCE(SUM(c.federal_action_obligation), 0)
    INTO v_count, v_amount
    FROM analysis.v_certified_assistance_ledger c
    JOIN targets t
      ON t.code = BTRIM(c.cfda_number)
    WHERE
        (c.load_batch_id = 20
         AND c.action_date_fiscal_year = 2018)
        OR
        (c.load_batch_id = 21
         AND c.action_date_fiscal_year = 2019);

    IF v_count <> 5337
       OR ROUND(v_amount, 2) <> 1274305391.00 THEN
        RAISE EXCEPTION
            'Historical population mismatch: rows %, amount %',
            v_count, v_amount;
    END IF;

    -- No overlapping historical program, award, or
    -- descriptive classification records are permitted.
    WITH targets(code) AS (
        VALUES
        ('64.104'), ('64.105'), ('64.110'),
        ('64.028'), ('64.032'), ('64.117'),
        ('64.120'), ('64.124')
    )
    SELECT
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping m
            JOIN targets t ON t.code = m.source_program_code
            WHERE m.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(m.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(m.valid_through_fiscal_year, 9999)
                  >= 2018
        )
        +
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_award_classification a
            JOIN targets t ON t.code = a.source_program_code
            WHERE a.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(a.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(a.valid_through_fiscal_year, 9999)
                  >= 2018
        )
        +
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_classification c
            JOIN targets t ON t.code = c.source_program_code
            WHERE c.source_system = 'USASPENDING_ASSISTANCE'
              AND COALESCE(c.valid_from_fiscal_year, -9999)
                  <= 2019
              AND COALESCE(c.valid_through_fiscal_year, 9999)
                  >= 2018
        )
    INTO v_bad;

    IF v_bad <> 0 THEN
        RAISE EXCEPTION
            'Historical classification/policy collisions: %',
            v_bad;
    END IF;

    -- Verify every later-year precedent is unique and correct.
    WITH targets(code) AS (
        VALUES
        ('64.104'), ('64.105'), ('64.110'),
        ('64.028'), ('64.032'), ('64.117'),
        ('64.120'), ('64.124')
    ),
    program_years AS (
        SELECT t.code, y.fiscal_year
        FROM targets t
        CROSS JOIN generate_series(2020, 2024)
            AS y(fiscal_year)
    ),
    checked AS (
        SELECT
            p.code,
            p.fiscal_year,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                AS mapping_count,
            COUNT(*) FILTER (
                WHERE m.resolved_accounting_disposition =
                          'EXCLUDE_DUPLICATE'
                  AND m.methodology_version =
                          'ANALYSIS-174B-5N-v1'
                  AND s.preferred_source = 'VA_GDX'
                  AND s.ledger_treatment = 'EXCLUDE_DUPLICATE'
            ) AS correct_count
        FROM program_years p
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system = 'USASPENDING_ASSISTANCE'
         AND m.source_program_code = p.code
         AND p.fiscal_year BETWEEN
             COALESCE(m.valid_from_fiscal_year, -9999)
             AND COALESCE(m.valid_through_fiscal_year, 9999)
        LEFT JOIN reference.federal_inflow_source_policy s
          ON s.federal_inflow_source_policy_id =
             m.federal_inflow_source_policy_id
        GROUP BY p.code, p.fiscal_year
    )
    SELECT COUNT(*)
    INTO v_precedent
    FROM checked
    WHERE mapping_count = 1
      AND correct_count = 1;

    IF v_precedent <> 40 THEN
        RAISE EXCEPTION
            'Later-year VA policy precedent failed: % of 40',
            v_precedent;
    END IF;

    -- Independent historical GDX reconciliation.
    SELECT COUNT(*)
    INTO v_gdx
    FROM (
        SELECT
            e.fiscal_year,
            COUNT(*) FILTER (
                WHERE k.aggregation_role = 'CONTROL_TOTAL'
            ) AS control_rows,
            COUNT(*) FILTER (
                WHERE k.aggregation_role = 'COMPONENT'
            ) AS component_rows,
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'COMPONENT'
            ), 0)
            -
            COALESCE(SUM(e.expenditure_amount) FILTER (
                WHERE k.aggregation_role = 'CONTROL_TOTAL'
            ), 0) AS difference
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category k
          ON k.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year IN (2018, 2019)
        GROUP BY e.fiscal_year
    ) q
    WHERE q.control_rows = 39
      AND q.component_rows = 273
      AND ROUND(q.difference, 2) = 0;

    IF v_gdx <> 2 THEN
        RAISE EXCEPTION
            'Historical VA GDX reconciliation failed';
    END IF;

    RAISE NOTICE
        'ETL-211L1 PRE-MIGRATION CONTROLS PASS';
END $$;

-- ============================================================
-- 2. HISTORICAL PROGRAM CLASSIFICATIONS
-- ============================================================

INSERT INTO reference.federal_inflow_program_classification
(
    source_system,
    source_program_code,
    source_program_title,
    inflow_family,
    inflow_subfamily,
    overlap_risk,
    covid_relevance,
    extraordinary_relevance,
    classification_basis,
    methodology_version,
    valid_from_fiscal_year,
    valid_through_fiscal_year
)
SELECT
    'USASPENDING_ASSISTANCE',
    v.program_code,
    v.program_title,
    'VETERANS',
    'VETERANS_PROGRAM',
    'KNOWN_OVERLAP',
    false,
    false,
    'FY2018-FY2019 historical extension of the '
    || 'ANALYSIS-174B-5N-v1 VA GDX benefit-family '
    || 'overlap methodology. Program identity '
    || 'corresponds to the historical VA GDX '
    || v.gdx_family
    || ' component. Historical GDX county controls '
    || 'reconcile exactly; later FY2020-FY2024 '
    || 'program policies consistently prefer VA_GDX. '
    || 'USAspending obligations and VA expenditures '
    || 'are distinct measures. This record identifies '
    || 'overlap risk; accounting disposition is '
    || 'governed by ANALYSIS-211L-v1 source policy.',
    'ANALYSIS-211L-v1',
    2018,
    2019
FROM (
    VALUES
    ('64.104',
     'PENSION FOR NON-SERVICE-CONNECTED DISABILITY FOR VETERANS',
     'COMPENSATION_PENSION'),
    ('64.105',
     'PENSION TO VETERANS SURVIVING SPOUSES, AND CHILDREN',
     'COMPENSATION_PENSION'),
    ('64.110',
     'VETERANS DEPENDENCY AND INDEMNITY COMPENSATION FOR SERVICE-CONNECTED DEATH',
     'COMPENSATION_PENSION'),
    ('64.028',
     'POST-9/11 VETERANS EDUCATIONAL ASSISTANCE',
     'EDUCATION_VRE'),
    ('64.032',
     'MONTGOMERY GI BILL SELECTED RESERVE',
     'EDUCATION_VRE'),
    ('64.117',
     'SURVIVORS AND DEPENDENTS EDUCATIONAL ASSISTANCE',
     'EDUCATION_VRE'),
    ('64.120',
     'POST-VIETNAM ERA VETERANS EDUCATIONAL ASSISTANCE',
     'EDUCATION_VRE'),
    ('64.124',
     'ALL-VOLUNTEER FORCE EDUCATIONAL ASSISTANCE',
     'EDUCATION_VRE')
) AS v(program_code, program_title, gdx_family);

-- ============================================================
-- 3. HISTORICAL VA GDX SOURCE POLICY
-- ============================================================

INSERT INTO reference.federal_inflow_source_policy
(
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
VALUES
(
    'VETERANS_AFFAIRS',
    'VA_GDX_ASSISTANCE_OVERLAP',
    'VA expenditures',
    'VA_GDX',
    'VA_GDX',
    ARRAY['USASPENDING_ASSISTANCE']::text[],
    'EXCLUDE_DUPLICATE',
    'FY2018-FY2019 extension of ANALYSIS-174B-5N-v1 '
    || 'for eight compensation, pension, and education '
    || 'Assistance Listings, excluding AL 64.109 already '
    || 'governed by ANALYSIS-209U-v1. '
    || 'Historical VA GDX reports contain Compensation '
    || '& Pension and Education & Vocational '
    || 'Rehabilitation/Employment expenditure components '
    || 'for all 39 Washington counties. '
    || 'Both years reconcile exactly to GDX controls. '
    || 'FY2020-FY2024 policies for all eight programs '
    || 'select VA_GDX as preferred expenditure and '
    || 'county allocation source. USAspending '
    || 'obligations are retained as transaction-level '
    || 'provenance, not added as a second expenditure '
    || 'stream. No dollar-for-dollar equivalence '
    || 'between obligations and expenditures is assumed. '
    || 'Burial allowances and medical-care programs '
    || 'are explicitly outside this policy.',
    'ANALYSIS-211L-v1',
    2018,
    2019
);

-- ============================================================
-- 4. HISTORICAL PROGRAM-POLICY MAPPINGS
-- ============================================================

INSERT INTO reference.federal_inflow_program_policy_mapping
(
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
    nextval(
        'reference.federal_inflow_program_policy_federal_inflow_program_policy_seq'
    ),
    'USASPENDING_ASSISTANCE',
    t.program_code,
    p.federal_inflow_source_policy_id,
    'EXCLUDE_DUPLICATE',
    'FY2018-FY2019 historical VA GDX benefit '
    || 'overlap reconciliation under ANALYSIS-211L-v1. '
    || 'Existing FY2020-FY2024 exclusion policy '
    || 'extended based on consistent program identity, '
    || 'historical GDX component coverage, and '
    || 'independently reconciled county controls. '
    || 'VA_GDX is the preferred expenditure and '
    || 'county allocation source; USAspending '
    || 'obligations are nonadditive provenance.',
    'ANALYSIS-211L-v1',
    2018,
    2019
FROM (
    VALUES
    ('64.104'), ('64.105'), ('64.110'),
    ('64.028'), ('64.032'), ('64.117'),
    ('64.120'), ('64.124')
) AS t(program_code)
CROSS JOIN reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-211L-v1'
  AND p.preferred_source = 'VA_GDX'
  AND p.valid_from_fiscal_year = 2018
  AND p.valid_through_fiscal_year = 2019;

-- ============================================================
-- 5. POST-MIGRATION HARD CONTROLS
-- ============================================================

DO $$
DECLARE
    v_classifications bigint;
    v_policies bigint;
    v_mappings bigint;
    v_rows bigint;
    v_amount numeric;
    v_bad bigint;
    v_program_years bigint;
    v_untouched bigint;
BEGIN
    SELECT COUNT(*)
    INTO v_classifications
    FROM reference.federal_inflow_program_classification
    WHERE methodology_version = 'ANALYSIS-211L-v1';

    SELECT COUNT(*)
    INTO v_policies
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-211L-v1';

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-211L-v1'
      AND resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE';

    IF v_classifications <> 8
       OR v_policies <> 1
       OR v_mappings <> 8 THEN
        RAISE EXCEPTION
            'Inserted record counts incorrect: classifications %, policies %, mappings %',
            v_classifications, v_policies, v_mappings;
    END IF;

    -- Each targeted transaction must resolve to exactly
    -- one historical exclusion mapping.
    WITH targets(code) AS (
        VALUES
        ('64.104'), ('64.105'), ('64.110'),
        ('64.028'), ('64.032'), ('64.117'),
        ('64.120'), ('64.124')
    ),
    historical AS (
        SELECT
            c.assistance_transaction_id,
            c.action_date_fiscal_year AS fiscal_year,
            BTRIM(c.cfda_number) AS program_code,
            c.federal_action_obligation
        FROM analysis.v_certified_assistance_ledger c
        JOIN targets t
          ON t.code = BTRIM(c.cfda_number)
        WHERE
            (c.load_batch_id = 20
             AND c.action_date_fiscal_year = 2018)
            OR
            (c.load_batch_id = 21
             AND c.action_date_fiscal_year = 2019)
    ),
    resolved AS (
        SELECT
            h.assistance_transaction_id,
            h.fiscal_year,
            h.program_code,
            h.federal_action_obligation,
            COUNT(m.federal_inflow_program_policy_mapping_id)
                AS matching_policies,
            COUNT(*) FILTER (
                WHERE m.resolved_accounting_disposition =
                          'EXCLUDE_DUPLICATE'
                  AND m.methodology_version =
                          'ANALYSIS-211L-v1'
            ) AS correct_matches
        FROM historical h
        LEFT JOIN reference.federal_inflow_program_policy_mapping m
          ON m.source_system = 'USASPENDING_ASSISTANCE'
         AND m.source_program_code = h.program_code
         AND h.fiscal_year BETWEEN
             COALESCE(m.valid_from_fiscal_year, -9999)
             AND COALESCE(m.valid_through_fiscal_year, 9999)
        GROUP BY
            h.assistance_transaction_id,
            h.fiscal_year,
            h.program_code,
            h.federal_action_obligation
    )
    SELECT
        COUNT(*),
        COALESCE(SUM(federal_action_obligation), 0),
        COUNT(*) FILTER (
            WHERE matching_policies <> 1
               OR correct_matches <> 1
        ),
        COUNT(DISTINCT (fiscal_year, program_code))
    INTO v_rows, v_amount, v_bad, v_program_years
    FROM resolved;

    IF v_rows <> 5337
       OR ROUND(v_amount, 2) <> 1274305391.00
       OR v_bad <> 0
       OR v_program_years <> 16 THEN
        RAISE EXCEPTION
            'Historical resolution failed: rows %, amount %, bad %, program-years %',
            v_rows, v_amount, v_bad, v_program_years;
    END IF;

    -- Preserve the existing AL 64.109 historical policy.
    SELECT COUNT(*)
    INTO v_untouched
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code = '64.109'
      AND m.methodology_version = 'ANALYSIS-209U-v1'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2018
      AND m.valid_through_fiscal_year = 2019
      AND s.preferred_source = 'VA_GDX';

    IF v_untouched <> 1 THEN
        RAISE EXCEPTION
            'Existing AL 64.109 historical policy changed';
    END IF;

    RAISE NOTICE
        'ETL-211L1 POST-MIGRATION CONTROLS PASS';
    RAISE NOTICE
        '5337 transactions; $1274305391.00 nonadditive';
    RAISE NOTICE
        '16 program-years; 8 classifications; 1 source policy; 8 mappings';
    RAISE NOTICE
        'AL 64.109 historical policy preserved';
END $$;

COMMIT;

\echo ''
\echo 'ETL-211L1 COMPLETE - TRANSACTION COMMITTED'
