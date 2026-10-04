# CMS Medicare Evidence

This directory contains selected validation and analytical evidence supporting the
Washington County Federal Fiscal Balance Project (WCFFBP) treatment of Medicare
payment streams and Medicare geographic-incidence questions.

These files are retained as public audit evidence. They are not, by themselves,
ledger entries or authorization to allocate federal expenditures to Washington
counties.

## Methodological principle

WCFFBP separates:

1. source measurement,
2. source and field semantics,
3. overlap and reconciliation,
4. accounting-policy decisions,
5. ledger inclusion, and
6. geographic incidence or allocation.

A successful source validation or geographic feasibility test does not
automatically establish that a payment stream should be added to the fiscal
ledger or allocated to a county.

## Directory structure

### `accounting/`

Evidence concerning the accounting boundaries among Medicare payment streams.

- `cms_medicare_payment_stream_additivity_v0_1_console.txt`

  Tests the relationship among the principal Medicare payment streams used in
  the project: Original Medicare fee-for-service, Medicare Part C, and Medicare
  Part D. The analysis establishes the tested pairwise accounting relationships
  and guards against double counting.

- `cms_rds_accounting_review.txt`

  Reviews the Medicare Part D Retiree Drug Subsidy (RDS). Economic additivity is
  distinguishable from geographic incidence. Washington beneficiary incidence
  can be observed, but Washington and county payment-dollar incidence remain
  unresolved. The evidence therefore does not authorize beneficiary-count or
  sponsor-name allocation of RDS dollars.

- `cms_wa_mffs_ffs_overlap_v0_2_console.txt`

  Reviews Medicare performance/payment material relative to Original Medicare
  fee-for-service. The streams may be economically distinct, but unresolved
  federal-fiscal-year cash timing and geographic incidence prevent automatic
  ledger inclusion.

## `original_medicare/`

Evidence supporting Original Medicare fee-for-service source and geographic
validation.

- `cms_original_medicare_ffs_v0_2_console.txt`

  Validates the Washington county-year Original Medicare FFS analytical
  structure, including county coverage, key uniqueness, and aggregate /
  per-capita identities.

- `cms_original_medicare_geo_v0_2_output.txt`

  Source-certification evidence for the geographic data used in the Original
  Medicare analysis. Suppressed service-component observations remain
  explicitly distinguished from observed zero values.

## `mssp/`

Evidence concerning the Medicare Shared Savings Program (MSSP), particularly
assigned-beneficiary county geography and the feasibility and limitations of
county-level analytical use.

The retained validation sequence includes:

- source validation,
- 2019 regular and off-cycle cohort linkage,
- 2016-2018 county-file profiling,
- county-value semantics,
- suppression constraints,
- geographic beneficiary bounds,
- auxiliary-estimator feasibility, and
- EarnSaveLoss sensitivity analysis.

These files represent different analytical questions and therefore should not
be interpreted as a simple sequence in which each later version supersedes all
earlier evidence.

For the 2019 analysis, regular January observations and July/off-cycle
observations represent participation-period cohorts. An ACO appearing in both
cohorts must not be deduplicated merely because the ACO identifier is the same.

Suppressed observations are not treated as zero.

The MSSP evidence does not, by itself, authorize EarnSaveLoss allocation to
Washington counties or infer county-level dollar incidence from administrative
or beneficiary geography. Unresolved source semantics and geographic
limitations remain explicit where applicable.

## Evidence status

The files in this directory are retained because they establish substantive
validation, accounting-boundary, overlap, geographic, suppression, or
sensitivity findings.

Temporary discovery inventories, failed or superseded validation runs,
zero-byte placeholders, code-search outputs, and publication-review working
files are intentionally excluded from this evidence package.

Canonical executable methodology remains in the repository's source-code and
ETL directories. These evidence files preserve selected execution results
needed to audit the conclusions produced by that methodology.

## Reproducibility

Where upstream CMS source payloads are large and reproducible from authoritative
sources, WCFFBP does not ordinarily use Git as a bulk-data archive. Source
provenance, acquisition methodology, validation evidence, and analytical code
are retained so that the analysis can be independently examined and reproduced.

## Interpretation

A `PASS` in an individual validation artifact means that the specific test
defined by that artifact passed. It does not imply that every downstream
accounting, ledger, or geographic-incidence question has been resolved.

This distinction is intentional and is central to the WCFFBP methodology:
measure first, reconcile explicitly, and make accounting or allocation
decisions only when supported by evidence.
