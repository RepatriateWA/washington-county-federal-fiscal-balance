# ETL-238B7 — IRS Refund and DRAFT-1 Chart Lineage Review

Status: EVIDENCE REVIEW — NO ACCOUNTING AUTHORIZATION
Period: Federal fiscal years 2018–2024
Scope: Washington statewide fiscal-balance analysis

## 1. Purpose

Determine whether the existing statewide fiscal-balance
calculations deduct federal tax refunds from IRS gross
collections, and assess whether the historical DRAFT-1
chart calculation is reproducible.

## 2. IRS Gross Collections

The accounting registry authorizes IRS_GROSS_COLLECTIONS
as a qualified provisional outflow for FY2018–FY2024.

The measure represents Washington-attributed IRS gross
collections, not a final estimate of federal tax economic
incidence on Washington residents.

## 3. Refund Evidence — ETL-238B6C

The read-only profile of irs.state_collections returned
seven Washington Total observations for FY2018–FY2024.

All seven observations contain gross collections.

All seven observations have NULL values for:
- refunds_issued
- refund_amount_thousands

Consequently, candidate net collections cannot be
calculated from these records.

NULL refund amounts must not be interpreted as zero.

No refund adjustment is authorized by this review.

## 4. DRAFT-1 Reporting Investigation

The following evidence was examined:

- ETL-194 historical accounting bridge
- IRS state collections loader
- IRS_AUTHORIZATION_DECISION.md
- ETL-238B4 reporting controls
- DRAFT-1 statewide evidence README
- ETL-238B6D repository chart-lineage search
- ETL-238B6E historical search review

The inspected reporting controls do not demonstrate
a subtraction of IRS refunds.

The original DRAFT-1 chart-generation calculation
was not recovered.

The historical chart values therefore remain
unreconciled and must not be represented as
independently reproduced.

This finding does not invalidate the underlying
component evidence preserved in DRAFT-1.

## 5. Accounting Disposition

IRS_GROSS_COLLECTIONS:
  Existing authorization unchanged.

IRS_NET_COLLECTIONS:
  Not authorized.

DRAFT-1 chart values:
  Historical preliminary reference only.
  Calculation lineage unresolved.

No database changes.
No ledger changes.
No source-family reclassification.

## 6. Next Analytical Priority

Construct a reproducible FY2018–FY2024 statewide
balance using verified federal inflows and the
existing IRS gross-collections outflow control.

Report qualified provisional components separately.

Explicitly disclose incomplete Medicare coverage,
refund uncertainty, timing limitations, and other
known deficiencies.

Preserve the convention:

  Federal inflows minus federal outflows.

A negative balance indicates net federal dollars
withdrawn from Washington under the measures used.

## 7. Governing Principle

Measure first. Explain later.