# WCFFBP Data Dictionary

## Washington County Federal Fiscal Balance Project

This document defines the principal analytical concepts, status values, geographic identifiers, time bases, provenance fields, and database objects used by the Washington County Federal Fiscal Balance Project (WCFFBP).

It is intended to help an independent researcher understand what WCFFBP data **mean**, not merely how the PostgreSQL database is structured.

The SQL definitions in the repository remain the authoritative implementation specification. This document provides the semantic layer needed to interpret those structures correctly.

For source selection and provenance, see `DATA_SOURCES.md`.

For accounting rules and analytical principles, see `METHODOLOGY.md`.

---

## 1. Fundamental Accounting Concepts

### Federal inflow

A **federal inflow** is a federal expenditure or other qualifying federal resource attributable to Washington under the applicable WCFFBP accounting and geographic-incidence methodology.

A source observation does not become a federal inflow merely because it appears in a federal expenditure database.

It must first satisfy the applicable rules for:

- accounting measure;
- source authority;
- overlap and duplicate treatment;
- time basis;
- geographic attribution;
- ledger authorization; and
- methodological status.

### Federal outflow

A **federal outflow** is a federal tax or other qualifying federal receipt attributable to Washington under the applicable WCFFBP methodology.

The term is expressed from the perspective of Washington rather than from the perspective of the federal government.

Thus:

- federal expenditures attributable to Washington are **inflows**; and
- federal receipts attributable to Washington are **outflows**.

### Federal fiscal balance

The canonical WCFFBP reporting convention is:

**Federal Fiscal Balance = Federal Inflows to Washington − Federal Outflows from Washington**

Therefore:

- a **positive** balance means measured federal inflows exceed measured federal outflows;
- a **negative** balance means measured federal outflows exceed measured federal inflows; and
- zero means the two are equal.

The same convention applies to state and county calculations.

Historical analytical artifacts may contain an earlier or opposite arithmetic convention. Those artifacts are preserved as research evidence and should not be silently rewritten. Current published WCFFBP results use the canonical convention above.

---

## 2. Measurement Is Not Accounting Treatment

WCFFBP distinguishes between observing a dollar and authorizing that dollar to enter a fiscal-balance calculation.

A value may therefore be:

1. acquired from an authoritative source;
2. preserved in the database;
3. normalized;
4. validated;
5. geographically attributed;
6. reconciled against another source; and yet
7. still not be authorized for additive inclusion in the federal fiscal-balance ledger.

This distinction is intentional.

**Presence in the database does not imply ledger inclusion.**

For example, the Medicare core accounting structures preserve certified county- and state-level values while explicitly preserving statuses indicating that loading the observations does not itself authorize their inclusion in the federal-inflow ledger.

---

## 3. Source Authority, Accounting Authority, and Geographic Authority

WCFFBP treats three questions separately.

### Source authority

**Is this an authoritative source for the observed value?**

A federal agency may be authoritative for a published observation without necessarily being the source selected for the final WCFFBP accounting measure.

### Accounting authority

**Which source or accounting pathway is permitted to contribute the dollar to the fiscal-balance ledger?**

Multiple federal systems may report the same underlying economic resource.

WCFFBP therefore selects an accounting pathway rather than summing every available observation.

### Geographic authority

**Does the source establish where the economic incidence of the expenditure or receipt belongs?**

Administrative recipient geography, place of performance, place of work, beneficiary residence, taxpayer address, and other geographic concepts are not presumed to be interchangeable.

A source can be authoritative for the dollar amount without being authoritative for county allocation.

---

## 4. One Federal Dollar, One Accounting Path

The WCFFBP overlap-control architecture implements the principle:

**One Federal Dollar, One Accounting Path.**

Where multiple source systems represent the same underlying federal resource, only the authorized accounting pathway may contribute the dollar to the principal ledger.

Other observations may remain in the database for:

- provenance;
- reconciliation;
- geographic analysis;
- classification;
- validation; or
- sensitivity analysis.

Exclusion from the additive ledger therefore does not imply that an observation is erroneous or unimportant.

---

# 5. Core Accounting Vocabulary

## `accounting_measure`

The economic or federal-accounting quantity represented by an observation or control.

Examples include compensation of employees and obligations by object class.

An accounting measure should not be inferred solely from the name of a program or source system.

## `inflow_family`

High-level WCFFBP classification describing the economic or program family to which a federal inflow belongs.

Examples may include Social Security, Medicare, Medicaid, Veterans Affairs, federal wages, or other federal expenditure families.

Program classification describes **what an expenditure represents**. It does not independently determine whether the observation enters the ledger.

## `inflow_subfamily`

More specific classification within an `inflow_family`.

Subfamilies allow distinct accounting rules to be assigned to economically different components within the same broad federal program family.

## `preferred_source`

The source selected to provide the authoritative accounting amount for a federal inflow family or subfamily.

A preferred source does not necessarily have to provide the geographic allocation used by WCFFBP.

## `allocation_source`

A source used to distribute or allocate an authoritative accounting amount geographically.

An allocation source does **not** independently add dollars to the fiscal-balance ledger.

This distinction allows WCFFBP to use one source for accounting authority and another for geographic information when the evidence supports doing so.

## `overlapping_sources`

Other source systems known or suspected to represent some or all of the same underlying expenditure family.

These sources are retained for reconciliation and provenance even when they are not independently additive.

## `overlap_risk`

Classification describing the risk that a source program is also represented in another federal expenditure source.

Implemented values include:

- `NONE`
- `LOW`
- `MODERATE`
- `HIGH`
- `KNOWN_OVERLAP`

Overlap risk identifies a reconciliation problem. It is not, by itself, an accounting disposition.

---

# 6. Source-Policy Ledger Treatment

The field `ledger_treatment` belongs to the **source-policy layer**.

It describes how an expenditure family is permitted to interact with the final ledger.

Implemented values include:

### `INCLUDE`

The source or accounting pathway is approved for inclusion subject to the applicable methodology.

### `INCLUDE_AFTER_RECONCILIATION`

The source may enter the ledger only after the required overlap or accounting reconciliation has been completed.

### `EXCLUDE_DUPLICATE`

The source represents dollars accounted for through another authorized pathway and therefore must not create a second additive inflow.

### `ALLOCATE_ONLY`

The source may be used for geographic allocation but does not itself contribute additional dollars.

### `SEPARATE_CREDIT_MEASURE`

The observation belongs to a separately reported credit-related measure rather than the principal additive expenditure measure.

### `SEPARATE_CONTINGENT_MEASURE`

The observation represents a contingent or otherwise separately treated measure rather than an ordinary additive expenditure.

### `REVIEW_REQUIRED`

The accounting treatment has not yet been resolved sufficiently for final ledger inclusion.

These values describe **source policy** and should not be conflated with the transaction- or award-level accounting dispositions described below.

---

# 7. Transaction and Award Accounting Dispositions

The later assistance accounting architecture resolves individual programs or awards into a more specific accounting vocabulary.

Implemented dispositions include:

### `INCLUDE_ADDITIVE`

The observation is authorized to contribute dollars additively under the applicable accounting policy.

### `EXCLUDE_DUPLICATE`

The observation represents an economic resource already accounted for through another authorized pathway.

It remains available for provenance and reconciliation but does not add a second set of dollars.

### `WITHHOLD_UNRESOLVED`

Available evidence is insufficient to establish additive treatment.

The amount is withheld rather than forced into or out of the principal ledger.

### `REFERENCE_ONLY`

The observation is retained for reference, reconciliation, provenance, or analytical context but is not an additive ledger component.

### `UNCLASSIFIED_REVIEW`

No sufficiently specific accounting classification has yet been established.

This is a fail-closed state: lack of classification does not default to additive inclusion.

## Accounting resolution hierarchy

For assistance accounting, WCFFBP resolves treatment in the following order:

1. **award-specific accounting classification**
2. **explicit program-to-source-policy mapping**
3. **unclassified review**

Award-specific classification takes precedence.

Program-policy mappings are explicit. They are not inferred from fuzzy matches, broad program-family similarities, or program-code prefixes.

---

# 8. Ledger Authorization and Accounting Status

## `ledger_authorization`

Explicit indication of whether an observation or certified analytical product has itself been authorized to contribute to a ledger.

A value may be completely valid as a source observation while carrying a status such as:

`NOT_AUTHORIZED_BY_THIS_CERTIFICATION`

That status means exactly what it says: the certification establishes the observation or analytical result but does not independently make the final accounting decision.

## `ledger_status`

Status field used by some accounting-integration structures to preserve the ledger state of the source certification.

For example:

`NOT_YET_AUTHORIZED`

indicates that the value has been preserved and validated but that final federal-inflow authorization remains a separate methodological decision.

## `methodology_version`

Identifier for the methodology under which a classification, policy, allocation, reconciliation, or certification was created.

Methodology identifiers are part of the research record.

A later methodology may supersede an earlier decision without destroying the earlier evidence.

---

# 9. Time Vocabulary

Time basis is explicit in WCFFBP because federal source systems do not all describe the same reference period.

## `fiscal_year`

A federal fiscal-year observation.

Where a field specifically represents federal fiscal year, WCFFBP may also describe it as `FFY`.

A fiscal-year value should not be silently substituted for a calendar-year value or vice versa.

## `calendar_year`

An observation whose source reference period is the calendar year.

For example, the BEA compensation observations currently used by WCFFBP are explicitly stored as `CALENDAR_YEAR`.

They must not be silently relabeled as federal fiscal year.

## `report_year`

Year associated with the reporting period of a source publication.

A report year does not automatically establish that the underlying economic measure is federal-fiscal-year based.

## `reference_period_type`

Explicit description of the time basis represented by an observation.

Examples include:

`CALENDAR_YEAR`

The field exists to prevent the apparent convenience of a four-digit year from concealing differences in temporal meaning.

## `budget_vintage`

The federal budget publication vintage from which an OMB observation was obtained.

For the OMB federal wage controls, WCFFBP preserves the budget vintage independently from the target fiscal year.

## `value_status`

Status assigned by the authoritative source to a reported value.

For OMB Object Class Analysis, implemented values include:

- `ACTUAL`
- `ESTIMATE`

WCFFBP preserves this distinction.

---

# 10. Geographic Vocabulary

## `state_id`

Internal WCFFBP surrogate identifier for a state.

References `reference.state_registry`.

It should not be confused with the Census/FIPS state code.

## `state_fips`

Two-character state FIPS code.

Washington is represented by its standard FIPS state code.

## `county_id`

Internal WCFFBP surrogate identifier for a county.

References `reference.county_registry`.

## `county_fips`

Depending on the source-specific structure, this term may represent either a source county identifier or a canonical five-character county FIPS value.

Researchers should inspect the relevant table definition rather than assume field width from the field name alone.

Within `reference.county_registry`, the three-character county component is stored separately from `full_fips`.

## `full_fips`

Canonical five-character state-plus-county FIPS identifier in `reference.county_registry`.

This is the preferred unambiguous geographic identifier when state and county components must be represented together.

## `geography_level`

Level represented by an observation.

Examples include:

- `STATE`
- `COUNTY`

Source-specific implementations may support additional levels.

## `geographic_basis`

The economic or administrative concept by which an observation is geographically attributed.

This is distinct from `geography_level`.

For example, a county-level value may still represent a **place-of-work** measure rather than residence-based economic incidence.

## `PLACE_OF_WORK`

Geographic basis used by the initial BEA federal compensation series.

It means the compensation observation is attributed according to place of work.

It should not be interpreted as a residence-based measure without a separate allocation methodology.

## Administrative geography

A location attached to a federal administrative record—for example, recipient address, awarding location, or other program-administration geography.

Administrative geography does not automatically establish economic incidence.

## Economic incidence

The geographic location to which WCFFBP determines that a federal receipt or expenditure should be attributed for the purpose of the fiscal-balance calculation.

Economic incidence may require evidence or allocation beyond the administrative geography contained in the source record.

---

# 11. Value and Completeness Vocabulary

## Observed value

A value reported directly by a source and preserved as an observation.

Where practical, WCFFBP preserves both the source representation and a normalized accounting representation.

## Normalized value

A source observation converted into a consistent machine-readable unit or format without changing its intended economic meaning.

For example, a source value reported in thousands of dollars may be preserved in its original form while also being normalized to whole dollars.

Normalization does not itself authorize ledger inclusion.

## Reconstructed value

A value derived from source components according to an explicit, reproducible procedure.

A reconstructed value is not represented as directly observed merely because it is ultimately derived from authoritative source data.

## Allocated value

A value geographically distributed using an explicit allocation source or rule.

Allocation changes geographic attribution; it does not create additional federal dollars.

## Estimated value

A value whose source or methodology explicitly identifies it as an estimate rather than an actual observation.

Estimated and actual values are not silently treated as equivalent.

## `NULL`

Absence of a database value.

`NULL` does not mean zero.

Depending on the source and field, it may indicate:

- unavailable data;
- incomplete coverage;
- unresolved accounting treatment;
- non-applicability; or
- a value intentionally not constructed.

The applicable source and methodology documentation determine its meaning.

## Suppressed

A source indicates that a value has been withheld or obscured, commonly for confidentiality or disclosure-control reasons.

**Suppressed is not zero.**

WCFFBP does not replace suppressed observations with zero merely to make an aggregation complete.

## Unresolved

Available evidence is insufficient to make the required accounting, timing, or geographic-incidence determination.

Unresolved values are preserved as unresolved rather than resolved through unsupported assumptions.

## Partial or incomplete

The source observation covers less than the intended analytical period, geography, program universe, or other required scope.

Partial observations are not silently extrapolated to complete observations.

---

# 12. Provenance Vocabulary

## `source_file`

File from which an observation or load was derived.

Where appropriate, source filenames are preserved as part of the analytical provenance chain.

## `source_sha256` / `source_file_sha256`

SHA-256 cryptographic digest of a preserved source artifact.

Hashes allow an independent researcher to determine whether a source artifact is byte-for-byte identical to the artifact used by WCFFBP.

## `source_row_number`

Row location of an observation in a source artifact or source-derived input.

It provides record-level traceability where the source format permits it.

## Source location

Some source domains preserve additional coordinates such as:

- source sheet;
- source row;
- source column; or
- source page.

These fields allow normalized observations to be traced back to their source representation.

## Load batch

A defined database-ingestion event associated with a particular source acquisition or preserved source vintage.

Load-batch records may include:

- source identity;
- source hash;
- retrieval timestamp;
- expected and actual row counts;
- load status;
- methodology or schema regime; and
- notes.

A load batch is a provenance concept, not an economic unit.

## Acquisition vintage

The particular retrieved version of a source dataset used by WCFFBP.

Multiple vintages may be preserved when necessary to reproduce historical methodology or identify source revisions.

## Observation

A source record received or preserved by WCFFBP.

An observation is not necessarily a unique economic transaction.

The same underlying transaction may be observed in more than one acquisition batch.

## Canonical transaction

The WCFFBP representation selected to represent a unique transaction in the canonical transaction layer.

For USAspending assistance, the distinction between observation grain and canonical transaction grain prevents cross-batch re-observation from becoming additive federal spending.

---

# 13. Principal Reference and Control Objects

## `reference.state_registry`

Canonical state reference table.

Important fields include:

- `state_id`
- `state_fips`
- `state_abbreviation`
- `state_name`
- `census_region`
- `census_division`

## `reference.county_registry`

Canonical county reference table.

Important fields include:

- `county_id`
- `state_id`
- `county_fips`
- `full_fips`
- `county_name`
- `county_type`

`full_fips` is unique.

## `reference.federal_inflow_program_classification`

Cross-source classification of federal inflow programs.

It answers:

**What kind of federal inflow does this source program represent?**

Important fields include:

- `source_system`
- `source_program_code`
- `source_program_title`
- `inflow_family`
- `inflow_subfamily`
- `overlap_risk`
- `covid_relevance`
- `extraordinary_relevance`
- `classification_basis`
- `methodology_version`
- validity years

This table classifies the expenditure. It does not independently decide whether that source is additive to the final ledger.

## `reference.federal_inflow_source_policy`

Methodological control table governing how an inflow family may contribute to the deduplicated fiscal-balance ledger.

It answers:

**How is this expenditure family allowed to enter the ledger?**

Important fields include:

- `inflow_family`
- `inflow_subfamily`
- `accounting_measure`
- `preferred_source`
- `allocation_source`
- `overlapping_sources`
- `ledger_treatment`
- `source_selection_basis`
- `methodology_version`
- validity years

## `reference.federal_inflow_award_classification`

Award-level accounting classification.

Used when a program cannot safely receive one accounting treatment solely from its program or Assistance Listing code.

Important fields include:

- `source_system`
- `source_program_code`
- `source_award_identifier`
- `inflow_family`
- `inflow_subfamily`
- `accounting_disposition`
- `classification_basis`
- `methodology_version`
- validity years

Award-specific classification has precedence over a less-specific program mapping.

## `reference.federal_inflow_program_policy_mapping`

Explicit mapping between a source-system program code and an established source policy.

Important fields include:

- `source_system`
- `source_program_code`
- `federal_inflow_source_policy_id`
- `resolved_accounting_disposition`
- `mapping_basis`
- `methodology_version`
- validity years

The mapping is used only where a more-specific award classification does not apply.

It exists specifically to prevent accounting treatment from being inferred through fuzzy or family-only joins.

---

# 14. Principal Source-Domain Objects

The following are important examples rather than an exhaustive catalog of every staging and normalization table in the repository.

## IRS

### `irs.state_collections`

State-level IRS collection observations.

Important fields include:

- `fiscal_year`
- `state_id`
- `tax_category`
- `returns_filed`
- `gross_collections_thousands`
- `refunds_issued`
- `refund_amount_thousands`
- `source_file`

Gross collections and refunds are separately represented.

## Social Security Administration

### `ssa.benefit_payments`

County-level Social Security benefit-payment observations.

Important fields include:

- `report_year`
- `state_id`
- `county_id`
- `benefit_type`
- `beneficiary_count`
- `monthly_benefits_thousands`
- `annual_benefits_thousands`
- `source_file`
- `source_table`

The reporting-year and payment-period semantics must be interpreted according to the relevant methodology rather than assumed from the presence of an annualized field.

## Department of Veterans Affairs

### `va.gdx_load_batch`

Provenance and load accounting for VA Geographic Distribution of Expenditures source workbooks.

The schema explicitly preserves the methodological break between the legacy FY2015–FY2023 source regime and the revised FY2024 regime.

### `va.gdx_county_expenditure`

County-level VA GDX expenditure observations.

Important concepts include:

- fiscal year;
- county;
- schema regime;
- expenditure class;
- source category;
- source amount;
- source unit;
- normalized expenditure amount;
- exact source location.

The table preserves source values while normalizing expenditure amounts to dollars.

### `va.gdx_county_metric`

Non-expenditure VA county metrics.

Metrics such as veteran population and unique patients are intentionally stored separately from expenditures so they cannot accidentally be summed into federal expenditures.

### `va.v_washington_county_gdx_control_total`

County-level annual VA GDX control-total view.

The underlying GDX schema changed in FY2024, so the view applies the appropriate source-regime logic rather than assuming one identical source structure across all years.

Accounting authority remains governed by the applicable current WCFFBP source policy.

## Bureau of Economic Analysis

### `bea.compensation_observation`

BEA federal civilian and military compensation observations.

Important fields include:

- `compensation_family`
- `accounting_measure`
- `reference_period_type`
- `calendar_year`
- `geographic_basis`
- `geography_level`
- `state_id`
- `county_id`
- source table and line code;
- source geography;
- original source value and unit;
- `value_dollars`;
- source file and hash.

The initial series represent:

- federal civilian compensation; and
- military compensation.

The observations are **calendar-year, place-of-work compensation measures**.

That semantic identity is preserved even when the observations are later used in an allocation or reconciliation procedure.

## Office of Management and Budget

### `omb.object_class_observation`

Atomic OMB Object Class Analysis observations used to construct federal wage-obligation controls.

Important fields include:

- `target_fiscal_year`
- `budget_vintage`
- `value_status`
- `accounting_measure`
- `scope`
- `object_class_code`
- `object_class_description`
- `obligation_millions`
- `obligation_dollars`
- source page;
- source file;
- source hash;
- source verification.

The source observations remain distinct from WCFFBP-derived wage totals.

### `omb.v_federal_wage_obligation_control`

Derived government-wide federal wage-obligation control.

Current derivation:

**Military wages**

`11.6 + 11.7`

**Nonmilitary wages**

`11.1 + 11.3 + 11.5 + 11.8`

**Total wages**

`Military wages + Nonmilitary wages`

The view derives these controls from preserved atomic observations rather than storing an unexplained aggregate.

## Office of Personnel Management / Federal Wage Allocation

### `opm.civilian_wage_allocation_evidence`

Evidence structure supporting allocation of the national nonmilitary federal wage control to Washington.

The OPM domain must be interpreted with its suppression diagnostics; suppressed salary observations are not treated as zero.

### `analysis.v_wa_federal_wage_allocation`

Certified Washington federal civilian-plus-military wage allocation view.

The view combines separately developed civilian and military allocation methodologies while preserving their methodology identifiers and validation requirements.

## Centers for Medicare & Medicaid Services

### `cms.medicare_core_county_year`

Certified county-year Medicare accounting integration structure.

Important fields include:

- `calendar_year`
- `county_fips`
- `county_id`
- Original Medicare/FFS dollars;
- Part C dollars;
- Part D dollars;
- core Medicare dollars;
- component status fields;
- completeness fields;
- timing basis;
- geography bases;
- treatment fields;
- ledger authorization;
- methodology version;
- source file and hash.

`core_medicare_dollars` is populated only where the certified integration supports a complete core value. Missing completeness is preserved rather than silently replaced.

Loading the table does not itself authorize ledger inclusion.

### `cms.medicare_core_state_year`

Certified Washington state-level Medicare accounting integration structure.

It preserves:

- Original Medicare/FFS;
- reconstructed Part C;
- reconstructed Part D;
- core Medicare sum;
- coverage/completeness information;
- timing status;
- ledger status; and
- methodology version.

The load performs no silent calendar-year-to-fiscal-year conversion, imputation, extrapolation, or ledger authorization.

The state-level certified value is not assumed to be merely the sum of the county table unless the methodology explicitly establishes that relationship.

---

# 15. USAspending Assistance Analytical Objects

## `analysis.v_certified_assistance_ledger`

Canonical certified assistance transaction ledger.

Its analytical grain is one canonical assistance transaction.

This object should not be confused with the raw observation universe.

## `analysis.v_assistance_transaction_observation_ledger`

Observation-grain analytical view.

Its grain is one raw assistance observation.

The observation pathway is conceptually:

**raw observation → observation bridge → canonical transaction → certified assistance ledger**

This structure allows WCFFBP to preserve multiple observations of a transaction across source acquisitions without counting those re-observations as additional federal spending.

Important identifiers distinguish:

- observation load batch;
- observation source row;
- canonical transaction;
- canonical load batch; and
- canonical source row.

These meanings should not be collapsed.

---

# 16. Metadata Objects

## `metadata.dataset_release`

Records named WCFFBP dataset releases.

Important fields:

- release version;
- release date;
- description;
- creation timestamp.

## `metadata.source_manifest`

Registry for source identity and basic citation metadata.

Important fields:

- source name;
- agency;
- source URL;
- citation;
- update frequency;
- first year;
- last year.

More detailed source provenance may also exist in domain-specific acquisition manifests and evidence artifacts.

## `metadata.variable_registry`

Registry for named analytical variables.

Important fields:

- variable name;
- display name;
- description;
- units;
- data type.

## `metadata.etl_run_log`

General ETL execution record.

Important fields:

- process name;
- start and completion time;
- status;
- records processed;
- notes.

Domain-specific load-batch structures may preserve substantially more provenance than this general log.

---

# 17. Raw, Curated, Reference, Analysis, and Reporting Layers

WCFFBP uses database schemas and repository structures for different analytical roles.

Although individual domains vary, the following conceptual distinction is useful.

### Raw layer

Preserves source observations with minimal semantic transformation.

Raw data are not automatically ledger data.

### Curated/source-domain layer

Normalizes source-specific observations while preserving their source semantics and provenance.

Examples include `ssa`, `va`, `cms`, `bea`, `omb`, `procurement`, and `assistance` structures.

### Reference layer

Stores canonical geography, program classifications, accounting policies, and other controlled methodological dimensions.

### Analysis layer

Contains analytical bridges, reconciliations, allocations, certified transaction views, and other derived structures used to implement WCFFBP methodology.

### Reporting layer

Contains views intended to summarize analytical results.

Not every historical reporting view represents the current WCFFBP Reference Calculation.

Researchers should consult current methodology and release documentation before treating a reporting object as authoritative.

---

# 18. Historical and Intermediate Objects

WCFFBP is an evolving research system.

The repository intentionally preserves historical migrations, earlier reporting views, diagnostic analyses, validation artifacts, and superseded methodological states where they provide useful audit evidence.

Therefore:

**existence in the repository does not imply current methodological authority.**

Examples include earlier partial fiscal-balance views and source-specific reporting structures created before later overlap, timing, or incidence questions were resolved.

Historical artifacts should be interpreted according to:

- their creation point in the research sequence;
- their methodology version;
- subsequent accounting-policy migrations;
- current `METHODOLOGY.md`; and
- the documentation associated with the applicable published release.

They are preserved because reproducibility includes the ability to understand how the methodology changed.

---

# 19. Source Values and Derived Values

WCFFBP attempts to preserve a visible distinction between:

**Source values**
Values published or directly represented by an authoritative source.

**Normalized values**
Source values converted into consistent units or database representations.

**Derived values**
Values calculated from source observations according to explicit WCFFBP rules.

**Allocated values**
Authoritative amounts distributed geographically according to an explicit allocation methodology.

**Published values**
Values selected and authorized for a particular WCFFBP release or Reference Calculation.

A derived or allocated value should be reproducible from its underlying source observations and methodology.

---

# 20. COVID and Extraordinary Funding

COVID relevance and extraordinary-funding status are analytical dimensions separate from ordinary ledger inclusion.

An expenditure can simultaneously be:

- a valid federal expenditure;
- additive or non-additive under the accounting methodology; and
- COVID-related or otherwise extraordinary.

COVID classification therefore does not itself determine whether a transaction is included or excluded from the principal ledger.

WCFFBP preserves these dimensions so results can support both inclusive and appropriately defined alternative views without destroying the underlying transaction history.

---

# 21. Zero, Missing, Suppressed, and Withheld Are Different

These states must not be conflated.

| State | Meaning |
|---|---|
| `0` | Observed or derived value is zero under the applicable methodology |
| `NULL` | No database value is present |
| Suppressed | Source intentionally withholds or obscures a value |
| Missing | Required observation is unavailable |
| Partial | Observation does not cover the complete required scope |
| Unresolved | Methodological evidence is insufficient for a determination |
| Withheld | WCFFBP intentionally prevents additive treatment pending resolution |
| Excluded duplicate | Dollar is accounted for through another authorized pathway |

A convenient numerical substitution is not a valid reason to convert one state into another.

---

# 22. Database Identifiers Are Not Economic Meaning

Fields ending in `_id` commonly provide database identity or relationships.

Examples include:

- `state_id`
- `county_id`
- `load_batch_id`
- `gdx_category_id`
- `federal_inflow_source_policy_id`

These identifiers should not be interpreted as economic classifications.

Conversely, fields such as:

- `inflow_family`
- `accounting_measure`
- `geographic_basis`
- `ledger_treatment`
- `accounting_disposition`

carry analytical meaning and should not be treated merely as database labels.

---

# 23. Authoritative Implementation

This data dictionary intentionally does not reproduce every column from every WCFFBP table.

The authoritative implementation remains the version-controlled SQL, ETL code, validation code, evidence artifacts, and source manifests contained in the repository.

When this document and an implementation detail appear inconsistent:

1. identify the relevant release and methodology version;
2. inspect the version-controlled implementation;
3. inspect the associated validation or reconciliation evidence;
4. determine whether the difference reflects a documented methodological change; and
5. report an unexplained inconsistency as a reproducibility issue.

Do not silently resolve the difference.

---

# 24. Relationship to Other WCFFBP Documentation

### `README.md`

Provides the public orientation to the project, its purpose, research philosophy, and Reference Calculation concept.

### `METHODOLOGY.md`

Defines the governing analytical principles and accounting methodology.

### `DATA_SOURCES.md`

Defines the principal source families, provenance model, source-selection concepts, and source-preservation approach.

### `DATA_DICTIONARY.md`

Defines the meaning of the principal analytical vocabulary and database structures.

Together, these documents provide the public interpretive layer over the version-controlled research implementation.

---

# 25. Reproducibility Principle

A database field should not require institutional memory to interpret correctly.

Where an analytical distinction materially affects the fiscal-balance calculation, WCFFBP seeks to represent that distinction explicitly through:

- source provenance;
- controlled vocabulary;
- accounting policy;
- methodology version;
- validation evidence;
- geographic basis;
- time basis; or
- ledger status.

The purpose of the data dictionary is therefore not merely to answer:

> **What columns exist?**

It is also to answer:

> **What does this observation mean, where did it come from, what may it be used for, and what would have to be true before it can affect the Washington federal fiscal balance?**

**Measure first. Explain later.**
