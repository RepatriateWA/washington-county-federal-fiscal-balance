# WCFFBP Data Sources

The Washington County Federal Fiscal Balance Project (WCFFBP) uses federal administrative, statistical, budgetary, and program data to estimate the fiscal relationship between Washington State and the federal government and, ultimately, to allocate that relationship among Washington's 39 counties.

This document identifies the principal source families used or evaluated by WCFFBP and describes their analytical roles.

> **Presence in this registry does not imply inclusion in the federal fiscal-balance ledger.**

A source may be acquired and validated without being accepted as an accounting control. A source accepted for statewide accounting may not be suitable for county allocation. A source may also be retained solely for reconciliation, comparison, or methodological reference.

WCFFBP therefore distinguishes among:

1. source acquisition;
2. source measurement and validation;
3. source semantics and completeness;
4. reconciliation and overlap;
5. accounting policy;
6. ledger inclusion; and
7. geographic incidence or allocation.

These stages are intentionally separate.

## Source-Status Terminology

**Acquired** means that WCFFBP has obtained and preserved, or documented the reproducible acquisition of, the source material.

**Source validated** means that the project has evaluated relevant structural, semantic, geographic, temporal, or numerical characteristics of the source. Validation does not by itself authorize ledger inclusion.

**Accounting control** means that the source has been selected to control a particular federal receipt or expenditure component for the applicable analytical period.

**Allocation source** means that the source is used to distribute a separately established accounting control among states, counties, or other geographic units.

**Reconciliation source** means that the source is used to identify overlap, duplication, omissions, timing differences, or other relationships among data sources.

**Diagnostic or reference source** means that the source informs methodology, comparison, or external validation but does not control the WCFFBP ledger.

**Provisional** means that the source or treatment is presently used in a draft analytical result but remains subject to further reconciliation or replacement.

**Unresolved** means that a material accounting, timing, semantic, or geographic-incidence question remains open.

## Provenance Standard

WCFFBP seeks to preserve a reproducible evidentiary chain from published result to authoritative source. Depending on the source and analytical use, that chain may include:

**published result → accounting policy → reconciliation or validation evidence → transformed observation → acquisition record → authoritative source**

Source citations identify the publisher of the underlying data. WCFFBP evidence paths document how the project acquired, interpreted, validated, transformed, reconciled, and used those data.

A citation to an authoritative source does not, by itself, establish the correctness of a WCFFBP accounting treatment. Conversely, a WCFFBP analytical artifact does not replace citation of the authoritative source from which the underlying observation was obtained.

Where available, WCFFBP preserves source URLs or publication identity, retrieval metadata, source filenames, checksums, acquisition manifests, transformation code, validation evidence, and accounting-policy records. Not every source provides every element of this chain. Missing provenance elements should remain identifiable rather than being inferred away.

This distinction is fundamental to the project: **source authority, accounting authority, and geographic-incidence authority are separate questions.**

## Principal Source Families

### Internal Revenue Service — Federal Receipts

**Agency:** Internal Revenue Service, U.S. Department of the Treasury

**Principal role:** Measurement and allocation of federal receipts attributable to Washington.

WCFFBP maintains multiple IRS source families because state-level federal collections and county-level tax statistics answer different questions and are not interchangeable.

For state gross collections, the repository preserves annual IRS Data Book state workbooks for 2015 through 2024. The associated evidence includes an acquisition manifest, structural profiling, semantic certification, Washington-specific extracts, and Washington reconciliation artifacts.

WCFFBP separately preserves IRS Historic Table 2 state data for tax years 2015 through 2023, associated documentation extracts, acquisition records, and an individual-income-tax allocator certification.

County Statistics of Income data provide geographically detailed tax information and are evaluated for county allocation rather than treated as interchangeable with the IRS state fiscal-year collections series.

IRS-reported business income taxes attributed to Washington are described as such. Administrative collection geography is not assumed to establish the ultimate economic incidence of a tax.

**Repository areas:** `data/raw/irs/`, IRS ETL and validation code, and associated evidence packages.

### USAspending — Federal Assistance

**Agency:** U.S. Department of the Treasury, USAspending.gov

**Principal role:** Transaction-level evidence for federal assistance attributable to Washington.

USAspending assistance data provide detailed award, transaction, program, recipient, agency, and place information. WCFFBP uses these records both to identify federal inflows and to reconcile assistance against program-specific authoritative sources.

USAspending is not assumed to be additive merely because an award or transaction is associated with Washington. Program-specific sources may supersede USAspending as accounting controls where they provide a more authoritative measure of the relevant federal expenditure.

WCFFBP therefore maintains explicit accounting classifications and reconciliation evidence for assistance program families. The assistance evidence package distinguishes source measurement, overlap analysis, accounting policy, and final ledger treatment rather than treating them as a single analytical step.

**Repository areas:** `data/raw/usaspending/assistance/`, assistance ETL and validation code, and `evidence/assistance/accounting_policy/`.

### USAspending — Federal Procurement

**Agency:** U.S. Department of the Treasury, USAspending.gov

**Principal role:** Transaction-level evidence for federal procurement associated with Washington.

Procurement records are evaluated separately from assistance records. Awarding agency, funding agency, recipient location, place of performance, transaction timing, and program function can represent different concepts and are not treated as interchangeable evidence of Washington economic incidence.

Where a program-specific federal expenditure source already controls an expenditure category, USAspending procurement is reconciled against that source before any additive treatment.

For example, VA procurement transactions are retained as transaction-level provenance and reconciliation evidence rather than automatically creating a second expenditure path alongside VA program expenditure controls.

**Repository areas:** `data/raw/usaspending/`, procurement ETL/validation code, and associated reconciliation evidence.

### Social Security Administration — OASDI

**Agency:** Social Security Administration

**Principal role:** Federal benefit-payment accounting and county allocation for Old-Age, Survivors, and Disability Insurance.

WCFFBP has preserved SSA county-series evidence for 2015–2024 covering all 39 Washington counties. The certification records 3,510 normalized observations, 39 counties per year, nine benefit types per year, county/year controls, source-workbook hashes, and annual state controls.

For the empirically reconciled period, SSA benefit-payment data are the preferred accounting and county-allocation source for OASDI. Overlapping USAspending assistance records are not treated as an additional expenditure stream.

A material timing qualification is preserved: the county annualized amount is based on the published December monthly benefit multiplied by twelve and therefore represents an annualized run-rate rather than directly observed federal-fiscal-year cash outlays.

**Repository areas:** `data/raw/ssa/`, SSA ETL/validation code, and related accounting-policy evidence.

### Social Security Administration — Supplemental Security Income

**Agency:** Social Security Administration

**Principal role:** Measurement of Supplemental Security Income payments attributable to Washington.

SSI is treated separately from OASDI. WCFFBP preserves SSI-related source and analytical evidence, but the applicable source, timing basis, and geographic treatment must be evaluated independently rather than inferred from the OASDI methodology.

Where SSI values appear in draft statewide calculations, their provenance and timing treatment should be identified with the published result.

**Status:** Source family retained; published-result provenance remains component-specific.

### Department of Veterans Affairs — Geographic Distribution of Expenditures

**Agency:** U.S. Department of Veterans Affairs

**Principal role:** State and county accounting/allocation of VA expenditures.

WCFFBP acquired VA Geographic Distribution of Expenditures data across FY2015–FY2024 and evaluated all 39 Washington counties. The source evidence explicitly recognized from the beginning that VA GDX categories could overlap USAspending records and therefore required reconciliation before combination.

The evidence package preserves provenance, geographic coverage, units, annual Washington controls, and the FY2024 Direct/Indirect methodology change.

Earlier evidence artifacts correctly preserve the then-unresolved additive-status question. Subsequent WCFFBP accounting policy selected VA GDX as the preferred FY2024 VA accounting and allocation source, with USAspending VA procurement retained for provenance and reconciliation rather than treated as a second additive path.

The earlier evidence is retained as historical research provenance rather than rewritten to reflect a decision made later.

**Repository areas:** `data/raw/va/` and associated VA reconciliation/accounting evidence.

### Centers for Medicare & Medicaid Services — Original Medicare

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Measurement and geographic analysis of Original Medicare expenditures.

WCFFBP maintains CMS evidence concerning Original Medicare fee-for-service expenditures, including county-year structure, payment semantics, geographic coverage, suppression, timing, and reconciliation.

Suppressed observations are not assumed to equal zero.

CMS evidence artifacts distinguish source measurement from accounting policy and from geographic-incidence authority. They do not, merely by existing, authorize a county ledger allocation.

### Centers for Medicare & Medicaid Services — Medicare Advantage / Part C

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Evaluation of Medicare Advantage payments and their relationship to other Medicare expenditure streams.

WCFFBP evaluates Part C separately from Original Medicare and tests additivity, timing, and geographic incidence before ledger treatment.

Program enrollment, benchmark, capitation, and payment information are not assumed to represent identical accounting concepts.

### Centers for Medicare & Medicaid Services — Medicare Part D

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Evaluation of Part D federal expenditures and their relationship to other Medicare expenditure streams.

Part D is treated as a distinct Medicare expenditure component subject to reconciliation and timing review before final accounting treatment.

### Centers for Medicare & Medicaid Services — Retiree Drug Subsidy

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Evaluation of Retiree Drug Subsidy expenditure evidence.

WCFFBP has identified the Retiree Drug Subsidy as a potentially distinct Medicare-related federal expenditure stream. Available evidence supports continued investigation, but dollar incidence remains unresolved and is not inferred from program presence alone.

### Centers for Medicare & Medicaid Services — Medicare Shared Savings Program

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Evaluation of MSSP financial flows and assigned-beneficiary geography.

WCFFBP separately evaluates MSSP financial results and county-level assigned-beneficiary data. Temporal participation cohorts are preserved as such rather than deduplicated merely because an ACO identifier appears in more than one participation period.

Suppression, financial semantics, beneficiary geography, and the relationship between shared-savings/loss amounts and Medicare accounting totals are evaluated independently.

MSSP source validation does not itself authorize allocation of financial results among Washington counties.

### Centers for Medicare & Medicaid Services — Medicare Trustees

**Agency:** Centers for Medicare & Medicaid Services / Boards of Trustees of the Federal Hospital Insurance and Federal Supplementary Medical Insurance Trust Funds

**Principal role:** National Medicare accounting and semantic controls.

Trustees reports are used to understand program structure, expenditure categories, trust-fund relationships, and accounting semantics. They may serve as reconciliation or national-control evidence without themselves establishing Washington geographic incidence.

### Centers for Medicare & Medicaid Services — Medicaid

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** State-level Medicaid expenditure and federal-share analysis.

WCFFBP maintains Medicaid reconciliation work separating program-specific CMS controls from overlapping federal assistance records. The repository contains explicit Medicaid control-composition reconciliation code and execution evidence.

The existence of a CMS program total does not by itself establish county economic incidence. State accounting control and county allocation remain separate methodological questions.

### Centers for Medicare & Medicaid Services — Children's Health Insurance Program

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** State-level CHIP expenditure and federal-share analysis.

WCFFBP has acquired the CMS Annual CHIP Expenditures Report / CMS-21 source series for FY2015 through FY2024. The source manifest records all ten annual reports as downloaded.

CMS program totals are evaluated as program-specific accounting evidence and reconciled against overlapping USAspending records before additive treatment.

### Centers for Medicare & Medicaid Services — State Health Expenditures and Related Sources

**Agency:** Centers for Medicare & Medicaid Services

**Principal role:** Context, reconciliation, and evaluation of state-level health expenditure controls.

These sources are evaluated according to their specific accounting definitions and time bases. They are not presumed to be additive to Medicare, Medicaid, or CHIP merely because they report federal health spending.

### Office of Personnel Management — FedScope

**Agency:** U.S. Office of Personnel Management

**Principal role:** Federal civilian employment and compensation allocation evidence.

WCFFBP evaluates FedScope employment and salary data for geographic allocation of federal civilian compensation controls.

A material salary-field discontinuity begins in 2017. The share of records with blank salary values rises from approximately 0.05–0.09 percent in 2015–2016 to roughly 13 percent from 2017 onward. WCFFBP therefore does not treat blank salary records as zero or as a negligible random omission.

FedScope source validation does not by itself establish the final federal wage accounting control.

### Bureau of Economic Analysis — Federal Civilian and Military Compensation

**Agency:** U.S. Bureau of Economic Analysis

**Principal role:** State and county federal compensation evidence.

WCFFBP acquired BEA CAINC6N county data for Washington for federal civilian compensation and military compensation, using line codes 2001 and 2002. The acquisition covers the Washington state observation plus all 39 counties for 2015–2024.

BEA compensation data provide an independently defined economic-statistics measure and are evaluated against federal accounting controls before ledger use.

### Bureau of Economic Analysis — Federal Civilian and Military Wages and Salaries

**Agency:** U.S. Bureau of Economic Analysis

**Principal role:** State-level wage evidence and reconciliation.

WCFFBP acquired BEA SAINC7N Washington data for federal civilian and military wages and salaries for 2015–2024. The source is explicitly treated as calendar-year economic-statistics evidence rather than automatically as a federal-fiscal-year accounting control.

### Office of Management and Budget — Object Class Analysis / Federal Wage Controls

**Agency:** Office of Management and Budget

**Principal role:** Federal-fiscal-year national accounting controls for federal civilian and military personnel compensation.

WCFFBP preserves official Budget object-class evidence used to reconstruct historical federal wage controls. The project distinguishes estimates from subsequently published actual values and preserves vintage provenance rather than silently replacing earlier observations.

Where a subsequent Budget publication supplies an actual value for a historical fiscal year, WCFFBP prefers that actual value for the principal historical ledger while retaining earlier estimates for replication and provenance.

**Repository areas:** `data/raw/omb/object_class/`, `data/interim/omb/`, and associated validation evidence.

### Office of Management and Budget — Historical Tables / Federal Receipts Controls

**Agency:** Office of Management and Budget

**Principal role:** National federal-receipts universe, decomposition, and reconciliation controls.

This is analytically distinct from OMB's federal-wage role.

WCFFBP preserves OMB Historical Tables evidence for national federal receipts, including individual income taxes, corporation income taxes, social-insurance receipts, other receipts, and specialized receipt-allocation work. The repository contains explicit certification artifacts for the federal-receipts universe and several component controls and decompositions.

These national controls do not by themselves determine Washington's share. State attribution requires an independently justified allocation or administrative source.

### U.S. Census Bureau

**Agency:** U.S. Census Bureau

**Principal role:** Geographic reference data and population controls.

Census sources support canonical state/county geography, FIPS relationships, and population denominators used in per-capita and allocation analyses.

Population is a denominator or allocator only where the methodology explicitly assigns that role. Population is not assumed to be an appropriate allocator for every federal receipt or expenditure.

### Department of Housing and Urban Development — Voucher Management System

**Agency:** U.S. Department of Housing and Urban Development

**Principal role:** Program-specific housing-assistance measurement and reconciliation.

WCFFBP preserves HUD Voucher Management System source manifests for 2022–2024 together with structural profiling, Washington Housing Assistance Payment semantic/composition analysis, formula validation, USAspending Assistance Listing 14.871 comparison, timing analysis, and reconciliation evidence.

The repository also contains an explicit HUD Housing Choice Voucher assistance-accounting policy artifact.

The existence of a program-specific HUD source does not, by itself, establish additive treatment relative to USAspending. The controlling accounting-policy disposition governs ledger treatment.

### Department of Labor — Unemployment Insurance

**Agency:** U.S. Department of Labor, Employment and Training Administration

**Principal role:** Unemployment-insurance receipt/allocation evidence.

WCFFBP preserves ETA-2112 source data and an annual unemployment-insurance allocator profile with certification evidence.

DOL evidence is used according to the accounting concept established by the applicable receipt methodology rather than treated as a generic proxy for all labor-related federal flows.

### Federal Highway Administration — Highway Trust Fund

**Agency:** Federal Highway Administration, U.S. Department of Transportation

**Principal role:** Specialized state allocation evidence for Highway Trust Fund-related federal receipts.

WCFFBP preserves the FHWA Highway Statistics 2024 FE-221B workbook, its landing-page evidence, a specialized-allocator acquisition manifest/report, and an associated OMB allocator extract.

FHWA data serve as a specialized allocator where the applicable federal receipt methodology calls for such an allocator; they are not treated as a general measure of Washington federal taxes.

### U.S. Department of the Treasury — Fiscal Stabilization and Related Assistance

**Agency:** U.S. Department of the Treasury

**Principal role:** Program-specific assistance reconciliation.

WCFFBP maintains explicit analytical and accounting-policy work for Treasury fiscal-stabilization assistance, including a policy artifact and assistance-accounting bridge/profile evidence.

Treasury program evidence is evaluated according to the specific program and accounting concept involved rather than treated as a single undifferentiated Treasury expenditure source.

### Rockefeller Institute of Government — Balance of Payments

**Organization:** Rockefeller Institute of Government

**Principal role:** External methodological reference and diagnostic comparison.

Rockefeller Institute state balance-of-payments studies are useful for comparing definitions, identifying source families, understanding alternative state/federal fiscal-balance methodologies, and evaluating WCFFBP results in an external methodological context.

They are not calibration targets. WCFFBP does not alter an independently derived result merely to reproduce a Rockefeller estimate.

The Draft-1 evidence expressly treats external Rockefeller estimates as diagnostic/reference evidence rather than as accounting controls.

Where third-party publications are not redistributed by WCFFBP, the project may preserve citation information, retrieval metadata, hashes, methodological extracts where appropriate, and derived factual evidence sufficient to document their analytical use.

## Additional and Supporting Sources

WCFFBP also evaluates or preserves evidence from additional federal sources where needed to establish a particular accounting control, allocator, denominator, timing relationship, or reconciliation.

A source's presence in `data/raw/`, an acquisition manifest, ETL code, or an evidence package should therefore not be interpreted as automatic inclusion in the fiscal-balance ledger.

The authoritative status of a source is determined component by component.

## Source Selection and Overlap

Federal programs are often represented in more than one federal dataset.

For example, the same underlying expenditure may appear in:

- a program-specific agency publication;
- USAspending assistance data;
- USAspending procurement data;
- a federal budget or trust-fund control;
- a state or county statistical series; or
- an external research compilation.

WCFFBP does not sum such sources merely because each independently contains a federal-dollar value.

Where overlap is plausible, the project seeks to establish:

**what was measured → whether the observations describe the same economic event → which source has accounting priority → whether any residual is genuinely additive.**

Explicit accounting-policy records are preferred over implicit assumptions.

## Time Basis

WCFFBP's principal accounting framework is organized by federal fiscal year where the source permits.

Not every federal source is reported on that basis.

Sources may instead represent:

- calendar years;
- tax years;
- December monthly observations annualized to a run-rate;
- point-in-time employment observations;
- award-action dates;
- periods of performance;
- program years; or
- other source-specific reporting periods.

WCFFBP does not silently convert one time basis into another.

Where conversion, annualization, or temporal allocation is required, the method should be explicitly identified and preserved.

## Geographic Interpretation

A Washington-associated federal record does not necessarily establish Washington economic incidence.

Relevant geographic concepts may include:

- taxpayer address;
- recipient address;
- place of performance;
- beneficiary residence;
- employee duty station;
- administrative collection geography;
- agency reporting geography; and
- modeled economic incidence.

These concepts are not presumed equivalent.

Similarly, establishment of a Washington statewide accounting control does not automatically establish how that amount should be distributed among Washington's 39 counties.

County allocation requires its own evidence and methodology.

## Missing, Suppressed, and Unavailable Data

WCFFBP distinguishes among:

- zero;
- missing;
- suppressed;
- unavailable;
- not applicable; and
- unresolved.

These states are not interchangeable.

A suppressed observation is not assumed to be zero. A missing value is not automatically imputed. Where an estimate or allocation is necessary, the method should be separately identified from the observed source value.

## COVID-19 and Other Extraordinary Federal Spending

WCFFBP preserves COVID-related federal expenditures and other extraordinary federal interventions as analytical classifications wherever feasible.

These expenditures are not discarded merely because they are unusual. They represent real federal fiscal flows.

At the same time, extraordinary spending can materially affect comparisons across years. WCFFBP therefore seeks to support both inclusive views and analytically useful classifications that allow extraordinary spending to be separately identified.

Classification does not imply exclusion from the principal ledger.

## Source Preservation and Reproducibility

WCFFBP seeks to preserve enough evidence to allow an outside analyst to reconstruct how a published result was produced.

As a general policy:

> **WCFFBP will preserve analytical code, transformations, validation evidence, source manifests, checksums, acquisition metadata, and published results in Git. Bulk reproducible source archives will not ordinarily be stored in Git when they can be reacquired from authoritative sources.**

Source preservation therefore falls broadly into three categories.

**Repository-preserved:** source artifacts sufficiently small and appropriate for direct preservation in the repository.

**Externally reproducible:** bulk or otherwise unsuitable source files represented by authoritative source identity, retrieval information, hashes, manifests, and acquisition code sufficient to reacquire and verify the source.

**Citation-only or conservatively non-redistributed:** third-party material for which WCFFBP preserves the citation, source identity, retrieval/provenance evidence, and analytical methodology without necessarily redistributing the underlying publication.

A file's absence from Git therefore does not necessarily represent a break in provenance.

## Historical Evidence and Current Policy

WCFFBP is a versioned research project.

Earlier evidence may accurately record that a question was unresolved at the time the evidence was produced. A later accounting policy may resolve that question.

The earlier artifact should ordinarily remain intact.

WCFFBP therefore distinguishes between:

**historical research state** — what had been established at a particular point in the investigation; and

**current accounting policy** — the presently adopted treatment based on the accumulated evidence.

This allows reviewers to see not only the current conclusion but how the project reached it.

## Relationship to Published Results

`DATA_SOURCES.md` establishes **source-level provenance**. It is not intended to be the terminal citation for every reported dollar value.

Material numbers in published WCFFBP results should identify the specific accounting control, transformation, reconciliation or allocation methodology, and applicable evidence supporting that result.

Accordingly, a published value should, where applicable, be traceable backward through:

**published value → ledger/component record → accounting policy → validation/reconciliation → transformation → acquisition record → authoritative source**

This provides two complementary forms of auditability:

- `DATA_SOURCES.md` explains the source families and their permitted analytical roles.
- Published-result evidence explains exactly how a particular reported value was produced.

## Continuing Source Development

WCFFBP is intentionally iterative.

Sources may be added, superseded, reclassified, or assigned different analytical roles as better evidence becomes available. Such changes should be documented rather than silently incorporated.

The objective is not to preserve an early methodology unchanged. It is to preserve enough evidence that methodological improvement itself remains reproducible.

The project's federal fiscal-balance reporting convention is:

**Federal Fiscal Balance = Federal Inflows to Washington − Federal Outflows from Washington**

where federal inflows are federal expenditures attributable to Washington and federal outflows are federal taxes and other federal receipts attributable to Washington.

A positive balance means Washington receives more from the federal government than it sends. A negative balance means Washington sends more than it receives.

The same convention applies to county-level balances.

> **Measure first. Explain later.**