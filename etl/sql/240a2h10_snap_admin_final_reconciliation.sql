\pset pager off
\echo 'ETL-240A2H10: AL 10.561 final reconciliation'

BEGIN TRANSACTION READ ONLY;

WITH
years AS (
    SELECT generate_series(2018, 2024) AS fiscal_year
),
usda(fiscal_year, federal_share_usd, arpa_usd, note) AS (
    VALUES
        (2018, 100351208::numeric, NULL::numeric, 'USDA Table 8'),
        (2019, 107364488::numeric, NULL::numeric, 'USDA Table 8'),
        (2020, 110112584::numeric, NULL::numeric,
         'USDA Table 9; Table 7 duplicates FY2019'),
        (2021, 113833181::numeric, 185291::numeric,
         'USDA Table 8; separate COVID funding table'),
        (2022, 113928759::numeric, 3163178::numeric,
         'USDA Table 8; separate ARPA column'),
        (2023, 124767005::numeric, 2221984::numeric,
         'USDA Table 8; separate ARPA column'),
        (2024, NULL::numeric, NULL::numeric,
         'USDA report not located')
),
wa AS (
    SELECT
        g.action_date_fiscal_year AS fiscal_year,
        g.assistance_transaction_id,
        g.federal_action_obligation,
        g.is_covid
    FROM analysis.v_assistance_geographic_attribution g
    WHERE g.cfda_number = '10.561'
      AND g.is_washington_attributed IS TRUE
      AND g.action_date_fiscal_year BETWEEN 2018 AND 2024
),
certified AS (
    SELECT DISTINCT assistance_transaction_id
    FROM analysis.v_certified_assistance_ledger
    WHERE cfda_number = '10.561'
),
annual AS (
    SELECT
        w.fiscal_year,
        COUNT(*) AS transaction_rows,
        SUM(w.federal_action_obligation) AS obligations_usd,
        SUM(w.federal_action_obligation)
            FILTER (WHERE w.is_covid IS TRUE) AS covid_obligations_usd,
        SUM(w.federal_action_obligation)
            FILTER (
                WHERE c.assistance_transaction_id IS NOT NULL
            ) AS certified_view_obligations_usd,
        COUNT(*)
            FILTER (
                WHERE c.assistance_transaction_id IS NOT NULL
            ) AS certified_view_rows
    FROM wa w
    LEFT JOIN certified c
      ON c.assistance_transaction_id = w.assistance_transaction_id
    GROUP BY w.fiscal_year
)
SELECT
    y.fiscal_year,
    COALESCE(a.transaction_rows, 0) AS transaction_rows,
    COALESCE(a.obligations_usd, 0) AS obligations_usd,
    COALESCE(a.covid_obligations_usd, 0) AS covid_obligations_usd,
    COALESCE(a.certified_view_obligations_usd, 0)
        AS certified_view_obligations_usd,
    COALESCE(a.certified_view_rows, 0) AS certified_view_rows,
    u.federal_share_usd AS usda_federal_share_usd,
    u.arpa_usd AS usda_separate_covid_usd,
    CASE
        WHEN u.federal_share_usd IS NOT NULL
        THEN a.obligations_usd - u.federal_share_usd
        ELSE NULL
    END AS obligations_minus_usda_usd,
    u.note
FROM years y
LEFT JOIN annual a USING (fiscal_year)
LEFT JOIN usda u USING (fiscal_year)
ORDER BY y.fiscal_year;

ROLLBACK;
