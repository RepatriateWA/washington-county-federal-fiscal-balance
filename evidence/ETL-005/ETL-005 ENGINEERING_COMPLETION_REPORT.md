# ETL-005 Completion Report
## USAspending Assistance Canonical Warehouse Construction

**Project:** Washington County Federal Fiscal Balance Project

**Work Package:** ETL-005

**Prepared:** August 2026

**Status:** COMPLETED

---

# Executive Summary

ETL-005 established the production-quality canonical warehouse for
USAspending Assistance award data.

The work package successfully demonstrated the complete end-to-end
Extract–Transform–Load (ETL) process for multiple fiscal years using an
immutable raw data warehouse, shared dimensional architecture,
canonical awards, canonical transactions, deterministic entity
resolution, and fully classified extraordinary funding relationships.

Every major transformation stage includes reproducible validation and
evidence artifacts.

---

# Objectives

ETL-005 was undertaken to accomplish the following objectives:

1. Preserve USAspending Assistance source files without modification.

2. Build an immutable raw warehouse.

3. Normalize shared reference dimensions.

4. Construct canonical award identities.

5. Construct immutable transaction identities.

6. Resolve recipients, agencies, and places through deterministic
   identity resolution.

7. Classify Disaster Emergency Fund Codes (DEFC).

8. Produce complete evidence packages supporting reproducibility.

---

# Source Data

## USAspending Assistance Archives

Fiscal Years Processed

| Fiscal Year | Status |
|-------------|--------|
| 2020 | Complete |
| 2021 | Complete |
| 2022 | Pending |
| 2023 | Pending |
| 2025 | Pending |

---

# Architecture

ETL-005 implemented the following warehouse architecture.

```
ZIP Archives
        │
        ▼
Archive Inventory
        │
        ▼
Immutable Raw Warehouse
        │
        ▼
Reference Dimensions
        │
        ▼
Canonical Awards
        │
        ▼
Canonical Transactions
        │
        ▼
Relationship Enrichment
        │
        ▼
Extraordinary Funding Classification
        │
        ▼
Evidence Packages
```

---

# FY2020 Results

## Raw Source

Rows Loaded

391,015

Canonical Awards

358,684

Canonical Transactions

391,015

Validation

PASS

---

## Shared Dimensions

### Assistance Listings

Distinct Listings

984

Inserted

169

Updated

68

Validation

PASS

---

### Assistance Types

Distinct Types

10

Validation

PASS

---

### Agencies

Distinct Agency Codes

144

New Subagencies

4

Validation

PASS

---

### Recipients

Canonical Identities

253,692

Identity Conflicts

0

Duplicate Keys

0

Validation

PASS

---

### Places

Canonical Places

2,708

Identity Conflicts

0

Unresolved Counties

0

Validation

PASS

---

# Relationship Enrichment

Recipient Relationships

391,015

Agency Relationships

391,015

Place Relationships

391,015

Validation

PASS

---

# Extraordinary Funding

Initial Validation

Known DEFC Relationships

320,202

Unknown DEFC Observations

1,341

Distinct Unknown Codes

19

---

## Reference Improvement

Rather than suppress unknown DEFC values, ETL-005 isolated every
previously unknown code.

Reference Package RP-001 expanded the reference dimension to include all
nineteen missing DEFC codes.

Following reference expansion:

Known Relationships

321,543

Unknown Observations

0

Unknown Codes

0

Validation

PASS

---

# FY2021 Results

Rows Loaded

261,008

Canonical Awards

228,110

Canonical Transactions

261,008

Validation

PASS

---

# Cross-Year Validation

The warehouse successfully demonstrated cross-year canonical identity
resolution.

Observed Results

✓ Shared recipient reuse

✓ Shared agency reuse

✓ Shared place reuse

✓ Canonical award continuity

✓ Immutable transaction identities

✓ Zero duplicate transaction keys

✓ Zero orphan award references

✓ Zero cross-batch identity conflicts

---

# Duplicate Archive Investigation

Two FY2020 USAspending archives were independently downloaded.

Batch 7

391,015 transactions

Batch 8

391,015 transactions

Validation demonstrated:

391,015 shared transaction keys

391,015 identical raw records

0 differing records

Batch 8 was designated the canonical FY2020 source.

Batch 7 remains preserved in the immutable raw warehouse for complete
provenance.

---

# Methodology

The project follows several governing principles.

• Preserve all original source data.

• Never overwrite raw observations.

• Normalize deterministic dimensions.

• Produce immutable transaction identities.

• Detect uncertainty rather than hiding it.

• Expand reference data instead of hard-coding exceptions.

• Generate evidence for every transformation.

• Require validation before proceeding to the next ETL stage.

---

# Evidence Produced

Each ETL stage produces evidence supporting independent verification.

Evidence includes:

• normalization summaries

• relationship summaries

• reconciliation reports

• validation reports

• unknown-code reports

• DEFC linkage reports

---

# Reproducibility

Every transformation performed during ETL-005 is deterministic.

Running the ETL against the same source archives will reproduce the same
canonical warehouse, evidence packages, and validation results.

---

# Limitations

ETL-005 currently covers USAspending Assistance data.

Future work includes:

• FY2022 processing

• FY2023 processing

• FY2025 processing

• Procurement ETL

• County allocation methodology

• COVID-only expenditure reporting

• Washington county fiscal balance reporting

---

# Conclusion

ETL-005 successfully established the production architecture for
USAspending Assistance within the Washington County Federal Fiscal
Balance Project.

The work package demonstrates:

• reproducible ETL,

• deterministic canonical identities,

• cross-year award continuity,

• immutable transaction history,

• complete extraordinary funding classification,

• evidence-driven validation, and

• transparent methodology suitable for independent audit.

ETL-005 is accepted as complete upon successful processing of the
remaining fiscal-year batches using the validated workflow established
during FY2020 and FY2021.