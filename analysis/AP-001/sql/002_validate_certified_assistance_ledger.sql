-- ============================================================================
-- AP-001A validation — Certified Assistance Analytical Ledger
-- ============================================================================

-- 1. Row-count reconciliation: must be identical.
SELECT
    (SELECT COUNT(*) FROM assistance.award_transaction) AS source_transactions,
    (SELECT COUNT(*) FROM analysis.v_certified_assistance_ledger) AS ledger_rows,
    (SELECT COUNT(*) FROM analysis.v_certified_assistance_ledger)
      - (SELECT COUNT(*) FROM assistance.award_transaction) AS row_difference;

-- 2. Transaction identity uniqueness: must return 0 duplicate groups.
SELECT COUNT(*) AS duplicate_transaction_key_groups
FROM (
    SELECT assistance_transaction_unique_key
    FROM analysis.v_certified_assistance_ledger
    GROUP BY assistance_transaction_unique_key
    HAVING COUNT(*) <> 1
) q;

-- 3. Transaction ID uniqueness: must return 0 duplicate groups.
SELECT COUNT(*) AS duplicate_transaction_id_groups
FROM (
    SELECT assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger
    GROUP BY assistance_transaction_id
    HAVING COUNT(*) <> 1
) q;

-- 4. Financial reconciliation: source and ledger obligation sums must match.
SELECT
    s.source_obligation,
    l.ledger_obligation,
    l.ledger_obligation - s.source_obligation AS obligation_difference
FROM
    (
        SELECT COALESCE(SUM(federal_action_obligation), 0) AS source_obligation
        FROM assistance.award_transaction
    ) s
CROSS JOIN
    (
        SELECT COALESCE(SUM(federal_action_obligation), 0) AS ledger_obligation
        FROM analysis.v_certified_assistance_ledger
    ) l;

-- 5. Fiscal-year reconciliation.
SELECT
    COALESCE(s.action_date_fiscal_year, l.action_date_fiscal_year)
        AS fiscal_year,
    COALESCE(s.source_rows, 0) AS source_rows,
    COALESCE(l.ledger_rows, 0) AS ledger_rows,
    COALESCE(l.ledger_rows, 0) - COALESCE(s.source_rows, 0)
        AS row_difference,
    COALESCE(s.source_obligation, 0) AS source_obligation,
    COALESCE(l.ledger_obligation, 0) AS ledger_obligation,
    COALESCE(l.ledger_obligation, 0) - COALESCE(s.source_obligation, 0)
        AS obligation_difference
FROM (
    SELECT
        action_date_fiscal_year,
        COUNT(*) AS source_rows,
        COALESCE(SUM(federal_action_obligation), 0) AS source_obligation
    FROM assistance.award_transaction
    GROUP BY action_date_fiscal_year
) s
FULL OUTER JOIN (
    SELECT
        action_date_fiscal_year,
        COUNT(*) AS ledger_rows,
        COALESCE(SUM(federal_action_obligation), 0) AS ledger_obligation
    FROM analysis.v_certified_assistance_ledger
    GROUP BY action_date_fiscal_year
) l
  ON l.action_date_fiscal_year = s.action_date_fiscal_year
ORDER BY fiscal_year;

-- 6. DEFC rollup sanity.
SELECT
    COUNT(*) FILTER (WHERE defc_code_count > 0) AS transactions_with_defc,
    COUNT(*) FILTER (WHERE defc_code_count > 1) AS transactions_with_multiple_defc,
    COUNT(*) FILTER (WHERE is_extraordinary) AS extraordinary_transactions,
    COUNT(*) FILTER (WHERE is_covid) AS covid_transactions,
    COUNT(*) FILTER (WHERE is_iija) AS iija_transactions
FROM analysis.v_certified_assistance_ledger;

-- 7. Geography resolution profile. Informational; not a PASS/FAIL by itself.
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE place_of_performance_id IS NOT NULL)
        AS rows_with_performance_place,
    COUNT(*) FILTER (WHERE reference_state_id IS NOT NULL)
        AS rows_with_reference_state,
    COUNT(*) FILTER (WHERE reference_county_id IS NOT NULL)
        AS rows_with_reference_county,
    COUNT(*) FILTER (WHERE place_source_condition IS NOT NULL)
        AS rows_with_place_source_condition
FROM analysis.v_certified_assistance_ledger;