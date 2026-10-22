# WCFFBP Accounting Registry — v0.2 WORKING CANDIDATE

This is an evidence-navigation and accounting-control registry, **not a final fiscal ledger**.

- `source_family_registry.csv`: source families, parents, methodological status, ledger gate.
- `evidence_crosswalk.csv`: original repository evidence and review state.
- `annual_accounting_matrix.csv`: 2018–2024 source-year slots; only Medicare CY amounts recovered from verified reports so far.
- `CHANGELOG.md`: tracked changes and unresolved decisions.

**Rules:** Never add parent `MEDICARE_CORE` to its children. Source availability, accounting certification, and ledger authorization are independent. `NOT_YET_VERIFIED_AT_ANNUAL_GRAIN` is not zero. Medicare calendar-year amounts are not federal-fiscal-year ledger entries. Part D retains partial-dollar coverage throughout; 2024 Part C and D are Jan–Sep only. No extrapolation or imputation.

This candidate was created from the user's three v0.1 seeds and selected reports fetched from GitHub. It has not been checked against the local PostgreSQL database and has not been committed to Git.

- `historical_combined_controls.csv`: FY2018–2019 combined historical RRB/HCV assertions that cannot safely be assigned to individual years from inspected SQL alone.
- `historical_annual_bridge_controls.csv`: ETL-209E verified FY2018–2019 annual HCV/RRB additive and withheld obligation partitions.

HCV FY2018–FY2024 observations represent additive-classified *net obligations*, not proven cash outlays. FY2018–2019 independently reproduced by ETL-209E; FY2020–FY2024 recovered from ETL-184 certified source-control assertions.

- `historical_program_mapping_controls.csv`: live-reproduced FY2018–2019 ETL-221U7 program-mapping scope by accounting disposition; **not** the all-assistance gross total and **not** a separately additive ledger stream.

`historical_current_state_assistance_controls.csv` preserves the user-executed ETL-223A complete FY2018–2019 historical source population by effective accounting disposition. The annual matrix USAspending assistance amounts are gross net obligations (non-additive control totals).


## v0.3.0 unified working extension
Read `UNIFIED_MODEL.md` first. The original v0.2.7 files are retained without rewriting source amounts. The new canonical ledger is an authorization scaffold, **not** a certified fiscal balance.

## Purpose and Governing Principles of the Unified Accounting Registry

### 1. Mission

The Unified Accounting Registry serves as the authoritative, continuously maintained inventory and status reference for the Washington County Federal Fiscal Balance Project (WCFFBP).

Its purpose is to document, organize, and preserve the evidence necessary to construct a transparent, reproducible, and defensible annual accounting of federal fiscal inflows to Washington State and federal fiscal outflows from Washington State.

The registry is intended to provide a succinct, reliable reference for understanding the current state of the project, identifying outstanding work, incorporating new evidence, and ensuring that the database remains complete and internally consistent as it develops.

**The registry documents accounting readiness and disposition; it does not independently authorize the inclusion of any dollar amount in the fiscal ledger.**

### 2. Five Fundamental Questions

The registry must be maintained so that it can answer five questions at any point in the project's development.

**1. What exists?**

Identify every known federal fiscal inflow and outflow family, its constituent streams, relevant data objects, and relationships to other families or streams.

The inventory should distinguish primary accounting sources, allocation sources, supporting evidence, reporting aggregates, and reference-only observations.

**2. What do we know about it?**

Document each stream's source, provenance, geographic coverage, reporting period, measurement basis, limitations, and available validation evidence.

The registry must distinguish observed data from estimates, allocations, derived calculations, and incomplete or provisional observations.

**3. Where does it stand?**

Record the current evidentiary and accounting status of each family, stream, and annual observation.

Relevant milestones include identification, acquisition, database loading, validation, reconciliation, accounting authorization, and ledger incorporation.

These milestones are distinct. Completion of one does not imply completion of another.

**4. What remains to be done?**

Identify missing reporting years, incomplete streams, unresolved overlaps, geographic allocation problems, outstanding validation requirements, and other impediments to accounting completeness.

The registry should make it possible to identify outstanding work without reconstructing the project's history from individual ETL scripts, database queries, or previous research sessions.

**5. What changes when new evidence arrives?**

Identify which existing records, dependencies, calculations, validations, and accounting decisions may be affected when new data, corrected observations, revised methodologies, or additional accounting dimensions are introduced.

A registry update should provide the basis for a structured review of affected components, preserving completeness and consistency across the database.

### 3. Registry Versus Ledger

The registry and the fiscal ledger serve different but complementary purposes.

**The registry is a system of documentation, evidence tracking, and accounting control.**

It records what is known, what has been processed, what has been validated, what has been authorized, and what remains unresolved.

**The ledger is the accounting record of amounts formally authorized for inclusion in the annual fiscal balance.**

A source may be fully acquired and technically validated without being eligible for addition to the ledger.

Likewise, an accounting source may contain valid dollar observations that cannot yet be included because of overlapping coverage, incompatible reporting periods, incomplete geography, uncertain measurement semantics, or unresolved source precedence.

An `INCLUDE_ADDITIVE` program-policy classification is not, by itself, sufficient authorization for an annual ledger amount.

The registry must preserve these distinctions explicitly.

### 4. Unified Registry Architecture

The registry is organized into three connected layers:

| Layer | Function |
|---|---|
| Source-family registry | Defines the universe of known inflow and outflow families, streams, sources, and their relationships. |
| Annual accounting matrix | Tracks annual availability, coverage, measurement characteristics, evidence, validation, and accounting readiness. |
| Canonical annual ledger reference | Tracks proposed and authorized accounting amounts, dispositions, and the evidence supporting ledger inclusion or exclusion. |

These layers represent different views of one coherent accounting model, not independent or competing accounting systems.

Supporting evidence crosswalks, historical controls, reconciliation records, and change logs provide traceability between these layers and the underlying database.

### 5. Accounting Completeness and Change Management

The registry should function as a completeness-control mechanism.

When a new data source, reporting year, payment stream, geographic dimension, methodology, or accounting policy is introduced, the following sequence should guide subsequent work:

1. Identify the affected accounting families and streams.
2. Identify the affected fiscal years and geographic units.
3. Identify dependent database objects, source policies, allocations, and calculations.
4. Determine which existing validations or reconciliations must be repeated.
5. Assess whether existing accounting dispositions or ledger entries are affected.
6. Update the relevant registry records and supporting evidence.
7. Verify that the revised registry remains structurally complete and internally consistent.

Changes should be traceable to their source evidence, methodology, effective reporting period, and applicable validation results.

A newly identified family or stream should not disappear from the registry merely because its data are unavailable or its accounting treatment remains unresolved.

### 6. Essential Data and Status Distinctions

The registry must consistently distinguish:

- **Missing from zero:** Absence of an observation is not evidence of a zero-dollar amount.
- **Available from validated:** Possession of source data does not establish their accuracy or fitness for use.
- **Validated from reconciled:** A technically correct observation may still overlap another accounting source.
- **Reconciled from authorized:** Resolution of source conflicts does not automatically constitute ledger approval.
- **Authorized from ledgered:** An authorized amount should remain distinguishable from an amount actually incorporated into a ledger.
- **Expenditure from obligation:** Federal obligations, outlays, benefit payments, allocations, and reported expenditures are different measurement concepts.
- **Fiscal year from calendar year:** Differences in reporting periods must remain explicit.
- **Statewide from county-attributed:** A valid Washington statewide observation does not necessarily support defensible allocation among Washington's 39 counties.
- **Primary from supporting evidence:** Reporting aggregates and reference controls must not be added to underlying payment streams when doing so would create double counting.

Accounting statuses should reflect documented evidence rather than inferred readiness.

### 7. Canonical Fiscal Balance Definition

For each reporting year \(y\), the Washington State federal fiscal balance is defined as:

\[
B_y = I_y - O_y
\]

Where:

- \(B_y\) is Washington's federal fiscal balance for year \(y\).
- \(I_y\) is the total of authorized federal fiscal inflows reaching Washington's economy during year \(y\).
- \(O_y\) is the total of authorized federal fiscal outflows from Washington to the U.S. federal government during year \(y\), including federal taxation and other qualifying payments.

**A negative balance denotes a negative fiscal-flow outcome for Washington State: federal outflows exceed federal inflows, representing net dollars removed from the economic activity of the state.**

A positive balance denotes net federal inflows exceeding federal outflows.

This sign convention is intrinsic to the project's accounting definition and must be preserved consistently in calculations, reporting, visualizations, documentation, and downstream analytical products.

The fiscal balance measures defined monetary flows. It is not, by itself, a comprehensive measure of economic welfare or the benefits and costs of federal government activity.

### 8. Operational Role and Project Continuity

The unified registry should be among the first resources consulted when beginning or resuming significant WCFFBP work.

It should enable a researcher to determine:

- The current universe of identified accounting components.
- The coverage and status of each component across reporting years.
- The existing database objects and evidence supporting each component.
- The outstanding requirements for advancing incomplete observations.
- The implications of introducing new data or modifying existing accounting methods.

The registry should reduce duplicated investigation, prevent inconsistent treatment of the same source, and preserve project continuity across development sessions.

It should remain sufficiently concise for routine review while providing references to detailed supporting evidence when necessary.

### 9. Scientific and Documentation Principles

The registry shall be maintained according to the following principles:

**Transparency:** Accounting decisions and their supporting evidence must be inspectable.

**Reproducibility:** Reported observations and accounting dispositions must be traceable to documented sources and methods.

**Consistency:** Equivalent data families, reporting periods, and accounting conditions should receive equivalent treatment unless a documented reason supports an exception.

**Completeness:** Known accounting components and outstanding evidence gaps must remain visible.

**Conservatism:** Unresolved amounts should not be authorized merely to produce a more complete-looking fiscal balance.

**Revision traceability:** Changes to source data, methodologies, validation results, and accounting decisions should be recorded without obscuring prior evidence.

**Nonpartisanship:** Accounting inclusion, exclusion, and measurement decisions must be determined by evidence and methodology rather than by the direction or magnitude of the resulting fiscal balance.

**Measure first. Explain later.**