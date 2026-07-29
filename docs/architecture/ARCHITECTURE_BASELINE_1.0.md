# Washington County Federal Fiscal Balance Project
# Architecture Baseline 1.0

Version: 1.0
Status: Approved
Date: July 2026

The purpose of this architecture is not merely to compute results, but to establish justified confidence in those results through transparent, reproducible, evidence-based engineering.

---

# 1. Purpose

This document defines the baseline architecture of the Washington County Federal Fiscal Balance Project.

It establishes the major subsystems, architectural principles, component responsibilities, and data flow for the project.

Implementation details may evolve.

The architectural principles defined herein SHALL remain stable except through an approved Architecture Decision Record (ADR).

---

# 2. Project Mission

The mission of this project is to construct a transparent, reproducible, evidence-based public data platform capable of measuring the net flow of federal tax dollars into and out of Washington State and its counties.

The platform shall enable independent verification of every published number.

---

# 3. Guiding Principles

1. Measure First. Explain Later.

2. Certify First. Publish Second.

3. Evidence Over Assertion.

4. Every Published Number Shall Be Traceable.

5. Evidence Packages Are Immutable.

6. Certification Must Be Reproducible.

7. The Evidence Package Is the Authoritative Deliverable.

---

# 4. Architectural Overview

The project consists of three major layers.

    Acquisition

        ↓

    Certification

        ↓

    Analysis

Each layer has clearly defined responsibilities.

No layer may bypass another.

---

# 5. Layer One — Acquisition

Purpose

Acquire federal source data.

Responsibilities

• Download source datasets

• Preserve original files

• Normalize data

• Populate PostgreSQL

Inputs

IRS

USAspending

Treasury

Census

Reference datasets

Outputs

Normalized database tables

The Acquisition Layer SHALL NOT produce published statistics.

---

# 6. Layer Two — Certification

Purpose

Demonstrate correctness.

Responsibilities

Validation

Relationship verification

Financial reconciliation

Schema validation

Evidence Package generation

Outputs

Certified datasets

Evidence Packages

Only certified datasets may be used for downstream analysis.

---

# 7. Layer Three — Analysis

Purpose

Generate public insight.

Responsibilities

Fiscal balance calculations

County comparisons

Time series

Maps

Reports

Public website

API

Analysis SHALL operate exclusively on certified datasets.

---

# 8. Major Components

Reference Data

IRS

Procurement

Treasury

Assistance

Certification Framework

Evidence Framework

Fiscal Balance Engine

Presentation Layer

---

# 9. Data Flow

Raw Federal Data

↓

Acquisition

↓

Normalization

↓

Validation

↓

Certification

↓

Evidence Package

↓

Certified Database

↓

Fiscal Balance Engine

↓

Public Reports

---

# 10. Evidence Architecture

Every certification SHALL generate an Evidence Package.

Evidence Packages are immutable.

Evidence Packages constitute the authoritative output of every ETL pipeline.

---

# 11. Certification Architecture

Certification consists of:

Structural checks

Relationship checks

Financial checks

Business rule checks

Compliance checks

Each check SHALL preserve machine-readable evidence.

---

# 12. Traceability

Every published metric SHALL be traceable to one or more Evidence Packages.

Every Evidence Package SHALL identify:

dataset

batch

versions

metadata

certification

supporting evidence

---

# 13. Standards

The architecture references the following project standards.

EPS-001

Evidence Package Standard

ETL-114

Certification Framework

Future standards SHALL extend, but not contradict, this baseline.

---

# 14. Architectural Decision Records

Major architectural changes SHALL be documented using ADRs.

Examples

ADR-0001

Evidence Packages Are the Primary Deliverable

ADR-0002

Evidence Packages Are Immutable

---

# 15. Future Expansion

The architecture is intentionally dataset-independent.

Future federal datasets SHALL integrate through the Acquisition and Certification layers before becoming available for analysis.

---

# Appendix A

Architecture Diagram

---

# Appendix B

Repository Layout

---

# Appendix C

Evidence Lifecycle

---

# Appendix D

Glossary




Diagram 1 – System Overview

                Raw Federal Data
                        │
                        ▼
               Acquisition Layer
                        │
                        ▼
              Certification Layer
                        │
                        ▼
               Evidence Packages
                        │
                        ▼
             Certified Data Warehouse
                        │
                        ▼
                 Analysis Layer
                        │
                        ▼
          Reports • Maps • API • Website



Diagram 2 – Evidence Pipeline

Download


    │
    ▼
Normalize
    │
    ▼
Validate
    │
    ▼
Certify
    │
    ▼
Generate Evidence Package
    │
    ▼
Publish Dataset     



Diagram 3 – Repository Organization

docs/
├── architecture/
├── standards/
├── adr/
└── developer/

etl/
├── loaders/
├── validation/
└── sql/

evidence/

data/


Diagram 4 – Component Relationships

                Acquisition
                     │
                     ▼
             Certification Engine
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
  Certified Dataset      Evidence Package
         │                       │
         └───────────┬───────────┘
                     ▼
             Fiscal Balance Engine
                     │
                     ▼
          Public Reports & Website