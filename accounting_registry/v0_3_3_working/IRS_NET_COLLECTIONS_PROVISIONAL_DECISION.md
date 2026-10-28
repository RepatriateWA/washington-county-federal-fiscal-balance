# ETL-239B1G3 — IRS Net Collections Provisional Accounting Decision

**Project:** Washington County Federal Fiscal Balance Project (WCFFBP)  
**Period:** Federal fiscal years 2018–2024  
**Status:** QUALIFIED PROVISIONAL ACCOUNTING DECISION — CANONICAL AUTHORIZATION WITHHELD

## 1. Decision

Adopt Washington-attributed IRS net collections as the preferred **provisional reporting scenario** for the seven-year statewide fiscal balance, subject to the qualifications below.

Retain gross IRS collections as an independently reproducible administrative control and comparison scenario.

This decision does not authorize new canonical ledger entries or supersede existing source-family authorizations.

## 2. Accounting convention

Net IRS collections = Gross IRS collections − IRS refunds issued.

Statewide fiscal balance = Federal inflows to Washington − Federal outflows from Washington.

IRS refunds are deducted once from gross collections in the net-basis scenario. Economic Impact Payments and advance Child Tax Credit payments are included within the published refund totals and are not added a second time.

This convention treats the IRS refund total as a reduction of administrative collections for provisional reporting. It does not establish that every refund component represents repayment of previously collected taxes.

## 3. Seven-year controls

| Measure | FY2018–FY2024 |
|---|---:|
| Expanded provisional federal inflows | $577,050,573,172.54 |
| IRS gross collections | $877,156,759,000.00 |
| IRS refunds issued, including interest | $92,094,284,000.00 |
| IRS net collections candidate | $785,062,475,000.00 |
| Gross-basis provisional balance | −$300,106,185,827.46 |
| Net-basis provisional candidate balance | −$208,011,901,827.46 |

ETL-239B1G2 passed all seven annual and aggregate arithmetic reconciliations.

## 4. Refund classification

The original IRS Table 8 worksheets establish that the FY2020–FY2022 individual refund hierarchy includes traditional refunds, Economic Impact Payments, and, for FY2021–FY2022, advance Child Tax Credit payments.

These are nested categories. Their amounts must not be summed independently with the IRS total refund amount.

The full refund total also contains other IRS tax-category refunds. The accounting meaning of traditional refunds and other refundable-credit components requires qualification.

## 5. Cross-family overlap

The seven-year source-family bridge includes no separate amount under REFUNDABLE_TAX_CREDITS.

Prior Treasury assistance reviews did not demonstrate direct EIP or advance CTC duplication within the Treasury programs examined.

These findings reduce identified overlap risk but do not prove transaction-level nonduplication across every federal expenditure source.

The net-basis scenario is therefore qualified provisional, not fully certified.

## 6. Limitations

- IRS administrative geographic attribution is not equivalent to ultimate economic tax incidence.
- Gross collections and refunds may differ in timing and underlying tax periods.
- IRS refunds include payments that are not necessarily repayments of previously collected taxes.
- Federal inflows combine source families with differing timing and measurement bases.
- Medicare and other expenditure coverage remains incomplete.
- COVID-era payment composition materially affects annual comparisons, particularly FY2020–FY2022.
- The seven-year estimate must not be described as a complete or final federal fiscal-incidence calculation.

## 7. Registry disposition

Preserve the existing IRS_GROSS_COLLECTIONS authorization.

Record IRS_NET_COLLECTIONS as a qualified provisional reporting candidate only.

Do not change canonical_annual_ledger.csv authorized amounts or authorize other source families through this decision.

Preserve both gross-basis and net-basis reporting scenarios and their source evidence.

## 8. Evidence

- ETL-239B1E8: Refund category hierarchy reconciliation.
- ETL-239B1E9: Source-family and assistance overlap investigations.
- ETL-239B1E9F: Original IRS worksheet header verification.
- ETL-239B1G1: Gross-basis expanded balance reconciliation.
- ETL-239B1G2: Net-basis annual and aggregate reconciliation.
- IRS_AUTHORIZATION_DECISION.md: Existing gross-collections authorization.
- UNIFIED_MODEL.md: Canonical sign convention and ledger separation.

## 9. Governing principle

**Measure first. Explain later.**

No database changes. No canonical ledger authorization.