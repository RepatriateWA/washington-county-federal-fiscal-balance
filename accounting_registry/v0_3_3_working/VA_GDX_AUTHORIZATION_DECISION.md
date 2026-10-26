# ETL-230E - VA GDX Authorization Decision

## Decision

QUALIFIED_PROVISIONAL_INFLOW

## Scope

Washington Department of Veterans Affairs Geographic Distribution
of Expenditures (GDX), federal fiscal years 2018-2024.

## Seven-year total

$39,565,398,612.58

## Accounting source

va.v_washington_county_gdx_control_total

FY2018-2023: legacy Total Expenditure controls.
FY2024: Total Direct Expenditure plus Total Indirect Expenditure.

The source contains all 39 Washington counties per fiscal year.
The FY2024 component-level NULL observations are preserved.

## Certification evidence

- EP-VA-001 source methodology and evidence package.
- ETL-219B5 / ETL-230B3: 273 county-year controls,
  seven annual controls, zero financial exceptions.
- ETL-220D / ETL-230B3: source-policy structural PASS;
  earlier final additive authorization expressly withheld.
- ETL-219C6 / ETL-230C: VA assistance disposition review.
- ANALYSIS-213-v1: historical VA procurement source selection.
- ETL-230D2 and ETL-230D3: accounting-boundary review.

## Nonduplication policy

VA GDX is the preferred statewide VA expenditure control.

USAspending VA procurement obligations are not separately additive.
Duplicate-classified VA assistance obligations are not additive.
Unresolved VA assistance obligations remain withheld.

No unresolved USAspending obligation is subtracted from GDX.
Obligations and expenditures are not dollar-for-dollar equivalents.

## Cross-family qualifications

CMS Medicaid and CHIP remain separate qualified expenditure
controls, with independently documented source definitions.
Universal interagency or cross-source nonduplication has not
been certified.

Federal civilian wages, military wages, Medicare, SSA, and other
future expenditure families require their own accounting-boundary
review before additive authorization alongside VA GDX.

## Geographic and reporting limitations

This decision authorizes a qualified provisional statewide
expenditure control, not county economic-incidence attribution.

It does not authorize modification of the existing PostgreSQL
partial-balance reporting views.

It does not certify a complete statewide federal fiscal balance,
universal cross-source overlap resolution, or full EPS-001
evidence-package compliance.

## Disposition

Seven VA GDX annual entries are qualified provisional inflows.
Final statewide balance publication remains subject to broader
coverage, timing, and cross-source reconciliation.
