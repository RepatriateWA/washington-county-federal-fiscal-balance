# Rockefeller Methodology Comparison

## Purpose

This document governs the project's replication of the Rockefeller Institute of Government's state balance-of-payments methodology.

## Governing rule

Use Rockefeller's methodology wherever it can be independently reproduced from official public federal data. Every deviation must be documented, justified, cited, and reproducible.

## Rockefeller expenditure framework

The current Rockefeller methodology organizes allocable federal expenditures into five major categories:

1. Direct payments to individuals
2. Grants
3. Contracts and procurement
4. Federal wages
5. COVID-19 relief spending

Rockefeller also retains an unallocable category for expenditures that cannot reasonably be assigned to states, including interest on the federal debt and international assistance.

The methodology uses a two-step structure:

1. Establish national federal-budget control totals.
2. Allocate the allocable totals among states using observed geographic data or the best available proxy.

The allocated state amounts plus other geographic areas and unallocable amounts must reconcile to the federal budget.

## Current Washington implementation

| Component | Rockefeller category | Current status | Principal limitation |
|---|---|---|---|
| Social Security OASDI | Direct payments | Implemented and validated | Current series annualizes December benefits and requires FFY control reconciliation |
| Medicare | Direct payments | Implemented and validated | Medicare Advantage payments are not yet fully represented |
| Medicaid | Grants | Implemented and validated | State observed total; county values would require explicit allocation |
| CHIP | Grants | Implemented and validated | State observed total; county values would require explicit allocation |

These programs are integrated in `reporting.v_washington_tracked_expenditures`, but this view is not yet a complete Rockefeller expenditure total.

## Immediate gaps

The highest-priority missing categories are:

- Federal contracts and procurement, especially Department of Defense obligations
- Other federal grants
- Veterans benefits
- Federal civilian wages
- Active-duty military wages
- Federal and military retirement payments
- Other direct payments, including SSI, nutrition assistance, housing, education assistance, and refundable tax credits
- Separately tagged COVID-19 relief spending for 2020–2023 reconciliation

## Treatment of military-related spending

Military activity is not one line item. It appears in several Rockefeller categories:

- Defense contracts and procurement
- Active-duty and civilian federal wages
- Military retirement direct payments
- Veterans direct payments
- Grants and assistance associated with military or emergency programs

Each stream must be implemented and validated separately to prevent omission or double counting.

## Observed versus allocated values

Every amount must be labeled as one of:

- **Observed:** directly reported for Washington or a Washington county.
- **Allocated:** derived from a documented geographic allocator.
- **Estimated:** calculated using a transparent model when neither observed nor standard allocation data exist.
- **Unallocable:** retained in national reconciliation but excluded from state totals.

Observed, allocated, and estimated values must never be silently combined.

## Definition of done for a category

A category is complete only when:

- Official federal source identified
- Source archived with provenance
- National control total identified
- Geographic allocation method documented
- Reproducible ETL implemented
- Automated validation passes
- Rockefeller comparison completed
- County applicability documented
- Source citations complete
- Coverage matrix updated

## Primary references

- Rockefeller Institute, *Giving or Getting? New York's Balance of Payments with the Federal Government*, 2025.
- Rockefeller Institute Balance of Payments Portal.
- Budget of the United States Government and official federal-agency datasets cited for each component.

## Next work package

**EP-003 WP-001 — Rockefeller Methodology Inventory**

1. Confirm the detailed direct-payment, grant, contract, wage, and COVID component lists from the methodology appendix.
2. Map every component to its national budget control and official geographic allocator.
3. Record existing implementation coverage.
4. Rank gaps by fiscal magnitude and methodological importance.
5. Select the next ETL only after the source, control total, and validation strategy are explicit.
