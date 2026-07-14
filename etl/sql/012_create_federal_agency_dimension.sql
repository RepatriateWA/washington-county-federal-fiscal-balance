CREATE TABLE IF NOT EXISTS reference.federal_agency (
    federal_agency_id BIGSERIAL PRIMARY KEY,

    agency_code TEXT NOT NULL UNIQUE,
    agency_name TEXT NOT NULL,

    parent_agency_code TEXT,
    agency_level TEXT NOT NULL DEFAULT 'AGENCY',

    is_revenue_agency BOOLEAN NOT NULL DEFAULT FALSE,
    is_expenditure_agency BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO reference.federal_agency (
    agency_code,
    agency_name,
    parent_agency_code,
    agency_level,
    is_revenue_agency,
    is_expenditure_agency,
    is_active
)
VALUES
    (
        'IRS',
        'Internal Revenue Service',
        'TREASURY',
        'BUREAU',
        TRUE,
        FALSE,
        TRUE
    ),
    (
        'TREASURY',
        'Department of the Treasury',
        NULL,
        'DEPARTMENT',
        TRUE,
        TRUE,
        TRUE
    ),
    (
        'SSA',
        'Social Security Administration',
        NULL,
        'INDEPENDENT_AGENCY',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'CMS',
        'Centers for Medicare & Medicaid Services',
        'HHS',
        'OPERATING_DIVISION',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'HHS',
        'Department of Health and Human Services',
        NULL,
        'DEPARTMENT',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'VA',
        'Department of Veterans Affairs',
        NULL,
        'DEPARTMENT',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'USA_SPENDING',
        'USAspending.gov',
        'TREASURY',
        'REPORTING_SYSTEM',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'OPM',
        'Office of Personnel Management',
        NULL,
        'INDEPENDENT_AGENCY',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'USDA',
        'U.S. Department of Agriculture',
        NULL,
        'DEPARTMENT',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'HUD',
        'Department of Housing and Urban Development',
        NULL,
        'DEPARTMENT',
        FALSE,
        TRUE,
        TRUE
    ),
    (
        'DOD',
        'Department of Defense',
        NULL,
        'DEPARTMENT',
        FALSE,
        TRUE,
        TRUE
    )
ON CONFLICT (agency_code)
DO UPDATE SET
    agency_name = EXCLUDED.agency_name,
    parent_agency_code = EXCLUDED.parent_agency_code,
    agency_level = EXCLUDED.agency_level,
    is_revenue_agency = EXCLUDED.is_revenue_agency,
    is_expenditure_agency = EXCLUDED.is_expenditure_agency,
    is_active = EXCLUDED.is_active;