SELECT
    COUNT(*) AS transaction_count,

    ROUND(
        SUM(federal_action_obligation)::numeric,
        2
    ) AS net_obligation_dollars,

    ROUND(
        SUM(
            CASE
                WHEN is_covid
                THEN federal_action_obligation
                ELSE 0
            END
        )::numeric,
        2
    ) AS covid_obligation_dollars,

    COUNT(DISTINCT award_id_fain)
        AS distinct_fain_count,

    COUNT(DISTINCT recipient_name)
        AS distinct_recipient_count,

    COUNT(DISTINCT assistance_type_code)
        AS distinct_assistance_type_count

FROM analysis.v_certified_assistance_ledger

WHERE action_date_fiscal_year BETWEEN 2020 AND 2024
  AND reference_state_abbreviation = 'WA'
  AND cfda_number = '93.767';