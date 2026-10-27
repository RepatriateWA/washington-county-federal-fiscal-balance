# WCFFBP ETL-238B5B — Provisional Assistance Reporting Checkpoint

Date: 2026-10-27
Status: VALIDATED READ-ONLY REPORTING SCENARIO; NOT CANONICAL LEDGER AUTHORIZATION.
Scope: Washington State, federal fiscal years 2018–2024.

## Purpose
Preserve the reproducible evidence supporting provisional inclusion of previously unresolved, tagged USAspending assistance, separately from established additive assistance. This package is an evidence checkpoint for subsequent work beyond `provisional_v0_1`.

## Methods
- Certified assistance transactions: `analysis.v_certified_assistance_ledger`.
- Current award and program policy classifications: `reference.federal_inflow_award_classification` and `reference.federal_inflow_program_policy_mapping`.
- Award policy takes precedence over program policy; policy validity is assessed for each transaction fiscal year.
- Transactions with no applicable policy and COVID, IIJA, or extraordinary tags are provisional candidates. Tagged buckets are mutually exclusive; a transaction contributes once.
- `INCLUDE_ADDITIVE` remains established; provisional candidates are **not** reclassified as canonical additive.
- Excluded, withheld, reference-only, and unresolved ordinary transactions are not included in expanded provisional assistance.

## Validation and annual results (USD)
| FY | Established additive | Qualified provisional | Expanded provisional |
|---|---:|---:|---:|
| 2018 | 7,388,375,150.75 | 0.00 | 7,388,375,150.75 |
| 2019 | 7,913,240,351.71 | 0.00 | 7,913,240,351.71 |
| 2020 | 15,588,133,958.75 | 991,541,734.03 | 16,579,675,692.78 |
| 2021 | 27,012,354,136.13 | 2,560,720,942.41 | 29,573,075,078.54 |
| 2022 | 11,997,036,710.62 | 1,794,448,658.11 | 13,791,485,368.73 |
| 2023 | 11,257,319,934.71 | 2,400,384,414.22 | 13,657,704,348.93 |
| 2024 | 11,839,873,255.40 | 1,356,271,681.25 | 13,196,144,936.65 |

FY2020–2024 qualified provisional total: **$9,103,367,430.02**. Reproduces DRAFT-1A to the cent.

Checks: zero conflicting transactions in all seven years; tag-bucket difference = 0.00 and universe difference = 0.00 in all seven years. ETL-238B5B output ends with `ROLLBACK`; no permanent DB writes.

## Files
- `238b5a_reconcile_provisional_assistance.sql`: first current-policy diagnostic.
- `238b5b_provisional_assistance_reporting_bridge.sql`: annual reporting bridge.
- `238b5b_stdout_utf8.txt`: validated console evidence converted from Windows UTF-16 to UTF-8 for portability.
- This `README.md`: interpretation, limitations, and next steps.

## Limitations / authorization hold
- Exact aggregate reproduction is not a substitute for a transaction-level historical/current crosswalk or independent cross-family overlap audit.
- FY2018–2019 zero provisional additions reflect available tagging and rules, not proof of full assistance coverage.
- Provisional reporting inclusion is distinct from canonical ledger authorization.
- No adjustment to ETL-238A statewide balance is authorized by this checkpoint alone.
- The wider DRAFT-1 vs ETL-238A fiscal balance gap remains unexplained; compare net provisional receipts against gross IRS collections with separate inflow/outflow bridges before attributing the difference.

## Next session
1. Confirm this evidence package is committed and pushed to GitHub; record commit SHA.
2. Verify FY2020–FY2024 qualified provisional assistance remains reproducible after later policy changes.
3. Reconcile DRAFT-1 provisional net federal receipts versus ETL-238A gross IRS collections, including definitions, fiscal-year basis, and any offsets or adjustments.
4. Preserve DRAFT-1, ETL-238A and expanded provisional series side-by-side; do not target-fit the balances.
5. Extend to FY2018–2019 only when evidence supports the historical classification.

Principle: **Measure first. Explain later.**
