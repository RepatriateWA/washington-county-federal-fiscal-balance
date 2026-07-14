CREATE TABLE IF NOT EXISTS reference.federal_program (
    federal_program_id BIGSERIAL PRIMARY KEY,

    federal_agency_id BIGINT NOT NULL
        REFERENCES reference.federal_agency(federal_agency_id),

    program_code TEXT NOT NULL UNIQUE,
    program_name TEXT NOT NULL,

    program_category TEXT NOT NULL,

    is_revenue_program BOOLEAN NOT NULL DEFAULT FALSE,
    is_expenditure_program BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO reference.federal_program (
    federal_agency_id,
    program_code,
    program_name,
    program_category,
    is_revenue_program,
    is_expenditure_program
)
SELECT
    fa.federal_agency_id,
    p.program_code,
    p.program_name,
    p.program_category,
    p.is_revenue_program,
    p.is_expenditure_program
FROM (
    VALUES

    -- IRS
    ('IRS','IRS_GROSS_COLLECTIONS','IRS Gross Collections','Revenue',TRUE,FALSE),
    ('IRS','IRS_INDIVIDUAL_INCOME','Individual Income Tax','Revenue',TRUE,FALSE),
    ('IRS','IRS_BUSINESS_INCOME','Business Income Tax','Revenue',TRUE,FALSE),
    ('IRS','IRS_ESTATE_GIFT','Estate and Gift Tax','Revenue',TRUE,FALSE),
    ('IRS','IRS_EXCISE','Excise Tax','Revenue',TRUE,FALSE),

    -- SSA
    ('SSA','OASDI_RETIREMENT','OASDI Retirement','Social Security',FALSE,TRUE),
    ('SSA','OASDI_SURVIVORS','OASDI Survivors','Social Security',FALSE,TRUE),
    ('SSA','OASDI_DISABILITY','OASDI Disability','Social Security',FALSE,TRUE),
    ('SSA','SSI','Supplemental Security Income','Social Security',FALSE,TRUE),

    -- CMS
    ('CMS','MEDICARE','Medicare','Health',FALSE,TRUE),
    ('CMS','MEDICAID','Medicaid','Health',FALSE,TRUE),
    ('CMS','CHIP','Children''s Health Insurance Program','Health',FALSE,TRUE),

    -- VA
    ('VA','VA_COMPENSATION','Veterans Compensation','Veterans',FALSE,TRUE),
    ('VA','VA_PENSION','Veterans Pension','Veterans',FALSE,TRUE),
    ('VA','VA_EDUCATION','Veterans Education','Veterans',FALSE,TRUE),

    -- USAspending
    ('USA_SPENDING','GRANTS','Federal Grants','Financial Assistance',FALSE,TRUE),
    ('USA_SPENDING','CONTRACTS','Federal Contracts','Procurement',FALSE,TRUE),
    ('USA_SPENDING','DIRECT_PAYMENTS','Direct Payments','Financial Assistance',FALSE,TRUE),
    ('USA_SPENDING','LOANS','Federal Loans','Financial Assistance',FALSE,TRUE)

) AS p(
    agency_code,
    program_code,
    program_name,
    program_category,
    is_revenue_program,
    is_expenditure_program
)
JOIN reference.federal_agency fa
    ON fa.agency_code = p.agency_code

ON CONFLICT (program_code)
DO UPDATE SET
    federal_agency_id = EXCLUDED.federal_agency_id,
    program_name = EXCLUDED.program_name,
    program_category = EXCLUDED.program_category,
    is_revenue_program = EXCLUDED.is_revenue_program,
    is_expenditure_program = EXCLUDED.is_expenditure_program;