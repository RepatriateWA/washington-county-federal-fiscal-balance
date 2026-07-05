# ADR-001: Federal Expenditure Warehouse Architecture

**Status:** Accepted

**Date:** July 4, 2026

## Context

The goal of the Washington County Federal Fiscal Balance Project is to measure the relationship between:

* Federal taxes paid by Washington residents and businesses.
* Federal expenditures returned to Washington.

The first phase of the project established an IRS data warehouse containing:

* County-level IRS Statistics of Income (SOI) data for Tax Years 2015–2022.
* State-level IRS collections data for Fiscal Years 2023–2024.

The next phase requires integrating federal expenditure data from multiple agencies and programs.

Unlike the IRS data, there is no single authoritative federal dataset that reports all expenditures at the county level.

The warehouse must therefore support multiple independent data sources while presenting a unified analytical model.

---

# Decision

Federal expenditures will be stored separately from IRS tax data.

The expenditure warehouse will be organized around **program categories**, not source files.

Each data source will load into normalized staging and production tables while sharing common geographic identifiers.

The Washington county FIPS code will serve as the primary geographic key whenever county-level data is available.

State-level datasets will be stored separately and will not be artificially allocated to counties unless a documented allocation methodology has been approved.

---

# Initial Program Categories

The initial Version 1 expenditure warehouse will support the following categories:

1. Social Security
2. Medicare
3. Medicaid
4. Veterans Benefits
5. SNAP
6. Federal Payroll
7. Federal Grants
8. Federal Contracts
9. Highway Funding
10. Education Funding
11. Agriculture Programs
12. Disaster Assistance

Additional categories may be added without redesigning the warehouse.

---

# Design Principles

The expenditure warehouse will follow the same engineering principles established for the IRS warehouse.

## Reproducibility

Every table must be reproducible from publicly available source data.

---

## Traceability

Every record must identify:

* source agency
* source dataset
* reporting period
* import file
* ETL version

---

## Validation

Every loader must include automated validation similar to the IRS validation framework.

Validation will include:

* row counts
* duplicate detection
* orphan geographic references
* required field checks
* source consistency

---

## Geographic Integrity

County-level records will always reference the existing county registry.

State-level records will reference the state registry.

No synthetic county allocations will be created unless explicitly documented.

---

## Versioning

Major structural changes to the warehouse will be documented through additional Architecture Decision Records (ADRs).

---

# Initial Target Sources

The project anticipates integrating data from agencies and systems such as:

* USAspending.gov
* Social Security Administration
* Centers for Medicare & Medicaid Services (CMS)
* Department of Veterans Affairs
* Department of Agriculture (USDA)
* Department of Transportation
* Bureau of Economic Analysis (BEA)
* Other authoritative federal sources as needed

The inclusion of a source does not imply immediate implementation; each source will be evaluated for geographic coverage, data quality, update frequency, and licensing.

---

# Long-Term Objective

The completed warehouse will support analytical calculations including:

Federal Fiscal Balance = Federal Expenditures − Federal Taxes Paid

at both the Washington statewide level and, where data permits, the county level.

This architecture is intended to provide a transparent, reproducible, and extensible platform for analyzing the flow of federal revenues and expenditures in Washington State.
