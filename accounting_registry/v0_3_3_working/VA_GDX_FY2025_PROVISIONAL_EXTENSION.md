# ETL-249D6 ? FY2025 VA GDX Provisional Extension

## Decision

QUALIFIED_PROVISIONAL_INFLOW_FY2025

This decision extends the historical VA GDX qualified provisional
statewide accounting treatment to federal fiscal year 2025 only.

It does not authorize canonical ledger inclusion, modify PostgreSQL
reporting views, or certify a complete statewide federal fiscal balance.

## Historical authority

- `VA_GDX_AUTHORIZATION_DECISION.md`
- Historical scope: FY2018?FY2024.
- Historical decision: `QUALIFIED_PROVISIONAL_INFLOW`.
- Historical certification: ETL-219B5 / ETL-230B3.
- FY2024 method: Total Direct Expenditure plus Total Indirect Expenditure.

The historical decision remains unchanged.

## FY2025 source and provenance

- Source: `data/raw/va/gdx/FY2025/GDX_FY25.xlsx`
- SHA256: `1cf95d35c842b0064eacb3055db4441a775163919a3e90d21d30d4966aefaf25`
- Reporting basis: federal fiscal year 2025.
- Geographic scope: Washington State, including all 39 counties.
- Source units: dollars.
- Statewide control: Direct plus Indirect Expenditure.

## FY2025 Washington expenditure control

| Measure | Dollars |
|---|---:|
| Direct expenditures | $4,659,297,977.48 |
| Indirect expenditures | $3,368,213,803.36 |
| **Total VA GDX expenditures** | **$8,027,511,780.84** |

## Historical comparison

- FY2024 source: `data/raw/va/gdx/FY2024/GDX_FY24.xlsx`
- FY2024 SHA256: `f55b40aa9ff4e5b99c22c0a51ab8ac3bc91c1b6801b67ea549aa5b54b5162035`
- FY2024 source units: thousands of dollars.
- FY2024 reconstructed control: $6,926,923,691.03.
- FY2024 published dashboard control: $6,926,923,691.03.
- FY2024 published-control difference: $0.00.
- FY2025 change: +$1,100,588,089.81.
- FY2025 percentage change: +15.8886%.

Both years use the combined direct-plus-indirect expenditure
measure. Subcategory definitions and presentation differ by year.

## Reconciliation evidence

- ETL-249D1: FY2025 source workbook inspection.
- ETL-249D2: FY2025 statewide and 39-county reconciliation.
- ETL-249D3: historical source and policy inventory.
- ETL-249D4: FY2024/FY2025 accounting-boundary comparison.
- ETL-249D5: qualification preflight.
- ETL-249D6: independent source-control validation.

ETL-249D2 reported zero state-to-county differences,
zero category discrepancies, and zero missing values.

Fourteen negative FY2025 county-level Loan Guaranty entries
are retained as signed source observations. Their underlying
adjustment semantics have not been independently established.

## Category-definition qualifications

FY2024 reports Medical Care as one category.

FY2025 separately reports Medical Community Care and
Medical VA Care.

FY2025 also separates several expenditure categories
previously grouped together, including education and
vocational rehabilitation, and adapted housing/equipment.

Accordingly, the combined annual controls are comparable
at the broad accounting-boundary level. Individual categories
require an explicit crosswalk before year-over-year comparison.

## Nonduplication policy

The historical VA GDX nonduplication restrictions continue
to govern provisional treatment:

1. VA GDX is the preferred statewide VA expenditure control.
2. USAspending VA procurement obligations are not separately additive.
3. Duplicate-classified VA assistance obligations are not additive.
4. Unresolved VA assistance obligations remain withheld.
5. Obligations are not treated as dollar-for-dollar equivalents
   of expenditures.
6. Universal cross-family nonduplication remains uncertified.

These restrictions are inherited from the historical
authorization decision and are not relaxed for FY2025.

## Authorization boundaries

Authorized by this provisional extension:

- Recognition of $8,027,511,780.84 as the FY2025 Washington
  VA GDX qualified provisional expenditure candidate.
- Use in subsequent provisional statewide presentation
  development, subject to the existing overlap restrictions
  and transparent disclosure of accounting limitations.

Not authorized:

- Canonical annual ledger certification or posting.
- Changes to PostgreSQL reporting views.
- Separate additive treatment of VA procurement obligations.
- Separate additive treatment of duplicate or unresolved
  VA assistance obligations.
- Certification of universal cross-family nonduplication.
- Automatic dashboard publication or modification.
- County economic-incidence attribution.

## Disposition

FY2025 VA GDX: QUALIFIED_PROVISIONAL_INFLOW_FY2025.

Historical FY2018?FY2024 VA GDX authorization is preserved.

The complete FY2025 statewide fiscal balance remains provisional
and subject to coverage, timing, overlap, and source-family
reconciliation.
