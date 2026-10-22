# WCFFBP Accounting Registry — Governance and Continuity Protocol

**Status:** Proposed permanent project governance policy  
**Applies to:** Washington County Federal Fiscal Balance Project (WCFFBP)  
**Guiding principle:** *Measure first. Explain later.*

## Purpose

The accounting registry is the project's authoritative record of completeness, evidence, reconciliation, and accounting authorization.

Its purpose is to preserve cumulative progress, identify outstanding work, prevent accidental regression, and provide a reproducible starting point for every future research session.

## Five Mandatory Operating Rules

### Rule 1 — Registry First

Every substantial work session begins by reviewing the current accounting registry, its completeness summary, outstanding material gaps, and next authorized ETL task.

Previously completed investigations must be located and reviewed before new work is undertaken.

### Rule 2 — No Loss of Established Evidence

Previously verified observations must not silently disappear or be overwritten.

If subsequent evidence challenges an observation, preserve the original value, source, verification status, and reasoning. Record the revised conclusion separately with an explicit explanation.

### Rule 3 — Separate Evidence from Authorization

The registry must distinguish among:

- Source observation
- Independent verification
- Accounting reconciliation
- Overlap resolution
- Authorization for ledger inclusion

An observed or verified amount is not automatically an authorized accounting amount.

### Rule 4 — Explicit Completeness Accounting

Every defined source-family and fiscal-year combination must remain represented in the registry, including missing observations.

Each record must identify its current status, supporting evidence, unresolved requirements, and materiality where available.

The completeness denominator must not change silently when new sources or families are introduced.

### Rule 5 — Controlled Versioning

Every approved registry update must preserve the previous version and provide a changelog identifying:

- Records added, revised, or superseded
- Amounts or classifications changed
- Evidence supporting each change
- Effects on completeness and accounting totals
- Remaining unresolved issues

Updates must pass validation before becoming authoritative.

## Mandatory Regression Safeguards

Every proposed registry revision must be checked for:

1. Disappearing source observations
2. Missing or invalid evidence references
3. Unauthorized status transitions
4. Duplicate or overlapping accounting amounts
5. Unexplained changes in observed or authorized values
6. Changes to the source-family/year completeness denominator
7. Failures to preserve prior authoritative versions

A failed regression check blocks promotion of the new registry version until the discrepancy is explained and resolved.

## Session Restart Protocol

At the beginning of each substantive WCFFBP session:

1. Inspect the repository and current Git status.
2. Read `ACCOUNTING_REGISTRY.md`.
3. Read this governance protocol.
4. Load the current authoritative registry version.
5. Review the completeness summary and unresolved material gaps.
6. Confirm the next ETL task against existing repository evidence.
7. Proceed without repeating previously certified work unless a documented reason requires reconsideration.

## Core Principle

**Progress is cumulative. Accounting conclusions may change, but the evidence and reasoning that produced them must remain auditable.**

The registry is the project's institutional memory and completeness control—not merely a reporting convenience.