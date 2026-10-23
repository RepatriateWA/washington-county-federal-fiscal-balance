# ETL-229 - CHIP Authorization Decision

## Decision
QUALIFIED_PROVISIONAL_INFLOW

## Scope
Washington CMS-21 CHIP and MCHIP additive federal-share
expenditures, FFY2018-FFY2024.

MCHIP 20 percent financing adjustments excluded.

## Seven-year total
$1,137,550,029

## Accounting source
chip.v_cms21_control_totals
reporting.v_washington_chip_expenditures

## Certification evidence
ANALYSIS-218-v1
ETL-218D - current rerun PASS, 14 exact CMS reconciliations
ETL-218F - current rerun PASS, unique effective dispositions
ETL-218G - existing reporting-lineage certification
ETL-229A3 - current read-only verification

## Nonduplication
USAspending AL 93.767 transactions are classified
EXCLUDE_DUPLICATE or WITHHOLD_UNRESOLVED in the tested scope.

No separate AL 93.767 obligation amount is authorized.
WITHHOLD_UNRESOLVED transactions remain withheld.

## Qualifications
Statewide CMS expenditure control only.
No county allocation certification.
No universal cross-source overlap certification.
No complete federal fiscal balance certification.
No EPS-001 evidence-package compliance claim.

Authorization is subject to independent ETL-229C
cross-version regression validation.
