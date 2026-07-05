# ADR-002: Initial Federal Expenditure Data Source — Social Security (OASDI)

**Status:** Accepted

**Date:** July 4, 2026

## Context

The Washington County Federal Fiscal Balance Project seeks to measure both sides of the federal fiscal equation:

* Federal taxes paid
* Federal expenditures received

Following completion of the IRS warehouse, the next phase is to establish a reproducible federal expenditure warehouse.

The project requires an initial expenditure dataset that is:

* Publicly available
* Published by an authoritative federal agency
* Available at the county level
* Stable from year to year
* Suitable for automated ETL and validation

## Decision

The first expenditure dataset integrated into the warehouse will be the **Social Security Administration (SSA) OASDI Beneficiaries by State and County** publication.

This dataset will serve as the reference implementation for all future expenditure loaders.

## Rationale

The SSA OASDI county dataset was selected because it:

* Is published directly by the Social Security Administration.
* Provides county-level geographic detail.
* Includes annual benefit payments and beneficiary counts.
* Uses a stable reporting format.
* Covers one of the largest federal expenditure programs.
* Can be validated against published statewide totals.

The ETL process developed for this dataset will establish patterns that can later be reused for Medicare, Medicaid, Veterans Affairs, USAspending.gov, and other federal programs.

## Data Quality Principles

The Social Security loader will follow the same engineering standards established for the IRS warehouse.

Each ETL run must:

* Preserve the original source file.
* Be fully reproducible.
* Load data into normalized warehouse tables.
* Record the source file and reporting year.
* Perform automated validation.
* Produce deterministic results.

## Geographic Standards

County records will reference the existing county registry through county identifiers.

Statewide totals will reference the state registry.

No estimated allocations will be created.

## Future Expansion

Completion of the Social Security loader will establish the standard architecture for future expenditure datasets, including:

* Medicare
* Medicaid
* Veterans Benefits
* SNAP
* Federal Grants
* Federal Contracts
* Highway Funding
* Education Funding
* Agriculture Programs
* Disaster Assistance

## Success Criteria

This ADR will be considered successfully implemented when:

1. County-level Social Security data can be loaded into the expenditure warehouse.
2. Validation confirms consistency with published SSA totals.
3. The data can be joined with the IRS warehouse using the county registry.
4. Analysts can compare estimated federal taxes with Social Security expenditures for Washington counties.

This ADR establishes the first production expenditure source for the Washington County Federal Fiscal Balance Project and provides the architectural template for future federal expenditure integrations.
