# EP-VA-001 — Washington County VA GDX Evidence Package

**Dataset:** VA Geographic Distribution of Expenditures — Washington County Series  
**Coverage:** FY2015–FY2024  
**Geography:** All 39 Washington counties  
**Generated:** 2026-08-13T04:31:17.956601+00:00

## Certified Scope

This package certifies official-source workbook provenance and SHA-256 identity,
complete FY2015–FY2024 and 39-county coverage, source-unit preservation,
legacy `$000s` normalization to dollars, the FY2024 Direct/Indirect
methodology break, financial reconciliation, and annual Washington GDX
county-control totals.

## Critical Limitation

**VA GDX is not yet certified as additive to the final federal
fiscal-balance ledger.**

Some GDX categories may overlap USAspending-derived federal spending. A
separate overlap/deduplication reconciliation must determine the controlling
source for each expenditure domain before the totals are combined.

## Reproduction

```powershell
python -m scripts.validate_va_gdx
python -m scripts.build_va_gdx_evidence_package
```
