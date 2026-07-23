## Architecture Baseline v1.0
Date: 2026-07-21

### Accepted
- ADR-001: Immutable Observational Data
- ADR-002: Separation of Evidence and Interpretation
- ADR-003: Reproducible Derivations

### Established
- Procurement Architecture Baseline
- Engineering Standards
- Validation Standards
- Evidence Package Standards

### Repository Tag
architecture-baseline-v1.0

v0.5.0
-------
Added canonical procurement warehouse.

New:
- Agency Dimension
- Recipient Dimension
- NAICS Dimension
- PSC Dimension

Improved:
- ETL framework
- Migration system
- Validation

Fixed:
- Database connection helper
- Migration numbering
# Changelog

All notable changes to the Washington County Federal Fiscal Balance Project will be documented in this file.

The project follows an evidence-first, reproducible engineering approach. Changes recorded here summarize user-visible and repository-level improvements between milestones.

---

## [Unreleased]

### Added
- Project engineering log (`PROJECT_LOG.md`)
- Migration governance documentation
- Procurement subsystem architecture planning

---

## [v0.5.0] - In Progress

### Added
- Canonical Award dimension
- Canonical Award Transaction fact table
- Canonical Recipient dimension
- Canonical Agency dimension
- NAICS classification dimension
- PSC classification dimension

### Infrastructure
- Shared ETL utilities
- Batch processing framework
- Deterministic normalization pipeline
- Validation framework
- Idempotent ETL execution

### Database
- Procurement schema expansion
- Migration `110_create_procurement_agency.sql`
- Agency normalization loader

### Improved
- Append-only migration numbering
- Database connection helper imports
- ETL consistency across procurement loaders
- Referential integrity between procurement entities

### Verified
- Agency normalization validation
- Idempotent execution
- Repeatable migration execution
- Canonical agency identity resolution

### Planned
- Place of Performance dimension
- Office dimension
- Procurement star schema integration
- End-to-end procurement validation suite