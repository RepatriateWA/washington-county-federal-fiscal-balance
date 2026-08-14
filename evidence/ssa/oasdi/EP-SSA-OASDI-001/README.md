# EP-SSA-OASDI-001 — Washington County SSA OASDI Evidence Package

**Dataset:** SSA OASDI Beneficiaries and Benefit Amounts — Washington County Series  
**Coverage:** Report years 2015-2024  
**Geography:** All 39 Washington counties  
**Generated:** 2026-08-14T00:52:19.766826+00:00

## Certification Scope
This package certifies 2015-2024 coverage, 3,510 normalized observations, 39 counties per year, 9 benefit types per year, 390 published county/year TOTAL controls, reference/program mapping integrity, December x 12 annualization integrity, documented SSA source-rounding treatment, annual Washington control totals, and SHA-256 identity of the ten local raw workbooks.

## Important Accounting Limitation
The annualized amount is the published December monthly benefit amount multiplied by 12. It is an annualized run-rate, not observed federal-fiscal-year cash outlay.

## Reproduction
```powershell
python -m scripts.validate_ssa_oasdi
python -m scripts.build_ssa_oasdi_evidence_package
```
