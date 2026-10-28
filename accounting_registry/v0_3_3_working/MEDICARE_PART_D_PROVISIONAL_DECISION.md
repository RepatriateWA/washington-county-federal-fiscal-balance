# Medicare Part D - Qualified Provisional Reporting Decision

## ETL-242A5

**Disposition: INCLUDE IN QUALIFIED PROVISIONAL REPORTING.**

Seven-year observed Part D addition: **$9869347614.65**.

This is a reporting-layer decision, not canonical-ledger authorization.

## Evidence

- CMS Medicare accounting boundary certification v0.1.
- CMS payment-stream additivity certification v0.1.
- CMS Medicare accounting integration annual profile.
- ETL-242A2 and ETL-242A3 evidence reviews.
- ETL-242A5 exact registry/annual-matrix/CMS reconciliation.

Original Medicare A/B, Part C, and Part D represent distinct
payment streams. Do not separately add the Medicare Core parent.
The Part D reconciliation workbook is a control, not another inflow.
USAspending AL 93.774 is an identified Medicare SMI duplicate.

## Scope and limitations

- Part D uses observed Washington county CPSC enrollment linked
  to CMS plan-payment observations.
- Only exact same-year contract/PBP matches are reconstructed.
- Unmatched and suppressed payment dollars are not imputed.
- Part D has partial dollar coverage in all seven years.
- Calendar year 2024 contains January-September Part D only.
- Calendar-year observations are not converted to FFY cash flows.
- The selected-assistance cross-family nonduplication review is
  qualified, not universally certified.
- Prior Part D reconciliation parent-organization failures remain
  documented; no failed control has been silently overridden.

## Ledger protection

All seven MEDICARE_PART_D canonical rows retain
NOT_YET_AUTHORIZED, with blank authorized amounts.
No database writes or canonical ledger modifications.

## Reporting

Use 242a5_partd_inclusive_balance.csv as a separate qualified
reporting bridge. Preserve the existing expanded-balance file.
The bridge's annual balances use IRS gross collections.
A separate seven-year IRS-net control incorporates aggregate refunds;
do not present it as annual IRS-net evidence.

## Reopening criteria

Reopen only for materially new federal payment evidence,
a demonstrated cross-family overlap, corrected CMS observations,
revised source coverage, or an approved CY-to-FFY conversion.

Do not repeat the already certified Medicare A/B-Part C-Part D
payment-stream additivity investigation without new evidence.
