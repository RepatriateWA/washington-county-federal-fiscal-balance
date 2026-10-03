\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-3 - VA ASSISTANCE / GDX OVERLAP EVIDENCE CLASSIFICATION'
\echo '===================================================================================================='
\echo 'READ ONLY - NO DATABASE WRITES'
\echo ''

DROP TABLE IF EXISTS pg_temp.va_5n3_classification;

CREATE TEMP TABLE va_5n3_classification (
    cfda_number text PRIMARY KEY,
    evidence_class text NOT NULL,
    gdx_category_code text,
    classification_basis text NOT NULL
);

-- ================================================================================================
-- CLASS A
--
-- Direct substantive correspondence between the USAspending assistance
-- program and an explicit VA GDX expenditure component demonstrated in 5N-2.
--
-- This is an evidentiary classification only. It does NOT persist an
-- accounting disposition.
-- ================================================================================================

INSERT INTO va_5n3_classification
    (cfda_number, evidence_class, gdx_category_code, classification_basis)
VALUES

-- Compensation / pension
('64.109', 'A_DIRECT_GDX_OVERLAP', 'COMPENSATION_PENSION',
 'Veterans Compensation for Service-Connected Disability directly corresponds to GDX Compensation & Pension.'),

('64.110', 'A_DIRECT_GDX_OVERLAP', 'COMPENSATION_PENSION',
 'Veterans Dependency and Indemnity Compensation corresponds to the GDX compensation/pension family and the explicit FY2024 DIC/Survivors Pension component.'),

('64.104', 'A_DIRECT_GDX_OVERLAP', 'COMPENSATION_PENSION',
 'Non-service-connected disability pension directly corresponds to GDX Compensation & Pension.'),

('64.105', 'A_DIRECT_GDX_OVERLAP', 'COMPENSATION_PENSION',
 'Survivor pension directly corresponds to GDX Compensation & Pension and the FY2024 DIC/Survivors Pension component.'),

-- Education / VRE
('64.028', 'A_DIRECT_GDX_OVERLAP', 'EDUCATION_VRE',
 'Post-9/11 Veterans Educational Assistance directly corresponds to GDX Education & VRE.'),

('64.117', 'A_DIRECT_GDX_OVERLAP', 'EDUCATION_VRE',
 'Survivors and Dependents Educational Assistance directly corresponds to GDX Education & VRE.'),

('64.124', 'A_DIRECT_GDX_OVERLAP', 'EDUCATION_VRE',
 'All-Volunteer Force Educational Assistance directly corresponds to GDX Education & VRE.'),

('64.032', 'A_DIRECT_GDX_OVERLAP', 'EDUCATION_VRE',
 'Montgomery GI Bill Selected Reserve directly corresponds to GDX Education & VRE.'),

('64.120', 'A_DIRECT_GDX_OVERLAP', 'EDUCATION_VRE',
 'Post-Vietnam Era Veterans Educational Assistance directly corresponds to GDX Education & VRE.'),

-- Medical care
('64.041', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Outpatient Specialty Care directly corresponds to GDX Medical Care.'),

('64.045', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Outpatient Ancillary Services directly corresponds to GDX Medical Care.'),

('64.012', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'Veterans Prescription Service directly corresponds to GDX Medical Care.'),

('64.040', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Inpatient Medicine directly corresponds to GDX Medical Care.'),

('64.048', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Mental Health Clinics directly corresponds to GDX Medical Care.'),

('64.047', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Primary Care directly corresponds to GDX Medical Care.'),

('64.013', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'Veterans Prosthetic Appliances directly corresponds to GDX Medical Care.'),

('64.050', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Diagnostic Care directly corresponds to GDX Medical Care.'),

('64.039', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'CHAMPVA directly corresponds to the GDX Medical Care expenditure family.'),

('64.049', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Community Living Center directly corresponds to GDX Medical Care.'),

('64.042', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Inpatient Surgery directly corresponds to GDX Medical Care.'),

('64.044', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Home Care directly corresponds to GDX Medical Care.'),

('64.011', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'Veterans Dental Care directly corresponds to GDX Medical Care.'),

('64.046', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Inpatient Psychiatry directly corresponds to GDX Medical Care.'),

('64.043', 'A_DIRECT_GDX_OVERLAP', 'MEDICAL_CARE',
 'VHA Mental Health Residential directly corresponds to GDX Medical Care.'),

-- Construction
('64.005', 'A_DIRECT_GDX_OVERLAP', 'CONSTRUCTION',
 'Grants to States for Construction of State Home Facilities directly corresponds to GDX Construction.'),

-- Memorial
('64.101', 'A_DIRECT_GDX_OVERLAP', 'MEMORIAL_BENEFITS',
 'Burial Expense Allowance corresponds to the explicit GDX Memorial Benefits component.'),

('64.203', 'A_DIRECT_GDX_OVERLAP', 'MEMORIAL_BENEFITS',
 'Veterans Cemetery Grants corresponds to the explicit GDX Memorial Benefits component.'),

('64.206', 'A_DIRECT_GDX_OVERLAP', 'MEMORIAL_BENEFITS',
 'Outer Burial Receptacle Allowance corresponds to the explicit GDX Memorial Benefits component.');

\echo ''
\echo 'SECTION 1 - CLASS A EXPLICIT DIRECT-GDX MAPPINGS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    cfda_number,
    evidence_class,
    gdx_category_code,
    classification_basis
FROM va_5n3_classification
ORDER BY
    gdx_category_code,
    cfda_number;


-- ================================================================================================
-- Build the complete 49-program VA assistance universe directly from the certified assistance ledger.
-- ================================================================================================

DROP TABLE IF EXISTS pg_temp.va_5n3_programs;

CREATE TEMP TABLE va_5n3_programs AS
SELECT
    trim(cfda_number::text) AS cfda_number,
    max(cfda_title) AS cfda_title,
    count(*) AS transaction_count,
    sum(federal_action_obligation)::numeric AS obligation_dollars,
    sum(
        CASE
            WHEN is_covid
            THEN federal_action_obligation
            ELSE 0
        END
    )::numeric AS covid_dollars
FROM analysis.v_certified_assistance_ledger
WHERE reference_state_abbreviation = 'WA'
  AND action_date_fiscal_year BETWEEN 2020 AND 2024
  AND trim(cfda_number::text) LIKE '64.%'
GROUP BY trim(cfda_number::text);


-- ================================================================================================
-- Assign all remaining programs.
--
-- B = positive/negative nonzero obligations without a direct 5N-2 mapping.
-- C = exactly zero net obligations over FY2020-FY2024.
-- ================================================================================================

INSERT INTO va_5n3_classification
    (cfda_number, evidence_class, gdx_category_code, classification_basis)
SELECT
    p.cfda_number,
    CASE
        WHEN p.obligation_dollars = 0
            THEN 'C_ZERO_DOLLAR'
        ELSE 'B_REQUIRES_FINAL_REVIEW'
    END,
    NULL,
    CASE
        WHEN p.obligation_dollars = 0
            THEN 'Net USAspending assistance obligation is zero for FY2020-FY2024; no ledger effect.'
        ELSE 'No sufficiently direct GDX component correspondence was established by ETL-174B-5N-2; retain for final review.'
    END
FROM va_5n3_programs p
LEFT JOIN va_5n3_classification c
    ON c.cfda_number = p.cfda_number
WHERE c.cfda_number IS NULL;


\echo ''
\echo 'SECTION 2 - COMPLETE 49-PROGRAM CLASSIFICATION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.cfda_number,
    p.cfda_title,
    c.evidence_class,
    c.gdx_category_code,
    p.transaction_count,
    p.obligation_dollars,
    p.covid_dollars
FROM va_5n3_programs p
JOIN va_5n3_classification c
    USING (cfda_number)
ORDER BY
    c.evidence_class,
    abs(p.obligation_dollars) DESC,
    p.cfda_number;


\echo ''
\echo 'SECTION 3 - EVIDENCE CLASS CONTROL TOTALS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    c.evidence_class,
    count(*) AS program_count,
    sum(p.transaction_count) AS transaction_count,
    sum(p.obligation_dollars)::numeric AS obligation_dollars,
    sum(p.covid_dollars)::numeric AS covid_dollars,
    round(
        100.0 * sum(p.obligation_dollars)
        / NULLIF((SELECT sum(obligation_dollars) FROM va_5n3_programs), 0),
        2
    ) AS percent_of_va_assistance
FROM va_5n3_programs p
JOIN va_5n3_classification c
    USING (cfda_number)
GROUP BY c.evidence_class
ORDER BY c.evidence_class;


\echo ''
\echo 'SECTION 4 - CLASS A BY GDX COMPONENT'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    c.gdx_category_code,
    count(*) AS program_count,
    sum(p.obligation_dollars)::numeric AS obligation_dollars,
    sum(p.covid_dollars)::numeric AS covid_dollars
FROM va_5n3_programs p
JOIN va_5n3_classification c
    USING (cfda_number)
WHERE c.evidence_class = 'A_DIRECT_GDX_OVERLAP'
GROUP BY c.gdx_category_code
ORDER BY sum(p.obligation_dollars) DESC;


\echo ''
\echo 'SECTION 5 - CLASS A ANNUAL COVERAGE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    l.action_date_fiscal_year AS fiscal_year,
    sum(l.federal_action_obligation)::numeric AS class_a_obligation,
    sum(
        CASE
            WHEN l.is_covid
            THEN l.federal_action_obligation
            ELSE 0
        END
    )::numeric AS class_a_covid_dollars
FROM analysis.v_certified_assistance_ledger l
JOIN va_5n3_classification c
    ON c.cfda_number = trim(l.cfda_number::text)
WHERE l.reference_state_abbreviation = 'WA'
  AND l.action_date_fiscal_year BETWEEN 2020 AND 2024
  AND c.evidence_class = 'A_DIRECT_GDX_OVERLAP'
GROUP BY l.action_date_fiscal_year
ORDER BY l.action_date_fiscal_year;


\echo ''
\echo 'SECTION 6 - CLASS B FINAL-REVIEW QUEUE'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.cfda_number,
    p.cfda_title,
    p.transaction_count,
    p.obligation_dollars,
    p.covid_dollars,
    round(
        100.0 * p.obligation_dollars
        / NULLIF((SELECT sum(obligation_dollars) FROM va_5n3_programs), 0),
        4
    ) AS percent_of_va_assistance
FROM va_5n3_programs p
JOIN va_5n3_classification c
    USING (cfda_number)
WHERE c.evidence_class = 'B_REQUIRES_FINAL_REVIEW'
ORDER BY
    abs(p.obligation_dollars) DESC,
    p.cfda_number;


\echo ''
\echo 'SECTION 7 - CLASS C ZERO-DOLLAR PROGRAMS'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    p.cfda_number,
    p.cfda_title,
    p.transaction_count,
    p.obligation_dollars,
    p.covid_dollars
FROM va_5n3_programs p
JOIN va_5n3_classification c
    USING (cfda_number)
WHERE c.evidence_class = 'C_ZERO_DOLLAR'
ORDER BY p.cfda_number;


\echo ''
\echo 'SECTION 8 - COMPLETE CONTROL REPRODUCTION'
\echo '----------------------------------------------------------------------------------------------------'

SELECT
    count(*) AS program_count,
    sum(transaction_count) AS transaction_count,
    sum(obligation_dollars)::numeric AS obligation_control,
    sum(covid_dollars)::numeric AS covid_control
FROM va_5n3_programs;


\echo ''
\echo 'SECTION 9 - CLASSIFICATION COMPLETENESS ASSERTIONS'
\echo '----------------------------------------------------------------------------------------------------'

DO $$
DECLARE
    v_program_count integer;
    v_classified_count integer;
    v_control numeric;
BEGIN
    SELECT count(*), sum(obligation_dollars)
    INTO v_program_count, v_control
    FROM va_5n3_programs;

    SELECT count(*)
    INTO v_classified_count
    FROM va_5n3_classification;

    IF v_program_count <> 49 THEN
        RAISE EXCEPTION
            'Expected 49 CFDA 64.* programs; found %',
            v_program_count;
    END IF;

    IF v_classified_count <> v_program_count THEN
        RAISE EXCEPTION
            'Classification count % does not equal program count %',
            v_classified_count,
            v_program_count;
    END IF;

    IF abs(v_control - 23707643332.28::numeric) > 0.01 THEN
        RAISE EXCEPTION
            'VA assistance control mismatch: expected 23707643332.28; found %',
            v_control;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM va_5n3_programs p
        LEFT JOIN va_5n3_classification c
            USING (cfda_number)
        WHERE c.cfda_number IS NULL
    ) THEN
        RAISE EXCEPTION
            'At least one CFDA 64.* program lacks an evidence classification';
    END IF;

    RAISE NOTICE
        'PASS: all 49 CFDA 64.* programs classified and $23,707,643,332.28 control reproduced';
END
$$;


\echo ''
\echo 'SECTION 10 - DECISION SUPPORT SUMMARY'
\echo '----------------------------------------------------------------------------------------------------'

WITH summary AS (
    SELECT
        c.evidence_class,
        count(*) AS programs,
        sum(p.obligation_dollars)::numeric AS dollars,
        sum(p.covid_dollars)::numeric AS covid_dollars
    FROM va_5n3_programs p
    JOIN va_5n3_classification c
        USING (cfda_number)
    GROUP BY c.evidence_class
)
SELECT
    evidence_class,
    programs,
    dollars,
    covid_dollars,
    round(
        100.0 * dollars
        / NULLIF(sum(dollars) OVER (), 0),
        2
    ) AS percent_of_control
FROM summary
ORDER BY evidence_class;


\echo ''
\echo '===================================================================================================='
\echo 'ETL-174B-5N-3 PROFILE COMPLETE - VA ASSISTANCE OVERLAP EVIDENCE CLASSIFICATION - NO DB WRITES'
\echo '===================================================================================================='