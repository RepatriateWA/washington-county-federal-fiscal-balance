# ADR-006: CMS Expenditure Subsystem

**Status:** Accepted

**Date:** 2026-07-14

## Context

Version 0.8 established the first production-quality federal expenditure subsystem using Social Security Administration OASDI data.

The next major expenditure source is the Centers for Medicare & Medicaid Services (CMS).

CMS administers several large federal health programs, including:

- Medicare
- Medicaid
- Children’s Health Insurance Program (CHIP)

These programs differ materially in funding structure, geographic detail, reporting period, and source methodology.

A clear architectural decision is required before CMS data are loaded.

## Decision

The CMS subsystem will represent Medicare, Medicaid, and CHIP as separate federal programs.

Each program will preserve its source-specific methodology while mapping into the shared warehouse dimensions:

```text
reference.federal_agency
reference.federal_program
reference.state_registry
reference.county_registry
reference.calendar_year