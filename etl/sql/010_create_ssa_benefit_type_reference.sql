CREATE TABLE IF NOT EXISTS reference.ssa_benefit_type (
    ssa_benefit_type_id BIGSERIAL PRIMARY KEY,
    benefit_type_code TEXT NOT NULL UNIQUE,
    benefit_type_name TEXT NOT NULL,
    benefit_group TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    is_total BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO reference.ssa_benefit_type (
    benefit_type_code,
    benefit_type_name,
    benefit_group,
    display_order,
    is_total
)
VALUES
    ('TOTAL', 'Total', 'Total', 1, TRUE),
    ('RETIRED_WORKERS', 'Retired workers', 'Retirement', 2, FALSE),
    ('RETIRED_SPOUSES', 'Retired worker spouses', 'Retirement', 3, FALSE),
    ('RETIRED_CHILDREN', 'Retired worker children', 'Retirement', 4, FALSE),
    ('SURVIVOR_WIDOWERS_PARENTS', 'Widow(er)s and parents', 'Survivors', 5, FALSE),
    ('SURVIVOR_CHILDREN', 'Survivor children', 'Survivors', 6, FALSE),
    ('DISABLED_WORKERS', 'Disabled workers', 'Disability', 7, FALSE),
    ('DISABLED_SPOUSES', 'Disabled worker spouses', 'Disability', 8, FALSE),
    ('DISABLED_CHILDREN', 'Disabled worker children', 'Disability', 9, FALSE)
ON CONFLICT (benefit_type_code)
DO UPDATE SET
    benefit_type_name = EXCLUDED.benefit_type_name,
    benefit_group = EXCLUDED.benefit_group,
    display_order = EXCLUDED.display_order,
    is_total = EXCLUDED.is_total;