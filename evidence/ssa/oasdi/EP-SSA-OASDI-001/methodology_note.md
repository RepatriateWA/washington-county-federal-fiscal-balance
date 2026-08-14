# EP-SSA-OASDI-001 Methodology Note

## Source and Scope
The dataset is the Social Security Administration county-level OASDI beneficiary and benefit-amount series for Washington State, report years 2015 through 2024.

## Published TOTAL Is the Authoritative County Monetary Control
SSA monetary values are published in thousands of dollars. Benefit-type amounts and TOTAL amounts are independently rounded by SSA. Therefore, component monetary sums are expected to differ slightly from the separately published TOTAL.

For certification purposes, the published TOTAL is retained as the authoritative county control value. Component-to-TOTAL reconciliation is evaluated using a documented tolerance derived from the maximum expected accumulation of source rounding.

The validator uses a conservative monthly county tolerance of +/- $5,000. The annualized tolerance is +/- $60,000 because annualized values are the monthly amount multiplied by 12.

## Beneficiary Counts
Published TOTAL beneficiary counts reconcile exactly to the sum of the eight component benefit categories for every county/year observation.

## Annualization Convention
The normalized annualized measure is:

    annualized benefit amount = December monthly benefit amount x 12

This is an annualized December run-rate. It is not a direct observation of benefits actually paid during the corresponding federal fiscal year.

## Balance-of-Payments Limitation
This package certifies faithful acquisition, normalization, structure, reference integrity, reconciliation, and reporting of the SSA OASDI county series. It does NOT, by itself, certify the December-x-12 amount as the final ledger measure for federal fiscal-year balance-of-payments accounting.

## Program Mapping
The eight component benefit types map to federal program categories. The published TOTAL is intentionally not assigned to one federal program because it combines multiple OASDI program categories.
