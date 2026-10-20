
# ANALYSIS-213-v1
## Historical VA GDX / USAspending Procurement Source-Treatment Policy

**Project:** Washington County Federal Fiscal Balance Project (WCFFBP)

**Fiscal years:** 2018–2019

**Evidence:** ETL-213J through ETL-213X

**Status:** Methodological source-selection decision; database implementation pending validation.

### 1. Purpose

Establish a defensible accounting-source policy for historical Department of Veterans Affairs expenditures and potentially overlapping USAspending procurement obligations in Washington State.

This policy is limited to FY2018 and FY2019.

### 2. Verified accounting controls

| Fiscal year | VA GDX expenditures | VA-funded procurement net obligations |
|---|---:|---:|
| 2018 | $4,377,268,316.65 | $457,642,893.26 |
| 2019 | $4,896,346,222.98 | $412,209,832.19 |
| Total | $9,273,614,539.63 | $869,852,725.45 |

VA GDX source workbooks were loaded successfully for all 39 Washington counties in both years, with no rejected rows.

The six GDX expenditure components reconcile exactly to their annual control totals, with zero difference in both years.

The GDX data use the legacy pre-FY2024 methodology.

### 3. Procurement evidence

The historical VA-funded procurement population contains:

- FY2018: 3,892 transactions, 3,132 awards.
- FY2019: 2,530 transactions, 2,041 awards.
- Combined net federal obligations: $869,852,725.45.

Procurement functional screening identified substantial medical care, construction/facilities, and IT/telecommunications activity.

The screening is not a certified allocation of obligations into GDX expenditure categories.

Procurement obligations and GDX expenditures differ in accounting measure, timing, functional aggregation, and geographic attribution.

### 4. Source-selection decision

For FY2018–FY2019:

- Accounting measure: ANNUAL_EXPENDITURES
- Inflow family: VETERANS_AFFAIRS
- Inflow subfamily: TOTAL_VA_EXPENDITURES
- Preferred source: VA_GDX
- County allocation source: VA_GDX
- Overlapping source: USASPENDING_PROCUREMENT
- Ledger treatment: INCLUDE_AFTER_RECONCILIATION

VA GDX is selected as the preferred accounting and county-allocation source for annual VA expenditures.

USAspending procurement observations are preserved for transaction-level provenance, functional and geographic analysis, and reconciliation.

USAspending VA procurement obligations are not authorized as a second additive expenditure stream.

### 5. Interpretation of overlap

The evidence establishes material functional overlap risk between procurement activity and the expenditure universe reported in VA GDX.

It does not establish:

- Dollar-for-dollar equivalence between procurement obligations and GDX expenditures.
- Same-fiscal-year recognition of corresponding expenditures.
- Complete containment of every procurement transaction within GDX.
- Washington beneficiary incidence solely from procurement place-of-performance geography.
- That every GDX expenditure is attributable to a procurement transaction.

No percentage from the PSC screening shall be represented as a certified overlap percentage.

### 6. Geographic-incidence safeguards

The separate Historical VA Procurement Geographic-Incidence Policy v0.1 remains applicable.

Recipient geography, primary place of performance, and destination or beneficiary geography must be preserved as distinct concepts.

Where procurement beneficiary incidence is unresolved, county allocation must not be inferred from place of performance alone.

The existence of an out-of-state beneficiary does not prove that no Washington supplier-side economic activity occurred.

### 7. Exception policy

Separate additive treatment of a procurement-related expenditure requires affirmative evidence that:

1. The corresponding activity lies outside the VA GDX expenditure universe.
2. An actual expenditure measure is available and distinguishable from the procurement obligation.
3. Its fiscal-year attribution is defensible.
4. Its Washington and county geographic incidence is supported.
5. The expenditure is not duplicated by another accounting source.

An unresolved possible exception remains excluded from additive accounting pending reconciliation; the source transaction remains preserved.

### 8. Relationship to existing policies

ANALYSIS-149-v1 applies to FY2024 and is not modified.

Existing FY2018–FY2019 VA assistance overlap policies, including ANALYSIS-209U-v1, ANALYSIS-211L-v1, ANALYSIS-211M-v1, and ANALYSIS-211N-v1, remain unchanged.

ANALYSIS-213-v1 concerns USAspending procurement, not USAspending assistance.

### 9. Implementation controls

A database policy migration may be performed only after:

- Confirming that no conflicting FY2018–FY2019 procurement source policy already exists.
- Validating the existing source-policy schema and constraints.
- Confirming that the migration does not change the FY2024 policy.
- Ensuring that the migration is repeatable and does not duplicate existing policy rows.
- Establishing post-migration checks of policy scope and source selection.

No procurement transaction records, GDX expenditure records, county allocations, or existing assistance policies are to be modified by this policy migration.

### 10. Outstanding accounting work

The selected source policy does not, by itself, authorize final ledger publication.

Remaining work includes validation of the final VA GDX ledger integration, interaction with other federal expenditure sources, documented exception treatment, and final accounting reconciliation.

---

**WCFFBP principle:** Measure first. Explain later.
