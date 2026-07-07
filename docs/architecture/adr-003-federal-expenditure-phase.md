# ADR-003: Federal Expenditure Subsystem

**Status:** Accepted

**Date:** 2026-07-06

## Context

Version 0.7 established the Revenue Foundation for the Washington County Federal Fiscal Balance project.

The system now imports and validates official IRS revenue data from two independent federal publication series:

- IRS Statistics of Income (SOI)
- IRS Data Book

These datasets provide a reproducible estimate of the federal revenues collected from Washington State and, where available, its counties.

The second half of the project requires measuring the federal expenditures returned to Washington in order to calculate fiscal balance.

---

## Decision

The expenditure subsystem will be developed incrementally by federal agency.

Each agency will become an independent ETL subsystem with its own:

- source acquisition
- staging
- transformation
- validation
- reporting

Each subsystem must be independently executable and independently testable.

---

## Initial Agency Order

The project will ingest expenditure datasets in the following order:

1. Social Security Administration (SSA)
2. Centers for Medicare & Medicaid Services (CMS)
3. USAspending.gov
4. Department of Veterans Affairs
5. Federal payroll
6. Additional agencies as required

This ordering reflects both fiscal significance and data availability.

---

## Architectural Principles

Every expenditure subsystem will follow the same engineering standards established for the IRS subsystem.

Each subsystem shall provide:

- automated download or standardized raw-data ingestion
- deterministic ETL
- PostgreSQL loading
- validation scripts
- release validation integration
- reproducible reporting

No manual database edits will be permitted.

---

## Database Design

Each agency will own its own schema or logical namespace.

Example:

```
ssa.*
cms.*
usaspending.*
```

Reference data will remain centralized.

Shared lookup tables will not be duplicated.

---

## Reporting

Reporting scripts will never read raw files.

Reporting will query PostgreSQL exclusively.

Future reporting views will provide a stable interface between ETL and analysis.

---

## Long-Term Goal

The completed platform will estimate, by county and year:

- Federal revenues collected
- Federal expenditures received
- Net fiscal balance

The project aims to provide a transparent, reproducible, and auditable methodology for estimating federal fiscal balance at the county level for Washington State.

---

## Version Milestone

Version 0.8 is defined as:

> First production-quality federal expenditure subsystem.

Initial implementation target:

Social Security Administration.