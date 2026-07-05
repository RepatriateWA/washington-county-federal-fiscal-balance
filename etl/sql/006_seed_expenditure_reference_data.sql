-- ==========================================================
-- Seed expenditure.program
-- ==========================================================

INSERT INTO expenditure.program
(program_code, program_name, description)
VALUES
('SSA', 'Social Security', 'Old-Age, Survivors, and Disability Insurance benefits'),
('MEDICARE', 'Medicare', 'Federal Medicare benefit payments'),
('MEDICAID', 'Medicaid', 'Federal share of Medicaid expenditures'),
('VA', 'Veterans Benefits', 'Veterans Administration benefits and services'),
('SNAP', 'Supplemental Nutrition Assistance Program', 'Food assistance benefits'),
('FED_PAYROLL', 'Federal Payroll', 'Federal civilian payroll'),
('GRANTS', 'Federal Grants', 'Federal financial assistance and grants'),
('CONTRACTS', 'Federal Contracts', 'Federal procurement and contract spending'),
('HIGHWAYS', 'Highway Funding', 'Federal highway programs'),
('EDUCATION', 'Education Funding', 'Federal education assistance'),
('USDA', 'Agriculture Programs', 'USDA farm and rural development programs'),
('DISASTER', 'Disaster Assistance', 'Federal disaster relief')
ON CONFLICT (program_code) DO NOTHING;

-- ==========================================================
-- Seed expenditure.data_source
-- ==========================================================

INSERT INTO expenditure.data_source
(source_code, source_name, agency_name, source_url)
VALUES
(
'SSA',
'Social Security Annual Statistical Supplement',
'Social Security Administration',
'https://www.ssa.gov/policy/docs/statcomps/'
),
(
'CMS',
'Centers for Medicare & Medicaid Services',
'Centers for Medicare & Medicaid Services',
'https://www.cms.gov/'
),
(
'USASPENDING',
'USAspending',
'U.S. Department of the Treasury',
'https://www.usaspending.gov/'
),
(
'USDA',
'USDA Open Data',
'U.S. Department of Agriculture',
'https://www.usda.gov/'
),
(
'VA',
'Veterans Affairs Open Data',
'U.S. Department of Veterans Affairs',
'https://www.va.gov/data/'
)
ON CONFLICT (source_code) DO NOTHING;