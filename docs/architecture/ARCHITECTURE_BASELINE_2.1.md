# ARCHITECTURE BASELINE 2.1
## Washington County Federal Fiscal Balance Project

Version: 2.1
Status: Baseline
Date: 2026-08-06

---

# Purpose

Architecture Baseline 2.1 documents the first complete normalization architecture for the Washington County Federal Fiscal Balance Project.

This baseline establishes the long-term design principles governing all future ETL development, data normalization, evidence generation, and analytical products.

The project is designed around one overriding objective:

> Every analytical conclusion must be reproducible from immutable source data using deterministic ETL processes.

This baseline therefore emphasizes:

- reproducibility
- transparency
- evidence preservation
- deterministic processing
- idempotent ETL
- shared normalization components
- complete auditability

---

# Guiding Principles

## 1. Immutable Raw Data

Raw federal source files are never modified.

Every source file is preserved exactly as published.

Normalization occurs only within warehouse tables.

---

## 2. Evidence First

Every transformation must produce evidence.

Evidence is considered a first-class deliverable.

Every ETL stage should be capable of producing an evidence package documenting:

- observations
- conflicts
- unmatched records
- normalization decisions
- validation results

No information is discarded merely because it cannot yet be classified.

---

## 3. Deterministic Processing

Repeated execution of the same ETL process against identical source data shall always produce identical warehouse contents.

A successful rerun should report:

Inserted ............ 0

Updated ............. 0

Unchanged ........... all

Validation .......... PASS

---

## 4. Shared Components

Business rules are implemented once.

Normalization logic belongs inside reusable shared modules whenever possible.

Examples include:

- identity generation
- relationship helpers
- geographic normalization
- extraordinary funding parsing
- evidence generation
- validation

Dataset-specific loaders should primarily orchestrate shared components.

---

## 5. Separation of Responsibilities

The architecture separates:

Raw ingestion

↓

Normalization

↓

Relationship construction

↓

Evidence generation

↓

Analytical reporting

Each layer has a single responsibility.

---

# Current Warehouse Domains

Current normalized domains include:

## Reference

- states
- counties
- agencies
- assistance listings
- assistance types
- funding opportunities
- extraordinary funding codes

---

## Assistance

Normalized assistance warehouse includes:

### Awards

Canonical award identity

### Transactions

Individual award transactions

### Recipients

Shared recipient identities

Recipient history

Parent recipient history

### Agencies

Shared agency hierarchy

Awarding agencies

Funding agencies

Subagencies

### Geography

Shared place-of-performance identities

Canonical place relationships

### Extraordinary Funding

Authoritative DEFC classifications

Transaction-to-DEFC relationships

COVID flags

IIJA flags

Funding family classifications

---

# Shared Infrastructure

The following shared libraries have been implemented.

## Identity Engine

Responsibilities:

- deterministic identities
- canonical identity keys
- conflict detection
- identity reconciliation

Shared by:

- recipients
- agencies
- places

---

## Relationship Helpers

Responsibilities:

- deterministic grouping
- canonical selection
- tie-breaking
- reconciliation
- validation

---

## Geographic Normalization

Responsibilities:

- canonical Washington county identities
- geographic fingerprints
- stable place identities
- warehouse-wide place reuse

---

## Extraordinary Funding

Shared components include:

Parser

Validation

Evidence generation

Reference classification

Relationship linkage

This architecture permits future datasets (including Procurement) to reuse identical DEFC logic.

---

# Evidence Architecture

Every normalization stage generates evidence.

Evidence packages preserve:

known relationships

unknown observations

unparsed values

validation summaries

reconciliation counts

No unresolved observations are discarded.

Unknown classifications remain available for future refinement.

---

# Validation Philosophy

Validation occurs continuously.

Typical validation includes:

duplicate identities

orphan relationships

referential integrity

count reconciliation

conflict detection

identity consistency

A successful ETL stage concludes only after all validation passes.

---

# Idempotent ETL

Every loader is expected to satisfy:

First execution

insert new records

Second execution

no inserts

no updates

all records unchanged

This behavior is considered a contract.

---

# Extraordinary Funding Baseline

Current implementation includes:

59,514 transactions containing DEFC values

70,071 parsed DEFC observations

63,008 authoritative transaction classifications

7,063 preserved unknown observations

27 distinct unclassified DEFC codes

2,944 multi-code transactions

No duplicate relationships

No orphan relationships

Zero unparsed source segments

All unknown codes remain preserved for future authoritative classification.

---

# Design Philosophy

The warehouse favors normalization over convenience.

The warehouse favors evidence over assumptions.

The warehouse favors deterministic processing over implicit behavior.

Whenever ambiguity exists, the system preserves evidence rather than guessing.

---

# Future Direction

Future development will extend the shared architecture to additional domains, including:

Procurement

Revenue

Treasury

IRS

Social Security

County allocation models

Federal balance calculations

Visualization products

Public analytical datasets

All future domains should reuse existing shared infrastructure whenever practical.

---

# Project Objective

The ultimate objective remains unchanged:

To construct a transparent, reproducible, county-level accounting of federal revenues collected from Washington State and federal expenditures returned to Washington State.

Every published statistic should be traceable through normalized warehouse tables to immutable federal source documents.

Measure first.

Explain later.
