# ADR-003 — Extraordinary Funding Classification

**Status:** Accepted

**Date:** 2026-08-05

---

# Context

The Washington County Federal Fiscal Balance Platform measures
federal expenditures received by Washington State and its counties.

USAspending provides several sources of information regarding
extraordinary appropriations, including Disaster Emergency Fund
Codes (DEFCs), award-level supplemental funding amounts,
transaction-level obligations, and Treasury account information.

The platform requires a single methodology for identifying and
measuring extraordinary funding that is transparent,
reproducible, and evidence-based.

---

# Problem

Award-level COVID and IIJA supplemental fields represent
overall-award values.

Transaction records represent individual financial actions.

A transaction belonging to an award that received COVID funding
does not necessarily represent COVID-funded spending.

Classifying every transaction on such an award as COVID would
overstate annual COVID inflows.

---

# Decision

The platform adopts the following principles.

## Principle 1

Annual fiscal flows shall be measured from
transaction-level financial observations.

The primary measurement field is:

    federal_action_obligation

---

## Principle 2

Award-level supplemental funding fields are used for:

• award classification

• reconciliation

• validation

They are not used directly as annual flow measurements.

---

## Principle 3

DEFC codes constitute a reference-data domain.

Observed DEFC values are inventoried without interpretation.

Authoritative classifications are maintained separately in:

    reference.extraordinary_funding_code

---

## Principle 4

Every DEFC classification shall include:

• official description

• public law

• funding family

• confidence

• citation

No classification may rely solely upon project inference.

---

## Principle 5

Funding families remain mutually distinguishable.

Current families include:

• Ordinary

• COVID

• IIJA

• Disaster

• Wildfire Suppression

• Other Emergency

• Not Designated

• Unresolved

---

# Consequences

The platform can:

✓ reproduce every classification

✓ update classifications without changing ETL code

✓ trace every decision to authoritative evidence

✓ separate recurring federal expenditures from extraordinary appropriations

✓ generate annual fiscal-flow series that are methodologically consistent

---

# Rationale

The project is guided by one overarching principle:

    Measure first.
    Explain later.

Classification exists to improve measurement,
not to influence conclusions.

## Related Components

ETL-005A
ETL-114
reference.extraordinary_funding_code
defc_classification.csv