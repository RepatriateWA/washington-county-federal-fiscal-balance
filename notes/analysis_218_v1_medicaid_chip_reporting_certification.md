# ANALYSIS-218-v1
## Washington Medicaid/CHIP Source, Overlap, and Reporting-Pathway Certification Record

**Project:** Washington County Federal Fiscal Balance Project (WCFFBP)
**Fiscal years:** Federal FY2018–FY2024
**Status:** Qualified PASS — source controls, identified USAspending overlap dispositions, reporting lineage, and methodology correction; **not** final statewide fiscal-balance certification
**Evidence:** ETL-218D, ETL-218E, ETL-218F, ETL-218G, ETL-218H1, ETL-218H2, ETL-218H3
**Repository checkpoint:** `3b9deb3` (`main`, pushed to `origin/main`)
**Record version:** 1.0; 2026-10-20

### 1. Purpose and scope

Document what the FY2018–FY2024 Medicaid and Children's Health Insurance Program (CHIP) evidence establishes, which duplicate-expenditure risks have been tested, and what remains uncertified. The objective is a traceable, nonduplicative accounting pathway, not a claim that all federal expenditures or the final Washington fiscal balance are complete.

This record summarizes executed audit outputs. It does not modify any source data, accounting policy, database view, or ledger entry. The independently executable SQL is the controlling verification artifact.

### 2. Preferred accounting sources and annual federal expenditure controls

Medicaid is sourced from CMS MBES Washington **Total Net Expenditures** federal-share controls on a federal-fiscal-year basis. CHIP is sourced from CMS-21 Washington **CHIP** and **MCHIP** additive federal-share controls; **MCHIP 20%** financing-adjustment rows are excluded from the additive expenditure measure. These are expenditure controls, not USAspending obligation totals.

| FFY | Medicaid federal expenditures ($) | CHIP additive federal expenditures ($) | Combined ($) |
|---:|---:|---:|---:|
| 2018 | 7,542,439,851 | 153,667,008 | 7,696,106,859 |
| 2019 | 8,258,800,793 | 192,747,238 | 8,451,548,031 |
| 2020 | 8,834,856,423 | 162,259,293 | 8,997,115,716 |
| 2021 | 11,442,944,427 | 183,473,223 | 11,626,417,650 |
| 2022 | 12,133,362,252 | 163,783,821 | 12,297,146,073 |
| 2023 | 12,219,087,130 | 150,504,673 | 12,369,591,803 |
| 2024 | 12,584,822,794 | 131,114,773 | 12,715,937,567 |

**ETL-218D:** Fourteen source-to-reporting controls reconciled (one Medicaid and one CHIP total per year), with zero dollar and provenance exceptions in the tested controls. CHIP additive worksheets were separately distinguished from excluded financing adjustments.

### 3. USAspending overlap and accounting dispositions

**ETL-218E:** Inspected effective Medicaid/CHIP source policies, program mappings, award classifications, and canonical USAspending assistance transactions. Medicaid Assistance Listing **93.778** was classified as `EXCLUDE_DUPLICATE` in the tested fiscal-year scope; CHIP Assistance Listing **93.767** used award-level classification rather than a blanket program mapping. The inspected core-program mappings did not authorize `INCLUDE_ADDITIVE`.

**ETL-218F:** The transaction-level effective-disposition audit passed its fail-closed gate: no tested Medicaid or CHIP transactions had an ambiguous, unmapped, conflicting, or additive disposition. Medicaid 93.778 observations resolved to duplicate exclusion. CHIP 93.767 observations resolved to either `EXCLUDE_DUPLICATE` or `WITHHOLD_UNRESOLVED`. The latter are **not** evidence of additional additive expenditure; they remain withheld pending affirmative reconciliation.

The identified historical CHIP award classifications include performance-bonus adjustments, Healthy Kids Together, and outreach/enrollment corrections requiring withholding, alongside core Title XXI financing classified as duplicate exclusion. Award classifications and transaction obligations must not be conflated with CMS federal-fiscal-year expenditure controls.

**Limitation:** These checks establish safety for the tested program/award transaction population and reporting path. They do not prove that every possible cross-source overlap across the entire federal expenditure universe has been resolved.

### 4. Reporting lineage and nonduplication

**ETL-218G:** The reporting dependencies and underlying view definitions showed the following path:

- `cms.medicaid_state_control_total` → `reporting.v_washington_medicaid_expenditures` → `reporting.v_washington_tracked_expenditures`.
- `chip.v_cms21_control_totals` → `reporting.v_washington_chip_expenditures` → `reporting.v_washington_tracked_expenditures`.
- `reporting.v_washington_revenue_summary` and `reporting.v_washington_tracked_expenditures` → `reporting.v_washington_partial_fiscal_balance`.

For each of seven years, the tracked-expenditure view contained **one Medicaid component and one CHIP component**, along with Original Medicare and three SSA OASDI components: **six rows per year, 42 rows total**. There were zero duplicate `(report_year, agency_code, program_code)` component keys. The independently reproduced partial balances differed from the view by **$0** in every tested year.

The verified direct dependencies of the partial-balance view are only `reporting.v_washington_revenue_summary` and `reporting.v_washington_tracked_expenditures`; the inspected pathway does not add USAspending assistance obligations as a second expenditure stream.

### 5. Methodology correction and independent verification

**ETL-218H1** established the pre-migration view definition, seven-year accounting baseline, and numerical fingerprint. **ETL-218H2** changed only the view's outdated methodology text, which had incorrectly said CHIP was excluded. The migration used exact-fragment and pre-migration fingerprint gates and committed successfully. **ETL-218H3** independently verified the committed state in a new read-only transaction.

The corrected note is:

> Partial balance: IRS gross collections minus annualized SSA OASDI benefits, Original Medicare actual payments, CMS Medicaid federal Total Net Expenditures, and CMS CHIP expenditures. VA, USAspending, Medicare Advantage, and other federal expenditures are not yet included.

Independent post-migration controls:

| Test | Verified result |
|---|---|
| Years | 7 (FY2018–FY2024) |
| Total gross collections | $877,156,759,000 |
| Total tracked expenditures | $323,024,861,111 |
| Total partial balances | $554,131,897,889 |
| Annual arithmetic differences | $0 in all 7 years |
| Medicaid/CHIP source-to-tracked differences | $0 in all 14 comparisons |
| Duplicate tracked-component keys | 0 in ETL-218G |
| Partial-view direct dependencies | 2 expected reporting views |
| Numerical MD5 fingerprint | `25a17fdc06e68f50d7c319dc8248f26f` |

The fingerprint was identical before and after the correction. No numerical accounting measure was changed by ETL-218H2.

### 6. Certification boundaries and unresolved work

**Verified within scope:** CMS annual Medicaid/CHIP expenditure controls; CHIP financing-adjustment exclusion; tested USAspending 93.778/93.767 overlap dispositions; unique Medicaid/CHIP representation in the tracked reporting view; partial-balance arithmetic; and faithful methodology wording.

**Not certified:**

1. A complete federal expenditure ledger or final Washington federal fiscal balance.
2. A uniform annual accounting basis for every included reporting component. SSA OASDI is a **December annualized benefit measure**, not demonstrated annual cash expenditures; the reported Original Medicare measure is **calendar-year** based rather than a fully reconciled federal-fiscal-year amount.
3. Full Medicare Advantage/Part C and Part D coverage; VA and other federal expenditure streams; or general USAspending additive inclusion.
4. Complete resolution of withheld CHIP awards or of all possible cross-source overlaps.
5. County-level allocation of these state CMS control totals or a certified 39-county balance.
6. Full **EPS-001 Evidence Package Standard** compliance. That standard's proposed structure requires additional immutable manifest, machine-readable certification, reconciliation, exception, log, and metadata artifacts. This methodology note is **not** a substitute for such a package.

A transaction classification of `EXCLUDE_DUPLICATE` or `WITHHOLD_UNRESOLVED` must not be interpreted as an assertion of dollar-for-dollar equivalence between USAspending **obligations** and CMS **expenditures**.

### 7. Reproduction and source-control references

The verified methodology-correction sequence is preserved in:

- `etl/sql/218h1_preflight_reporting_methodology.sql`
- `etl/sql/218h2_correct_partial_balance_methodology.sql`
- `etl/sql/218h3_verify_partial_balance_methodology.sql`

All three were committed and pushed in Git commit **`3b9deb3`**. ETL-218D–218G execution results and associated policy evidence were reviewed during this certification sequence; their underlying scripts and runtime outputs remain separate evidence inputs and must be retained or packaged before any EPS-001 compliance claim.

**Disposition:** **Qualified PASS — Medicaid/CHIP source, overlap-classification, reporting-lineage, and methodology-correction controls for FY2018–FY2024.** Final statewide fiscal-balance publication remains blocked pending comprehensive expenditure coverage, timing-basis reconciliation, cross-source nonduplication, and reproducible evidence packaging.

---

**WCFFBP principle:** Measure first. Explain later. Certify first. Publish second.
