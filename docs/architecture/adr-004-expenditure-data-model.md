  # ADR-004: Expenditure Data Model

**Status:** Accepted

**Date:** 2026-07-07

## Context

Version 0.8 introduces the Federal Expenditure Subsystem.

Unlike the IRS revenue subsystem, federal expenditures originate from multiple agencies, each administering numerous programs. The data model must accommodate new programs without requiring schema redesign.

The system is expected to ingest data from:

- Social Security Administration (SSA)
- Centers for Medicare & Medicaid Services (CMS)
- Department of Veterans Affairs (VA)
- USAspending.gov
- Office of Personnel Management (OPM)
- Additional federal agencies as required.

---

## Decision

The expenditure subsystem will organize data primarily by **agency**, not by individual program.

Each agency will expose one or more generalized fact tables.

Programs will be represented by categorical attributes rather than separate tables whenever practical.

---

## Example

Instead of creating:

```
ssa.retirement_benefits
ssa.disability_benefits
ssa.survivor_benefits
ssa.ssi_benefits
```

the project will prefer:

```
ssa.benefit_payments
```

with:

| Column | Description |
|---------|-------------|
| benefit_type | Retirement, Disability, Survivors, SSI |
| report_year | Reporting year |
| county_id | County receiving payments |
| beneficiary_count | Number of beneficiaries |
| annual_benefits_thousands | Annual payments |
| source_file | Original publication |

---

## Similar Pattern

CMS

```
cms.payments
```

Program types

- Medicare
- Medicaid
- CHIP

---

VA

```
va.benefits
```

Benefit types

- Compensation
- Pension
- Education
- Medical

---

USAspending

```
usaspending.awards
```

Award types

- Grant
- Contract
- Direct Payment
- Loan

---

## Advantages

This model provides:

- fewer database tables
- consistent ETL patterns
- simpler validation
- simpler reporting
- easier future expansion
- reduced schema churn

---

## Reporting

Reporting views should aggregate by:

- agency
- program
- county
- fiscal year

without requiring knowledge of the underlying ETL.

---

## Guiding Principle

New federal programs should generally result in **new rows**, not **new tables**.

New tables should only be introduced when a program has substantially different structure that cannot be represented by the generalized agency schema.

---

## Consequences

The first SSA implementation may initially use:

```
ssa.county_oasdi_benefits
```

during development.

Before Version 1.0, the schema will be consolidated into:

```
ssa.benefit_payments
```

to align with the long-term architectural model.  