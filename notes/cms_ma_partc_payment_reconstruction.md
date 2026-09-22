# CMS Medicare Advantage Part C Payment Reconstruction

## Checkpoint v0.1

### Scope

Principal payment reconstruction begins January 2015.

CY2014 is retained as source/provenance material but excluded from the
principal reconstruction because the CY2014 Plan Payment technical notes
do not explicitly document the A/B PMPM standardization convention.

No CY2015-CY2024 payment semantics are back-cast into CY2014.

The currently validated monthly source universe ends September 2024.
Accordingly:

- CY2015-CY2023 are complete calendar years.
- CY2024 currently represents January-September only.

### Payment semantics

For CY2015-CY2024, CMS documentation explicitly identifies Average A/B
PM/PM Payment as standardized to a 1.0 risk score.

Therefore:

    Risk-adjusted A/B PMPM
        = Standardized A/B PMPM * Average Part C Risk Score

The CMS-published Average Rebate PM/PM Payment is treated as a separate
Part C payment component. It is not multiplied by the Part C risk score.

For WCFFBP reconstruction:

    Part C PMPM
        = Risk-adjusted A/B PMPM + Rebate PMPM

and:

    Part C dollars
        = Published numeric enrollment * Part C PMPM

### Rebate definition

In this context, a Medicare Advantage rebate is a CMS payment component
arising when an MA plan's bid is below the applicable benchmark. It
represents the plan's applicable share of the resulting savings under
Medicare Advantage payment rules and may finance supplemental benefits
and/or reductions in beneficiary cost sharing or premiums.

"Rebate" does not mean a refund of a payment previously made by the
beneficiary or plan.

### Enrollment and source limitations

No suppressed enrollment values are imputed.

A published enrollment cell without a corresponding CMS payment cell is
preserved as SOURCE_PAYMENT_CELL_UNAVAILABLE rather than assigned a
fabricated PMPM.

### Reconstruction validation result

Validation scope: January 2015 through September 2024

Required periods:                         117
Periods processed:                        117
Published target member-months:           12,104,643
Reconstructed member-months:              12,104,528
Source payment-cell unavailable:          115
Nonnumeric linked payment inputs:         0
Accounted published member-months:        12,104,643
Unexplained member-months:                0

Reconstruction enrollment coverage:       99.999050%
Published-enrollment accounting coverage: 100.000000%

Risk-adjusted A/B dollars:                $10,045,498,613.35
Rebate dollars:                           $   893,069,777.31
Reconstructed Part C dollars:             $10,938,568,390.66

Duplicate contract keys:                  0
Unresolved contract rows:                 0
Ambiguous SNP contract/plan keys:         0
Unresolved SNP rows:                      0
Duplicate payment keys:                   0

Overall reconstruction validation:        PASS

### Interpretation

PASS establishes deterministic reconstruction of Part C dollars for
directly supported published enrollment cells within the stated scope.

The reconstructed $10.938568 billion is a reconstructed CMS Part C
payment measure. It is not yet a certified WCFFBP federal-inflow ledger
value.

The following remain separate validation gates:

1. Independent payment reconciliation.
2. Completion/treatment of CY2024.
3. County-allocation certification.
4. Database and ledger integration.
5. Final WCFFBP fiscal-balance inclusion.
