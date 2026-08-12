# AP-001 — Washington State Extraordinary Federal Funding Analysis

## Washington County Federal Fiscal Balance Project

---

# Purpose

AP-001 is the first analytical work package built upon the certified ETL warehouse established by ETL-005.

Its purpose is to measure extraordinary federal funding flowing into Washington State using a transparent, reproducible, evidence-based methodology.

Unlike ETL-005, which was responsible for data acquisition and normalization, AP-001 is responsible for measurement, analysis, and reporting.

Every analytical result produced by AP-001 must be traceable to certified warehouse data and reproducible from repository artifacts.

---

# Project Philosophy

The Washington County Federal Fiscal Balance Project is guided by a simple principle:

> **Measure first. Explain later.**

AP-001 exists to produce reliable measurements before any policy interpretation.

The purpose of this work package is not to advocate for any particular conclusion.

Its purpose is to establish transparent facts.

---

# Objectives

AP-001 has six primary objectives.

1. Measure extraordinary federal funding received by Washington State.

2. Distinguish extraordinary funding by funding family, including:

   * COVID
   * Emergency
   * Disaster
   * Wildfire Suppression
   * Infrastructure Investment and Jobs Act (IIJA)

3. Support both:

   * inclusive measurements
   * COVID-excluded measurements

4. Preserve complete analytical provenance from every published number back to original USAspending source transactions.

5. Produce county-level analytical outputs suitable for later federal fiscal balance calculations.

6. Establish a reusable analytical framework for future work packages.

---

# Scope

AP-001 analyzes only federally reported USAspending Assistance data processed through ETL-005.

This work package does not:

* estimate missing federal expenditures,
* estimate federal taxation,
* calculate donor/recipient status,
* infer political conclusions.

Those analytical efforts belong to future work packages.

---

# Inputs

AP-001 depends upon the certified warehouse produced by ETL-005.

Primary inputs include:

* Canonical Assistance Transactions
* Canonical Awards
* Canonical Recipients
* Recipient History
* Agencies
* Places
* Assistance Listings
* Assistance Types
* Extraordinary Funding Relationships
* County Reference Data

---

# Primary Deliverables

AP-001 will produce:

## Certified Analytical Ledger

A transaction-level analytical view joining every certified warehouse dimension.

One row represents one transaction.

No aggregation occurs in this layer.

---

## Washington Attribution

Certified attribution of transactions using both:

* recipient geography
* place-of-performance geography

These attribution methods are intentionally preserved separately.

---

## Analytical Measurements

Measurements including:

* Fiscal Year totals
* Funding Family totals
* Agency totals
* Assistance Listing totals
* County totals
* Recipient totals

---

## Comparative Views

Separate measurements for:

* All Extraordinary Funding
* COVID Funding
* Non-COVID Extraordinary Funding
* Emergency Funding
* Disaster Funding
* Wildfire Suppression Funding
* IIJA Funding

---

## Publication Tables

Publication-ready datasets supporting reports and visualizations.

---

# Engineering Principles

Every AP-001 artifact shall satisfy the following principles.

## Reproducibility

Every published number must be reproducible from repository code.

---

## Traceability

Every published number must trace back to source transactions.

---

## Transparency

Methodology shall be public and documented.

---

## Immutability

Raw warehouse data shall never be modified by analytical processes.

---

## Evidence

Evidence accompanies every significant analytical output.

---

## Separation of Concerns

ETL prepares data.

Analysis measures data.

Interpretation explains data.

These responsibilities remain distinct.

---

# Validation

Every analytical product shall include validation demonstrating:

* source row counts,
* transaction reconciliation,
* county reconciliation,
* funding-family reconciliation,
* reproducibility of totals,
* citation of data sources,
* analytical assumptions.

---

# Repository Structure

```
analysis/
└── AP-001/
    ├── README.md
    ├── sql/
    ├── python/
    ├── evidence/
    ├── outputs/
    ├── documentation/
    ├── AP-001_METHOD.md
    ├── AP-001_VALIDATION.md
    └── AP-001_RESULTS.md
```

---

# Expected Outputs

Examples of planned analytical products include:

* Washington State Extraordinary Federal Funding Report
* County Extraordinary Funding Summary
* COVID vs Non-COVID Funding Comparison
* Extraordinary Funding by Federal Agency
* Extraordinary Funding by Assistance Listing
* Extraordinary Funding by Recipient
* Extraordinary Funding Time Series

---

# Relationship to Future Work

AP-001 establishes the analytical foundation for future project phases, including:

* Washington State Federal Fiscal Balance
* County-Level Federal Fiscal Balance
* Federal Revenue Attribution
* Net Federal Fiscal Balance Calculations
* Public Reporting
* Legislative Support Materials

---

# Acceptance Criteria

AP-001 shall be considered complete when:

* every published measurement is reproducible;
* every published measurement is traceable to certified warehouse data;
* all analytical SQL, Python scripts, evidence, and documentation are committed to the repository;
* validation demonstrates complete reconciliation between published results and warehouse inputs;
* the work package produces publication-ready outputs suitable for public distribution.

---

# Long-Term Vision

The Washington County Federal Fiscal Balance Project seeks to provide the citizens of Washington with transparent, evidence-based measurements describing the fiscal relationship between Washington State and the United States federal government.

AP-001 represents the first analytical realization of that vision.

By combining rigorous engineering, transparent methodology, and reproducible analysis, this work package establishes the foundation for future statewide and county-level fiscal balance reporting.

Rather than asking citizens to trust conclusions, the project enables them to examine the underlying evidence, methodology, and calculations for themselves.
