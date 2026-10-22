# WCFFBP Accounting Registry

**Project:** Washington County Federal Fiscal Balance Project  
**Guiding principle:** Measure first. Explain later.  
**Registry status:** WORKING — NOT YET PROMOTED  
**Current working version:** v0_3_0_working

## Start Here

This document is the permanent entry point for WCFFBP accounting work.

Before beginning a substantive research session:

1. Inspect the current Git branch, HEAD, and tracked modifications.
2. Read [Registry Governance](accounting_registry/REGISTRY_GOVERNANCE.md).
3. Review the current registry version and completeness statistics.
4. Identify unresolved material accounting gaps.
5. Inspect existing repository evidence before creating new ETL work.

The five mandatory operating rules and regression safeguards are established in the governance document.

## Current Registry

Working directory:

`accounting_registry/v0_3_0_working/`

Principal files:

- `README.md`
- `CHANGELOG.md`
- `annual_accounting_matrix.csv`
- `canonical_annual_ledger.csv`
- `evidence_crosswalk.csv`
- `source_family_registry.csv`

The working registry is not yet the authoritative accounting ledger.

No annual ledger amounts have been authorized for inclusion merely because they appear as observed candidates.

## Completeness Baseline

Last reported checkpoint: ETL-226A.

| Measure | Count |
|---|---:|
| Source families | 23 |
| Fiscal years | 7 (2018–2024) |
| Family-year cells | 161 |
| Observed cells | 100 |
| Missing cells | 61 |
| Independently verified cells | 63 |
| Families with observations | 14 |
| Families without observations | 9 |

These figures are a historical checkpoint, not an automatically refreshed measurement.

A new registry version must preserve the prior snapshot and report all completeness changes.

## Current Work

**Active task:** ETL-226C5G — Accounting registry reconciliation.

Immediate priorities:

1. Establish registry regression safeguards.
2. Reconcile established assistance-program policies with the registry.
3. Preserve historical FY2018–FY2019 policy extensions separately.
4. Produce a proposed registry update and before/after completeness comparison.
5. Promote a registry version only after validation.

## Accounting Discipline

Source observations, independent verification, overlap reconciliation, and ledger authorization are distinct states.

An `INCLUDE_ADDITIVE` USAspending assistance disposition does not, by itself, establish that an amount is an authorized cash-expenditure ledger entry.

Do not add overlapping source families together without explicit reconciliation.

## Repository Safety

- Inspect existing work before writing replacements.
- Never use blanket staging commands for accounting work.
- Preserve unrelated local modifications.
- Commit narrowly scoped, verified changes.
- Keep diagnostic evidence available for future review.

## Continuity

At each substantive checkpoint, update this entry point with:

- Current registry version and status
- Latest validated completeness statistics
- Most recent completed ETL task
- Next recommended task
- Material unresolved accounting questions

Progress is cumulative. Evidence and accounting decisions must remain auditable.
