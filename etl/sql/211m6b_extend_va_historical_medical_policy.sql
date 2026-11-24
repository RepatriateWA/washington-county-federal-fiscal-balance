
\set ON_ERROR_STOP on
\pset pager off
\pset null '[NULL]'

\echo '============================================================'
\echo 'ETL-211M6B - HISTORICAL VA MEDICAL CARE POLICY EXTENSION'
\echo 'FY2018-FY2019 | ANALYSIS-211M-v1'
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
    -- Prevent repeated execution or partial installation.
    SELECT
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_classification
         WHERE methodology_version = 'ANALYSIS-211M-v1')
        +
        (SELECT COUNT(*)
         FROM reference.federal_inflow_source_policy
         WHERE methodology_version = 'ANALYSIS-211M-v1')
        +
        (SELECT COUNT(*)
         FROM reference.federal_inflow_program_policy_mapping
         WHERE methodology_version = 'ANALYSIS-211M-v1')
    INTO v_count;

    IF v_count <> 0 THEN
        RAISE EXCEPTION
            'ETL-211M6B already installed or partially present';
    END IF;

    -- Verify exact certified historical source population.
    WITH targets(code) AS (
        VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
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

    IF v_count <> 11818
       OR ROUND(v_amount, 2) <> 2297804301.00 THEN
        RAISE EXCEPTION
            'Historical population mismatch: rows %, amount %',
            v_count, v_amount;
    END IF;

    -- No historical program, award, or descriptive
    -- classification collisions permitted.
    WITH targets(code) AS (
        VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
    )
    SELECT
        (
            SELECT COUNT(*)
            FROM reference.federal_inflow_program_policy_mapping m
            JOIN targets t
              ON t.code = BTRIM(m.source_program_code)
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
            JOIN targets t
              ON t.code = BTRIM(a.source_program_code)
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
            JOIN targets t
              ON t.code = BTRIM(c.source_program_code)
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

    -- Verify every FY2020-FY2024 precedent.
    WITH targets(code) AS (
        VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
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
                  AND s.allocation_source = 'VA_GDX'
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

    IF v_precedent <> 75 THEN
        RAISE EXCEPTION
            'Later-year VA Medical Care precedent failed: % of 75',
            v_precedent;
    END IF;

    -- Verify independent historical VA GDX Medical Care controls.
    SELECT COUNT(*)
    INTO v_gdx
    FROM (
        SELECT
            e.fiscal_year,
            COUNT(*) AS county_rows,
            COUNT(DISTINCT e.county_id) AS counties,
            ROUND(SUM(e.expenditure_amount)::numeric, 2)
                AS expenditure_total
        FROM va.gdx_county_expenditure e
        JOIN va.gdx_expenditure_category k
          ON k.gdx_category_id = e.gdx_category_id
        WHERE e.fiscal_year IN (2018, 2019)
          AND k.category_code = 'MEDICAL_CARE'
        GROUP BY e.fiscal_year
    ) q
    WHERE q.county_rows = 39
      AND q.counties = 39
      AND (
          (q.fiscal_year = 2018
           AND q.expenditure_total = 1526068781.09)
          OR
          (q.fiscal_year = 2019
           AND q.expenditure_total = 1665541164.21)
      );

    IF v_gdx <> 2 THEN
        RAISE EXCEPTION
            'Historical VA GDX Medical Care controls failed';
    END IF;

    RAISE NOTICE
        'ETL-211M6B PRE-MIGRATION CONTROLS PASS';
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
    'FY2018-FY2019 historical extension of '
    || 'ANALYSIS-174B-5N-v1 VA GDX Medical Care '
    || 'overlap methodology. Historical VA GDX '
    || 'Medical Care expenditures are present for '
    || 'all 39 Washington counties and reconcile '
    || 'to certified annual controls. '
    || 'FY2020-FY2024 policies consistently prefer '
    || 'VA_GDX for these Assistance Listings. '
    || 'USAspending obligations and VA expenditures '
    || 'are distinct accounting measures. '
    || 'This classification identifies overlap risk; '
    || 'accounting disposition is governed by '
    || 'ANALYSIS-211M-v1 source policy.',
    'ANALYSIS-211M-v1',
    2018,
    2019
FROM (
    VALUES
    ('64.011', 'VETERANS MEDICAL CARE ASSISTANCE 64.011'),
    ('64.012', 'VETERANS MEDICAL CARE ASSISTANCE 64.012'),
    ('64.013', 'VETERANS MEDICAL CARE ASSISTANCE 64.013'),
    ('64.039', 'VETERANS MEDICAL CARE ASSISTANCE 64.039'),
    ('64.040', 'VETERANS MEDICAL CARE ASSISTANCE 64.040'),
    ('64.041', 'VETERANS MEDICAL CARE ASSISTANCE 64.041'),
    ('64.042', 'VETERANS MEDICAL CARE ASSISTANCE 64.042'),
    ('64.043', 'VETERANS MEDICAL CARE ASSISTANCE 64.043'),
    ('64.044', 'VETERANS MEDICAL CARE ASSISTANCE 64.044'),
    ('64.045', 'VETERANS MEDICAL CARE ASSISTANCE 64.045'),
    ('64.046', 'VETERANS MEDICAL CARE ASSISTANCE 64.046'),
    ('64.047', 'VETERANS MEDICAL CARE ASSISTANCE 64.047'),
    ('64.048', 'VETERANS MEDICAL CARE ASSISTANCE 64.048'),
    ('64.049', 'VETERANS MEDICAL CARE ASSISTANCE 64.049'),
    ('64.050', 'VETERANS MEDICAL CARE ASSISTANCE 64.050')
) AS v(program_code, program_title);

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
    'FY2018-FY2019 historical extension of '
    || 'ANALYSIS-174B-5N-v1 for 15 VA Medical Care '
    || 'Assistance Listings. Historical VA GDX '
    || 'Medical Care expenditures are present for '
    || 'all 39 Washington counties in both years. '
    || 'FY2020-FY2024 program policies consistently '
    || 'select VA_GDX as preferred expenditure and '
    || 'county allocation source. USAspending '
    || 'obligations remain transaction-level provenance '
    || 'and are not added as a second expenditure '
    || 'stream. No dollar-for-dollar equivalence '
    || 'between obligations and expenditures is '
    || 'assumed. AL 64.029 is explicitly excluded '
    || 'and remains subject to separate review.',
    'ANALYSIS-211M-v1',
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
    'FY2018-FY2019 historical VA GDX Medical Care '
    || 'overlap reconciliation under ANALYSIS-211M-v1. '
    || 'Historical GDX county Medical Care controls '
    || 'verified independently. Existing FY2020-FY2024 '
    || 'program exclusions establish the later-year '
    || 'precedent. VA_GDX remains the preferred '
    || 'expenditure and county allocation source. '
    || 'USAspending obligations are nonadditive '
    || 'transaction-level provenance.',
    'ANALYSIS-211M-v1',
    2018,
    2019
FROM (
    VALUES
    ('64.011'), ('64.012'), ('64.013'),
    ('64.039'), ('64.040'), ('64.041'),
    ('64.042'), ('64.043'), ('64.044'),
    ('64.045'), ('64.046'), ('64.047'),
    ('64.048'), ('64.049'), ('64.050')
) AS t(program_code)
CROSS JOIN reference.federal_inflow_source_policy p
WHERE p.methodology_version = 'ANALYSIS-211M-v1'
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
    WHERE methodology_version = 'ANALYSIS-211M-v1';

    SELECT COUNT(*)
    INTO v_policies
    FROM reference.federal_inflow_source_policy
    WHERE methodology_version = 'ANALYSIS-211M-v1';

    SELECT COUNT(*)
    INTO v_mappings
    FROM reference.federal_inflow_program_policy_mapping
    WHERE methodology_version = 'ANALYSIS-211M-v1'
      AND resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE';

    IF v_classifications <> 15
       OR v_policies <> 1
       OR v_mappings <> 15 THEN
        RAISE EXCEPTION
            'Inserted counts incorrect: classifications %, policies %, mappings %',
            v_classifications, v_policies, v_mappings;
    END IF;

    -- Each historical transaction must resolve to exactly
    -- one exclusion mapping.
    WITH targets(code) AS (
        VALUES
        ('64.011'), ('64.012'), ('64.013'),
        ('64.039'), ('64.040'), ('64.041'),
        ('64.042'), ('64.043'), ('64.044'),
        ('64.045'), ('64.046'), ('64.047'),
        ('64.048'), ('64.049'), ('64.050')
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
                          'ANALYSIS-211M-v1'
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

    IF v_rows <> 11818
       OR ROUND(v_amount, 2) <> 2297804301.00
       OR v_bad <> 0
       OR v_program_years <> 30 THEN
        RAISE EXCEPTION
            'Historical resolution failed: rows %, amount %, bad %, program-years %',
            v_rows, v_amount, v_bad, v_program_years;
    END IF;

    -- Preserve the existing FY2020-FY2024 policy records.
    SELECT COUNT(*)
    INTO v_untouched
    FROM reference.federal_inflow_program_policy_mapping m
    JOIN reference.federal_inflow_source_policy s
      ON s.federal_inflow_source_policy_id =
         m.federal_inflow_source_policy_id
    WHERE m.source_system = 'USASPENDING_ASSISTANCE'
      AND m.source_program_code IN (
          '64.011','64.012','64.013',
          '64.039','64.040','64.041',
          '64.042','64.043','64.044',
          '64.045','64.046','64.047',
          '64.048','64.049','64.050'
      )
      AND m.methodology_version = 'ANALYSIS-174B-5N-v1'
      AND m.resolved_accounting_disposition =
          'EXCLUDE_DUPLICATE'
      AND m.valid_from_fiscal_year = 2020
      AND m.valid_through_fiscal_year = 2024
      AND s.preferred_source = 'VA_GDX';

    IF v_untouched <> 15 THEN
        RAISE EXCEPTION
            'Existing later-year VA Medical Care policies changed';
    END IF;

    RAISE NOTICE
        'ETL-211M6B POST-MIGRATION CONTROLS PASS';
    RAISE NOTICE
        '11818 transactions; $2297804301.00 nonadditive';
    RAISE NOTICE
        '30 program-years; 15 classifications; 1 source policy; 15 mappings';
    RAISE NOTICE
        'FY2020-FY2024 precedent preserved; AL 64.029 excluded';
END $$;

COMMIT;

\echo ''
\echo 'ETL-211M6B COMPLETE - TRANSACTION COMMITTED'
