# WCFFBP Accounting Registry

**Project:** Washington County Federal Fiscal Balance Project

**Guiding principle:** Measure first. Explain later.

**Registry status:** VALIDATED WORKING ? NOT FINAL FISCAL BALANCE

**Current working version:** `v0_3_3_working`

## Start Here

Read:

1. [Registry Governance](accounting_registry/REGISTRY_GOVERNANCE.md)
2. [Current Registry README](accounting_registry/v0_3_3_working/README.md)
3. [Current Changelog](accounting_registry/v0_3_3_working/CHANGELOG.md)
4. [Canonical Annual Ledger](accounting_registry/v0_3_3_working/canonical_annual_ledger.csv)
5. [Annual Accounting Matrix](accounting_registry/v0_3_3_working/annual_accounting_matrix.csv)

## Latest Validated Checkpoint

ETL-229C: CHIP qualified authorization regression PASS.

| Measure | Count |
|---|---:|
| Source families | 23 |
| Fiscal years | 7 (2018-2024) |
| Family-year observations | 161 |
| Potential ledger observations | 147 |
| Authorized annual observations | 21 |
| Authorized families | 3 |

Authorized families:

- IRS_GROSS_COLLECTIONS: seven qualified provisional
  outflow controls, totaling $877,156,759,000.
- MEDICAID: seven qualified provisional inflow
  controls, totaling $73,016,313,670.
- CHIP: seven qualified provisional inflow
  controls, totaling $1,137,550,029.

These are individual accounting controls, not a complete
or publishable federal fiscal balance.

## Current Work

**Next task:** Select the next unauthorised accounting family
using the registry's evidence and readiness status.

Maintain separate treatment of expenditure controls,
obligations, timing bases, and overlapping source families.

## Mandatory Operating Discipline

- Inspect Git HEAD and tracked modifications.
- Review the current registry and existing evidence first.
- Distinguish observed, verified, reconciled, and authorized.
- Never add overlapping accounting families without review.
- Validate every change against the preceding registry version.
- Never stage unrelated files or use blanket `git add`.
- Preserve prior registry versions and audit evidence.

## Continuity

The registry is the permanent restart reference.
Update this page after each committed family authorization.
