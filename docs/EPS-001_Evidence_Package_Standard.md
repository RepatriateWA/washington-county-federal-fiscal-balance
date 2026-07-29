# EPS-001
# Evidence Package Standard

**Version:** 1.0.0 (Draft)
**Status:** Proposed
**Effective:** TBD
**Applies To:** All certified ETL pipelines

Normative Statement: This document is normative. In the event of a conflict between this specification and an implementation, the specification governs.

---

# 1. Purpose

This standard defines the required structure, contents, behavior, and lifecycle of an Evidence Package produced by the Washington County Federal Fiscal Balance Project.

An Evidence Package is the authoritative deliverable produced by a certified ETL pipeline.

Its purpose is to provide a complete, reproducible, machine-readable, and human-readable record demonstrating how a certified dataset was produced.

---

# 2. Scope

This standard applies to every dataset processed by the project, including but not limited to:

- Procurement
- IRS Statistics of Income
- Treasury
- Census
- Federal Assistance
- Fiscal Balance Calculations
- Future datasets

---

# 3. Design Principles

The project is governed by the following principles.

### Principle 1

Measure First. Explain Later.

### Principle 2

Certify First. Publish Second.

### Principle 3

Evidence Over Assertion.

### Principle 4

Every Published Number Shall Be Traceable.

### Principle 5

Evidence Packages Are Immutable.

### Principle 6

Certification Must Be Reproducible.

### Principle 7

The Evidence Package Is the Authoritative Deliverable.

---

# 4. Requirements Language

The key words

MUST

MUST NOT

SHOULD

SHOULD NOT

MAY

are interpreted as described in RFC 2119.

---

# 5. Lifecycle

Every ETL pipeline SHALL execute the following stages.

Acquire

↓

Normalize

↓

Validate

↓

Certify

↓

Generate Evidence Package

↓

Publish Certified Dataset

Publication SHALL NOT occur prior to successful certification.

---

# 6. Directory Structure

Every Evidence Package SHALL conform to the following structure.

evidence/

    <dataset>/

        batch_<id>/

            EPS-<version>/

                manifest.json

                certification.json

                certification_report.txt

                metadata/

                    batch_metadata.json

                    certification_version.json

                reconciliation/

                exceptions/

                logs/

---

# 7. Required Artifacts

Every package MUST contain

• manifest.json

• certification.json

• certification_report.txt

• batch_metadata.json

• certification_version.json

• reconciliation directory

• exceptions directory

• logs directory

---

# 8. Manifest

The manifest SHALL identify

- package version

- dataset

- batch

- status

- artifact inventory

- creation timestamp

The manifest SHALL be considered the entry point to the package.

---

# 9. Certification Report

The report SHALL be human-readable.

It SHALL summarize

- certification status

- passed checks

- failed checks

- warnings

- execution summary

---

# 10. Certification JSON

The JSON report SHALL contain

summary

checks

evidence

statistics

versions

metadata

Each certification check SHALL preserve its structured evidence.

---

# 11. Reconciliation Files

Reconciliation CSVs SHALL document numerical agreement between

raw data

normalized data

certified data

Each reconciliation SHALL be independently reproducible.

---

# 12. Exception Files

Exception files SHALL exist even when no exceptions occur.

Header-only CSV files SHALL indicate that the corresponding validation completed successfully with zero exceptions.

Missing exception files SHALL be considered non-compliant.

---

# 13. Metadata

Metadata SHALL include

dataset

batch identifier

UTC creation timestamp

ETL version

certification version

Evidence Package version

Git commit identifier (when available)

---

# 14. Immutability

Evidence Packages SHALL NOT be modified after creation.

Corrections SHALL produce a new package version.

Previously generated packages SHALL remain available for audit purposes.

---

# 15. Traceability

Every published dataset SHALL identify the Evidence Packages from which it was derived.

Every published number SHALL be traceable to one or more certified Evidence Packages.

---

# 16. Compliance

An ETL pipeline SHALL be considered EPS-001 compliant only if

• certification succeeds

• required artifacts are present

• directory structure conforms

• metadata is complete

• reconciliation artifacts are present

• exception artifacts are present

• package passes schema validation

---

# 17. Future Compatibility

Future versions of this standard SHALL remain backward compatible whenever practical.

Breaking changes SHALL require a new Evidence Package version identifier.

---

# Appendix A

Example directory layout

...

# Appendix B

Example certification.json

...

# Appendix C

Example manifest.json

...