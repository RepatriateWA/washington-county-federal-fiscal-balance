# Washington County Federal Fiscal Balance Platform
## Architecture Baseline 2.0

**Status:** Active Baseline  
**Date:** 2026-08-05  
**Supersedes:** `ARCHITECTURE_BASELINE_1.0.md`

---

# 1. Purpose

This document records the architecture of the Washington County Federal Fiscal Balance Platform at the point when both the Procurement and Assistance USAspending domains had reached structurally complete, normalized warehouse states.

Architecture Baseline 2.0 is intended to provide future contributors with a clear account of:

- what the platform currently contains;
- how its principal layers interact;
- which architectural principles govern the system;
- which components are complete;
- which components remain under development;
- and how the platform is expected to evolve.

This document is an architectural snapshot, not a substitute for source code, schema migrations, certification reports, evidence packages, or Architecture Decision Records.

---

# 2. Project Objective

The long-term objective of the platform is to measure the balance between:

- federal dollars withdrawn from Washington State through federal taxation; and
- federal dollars expended into Washington State through federal programs.

The ultimate analytical target is a county-level federal fiscal balance for all 39 Washington counties.

The platform is designed to support a broader public-facing product:

> **Washington Federal Fiscal Flow Dashboard**

The dashboard is expected to present transparent, reproducible, and evidence-backed measurements of federal fiscal flows into and out of Washington State.

---

# 3. Guiding Principles

The platform is governed by the following principles.

## 3.1 Measure first. Explain later.

The system is designed to produce trustworthy measurements before interpreting their meaning.

## 3.2 Preserve raw evidence

Source observations are retained in immutable raw tables before normalization.

## 3.3 Separate observation from interpretation

Raw source values, normalized entities, relationships, classifications, and analytical conclusions are stored as distinct layers.

## 3.4 Preserve history

The platform does not overwrite competing or changing observations when those differences are analytically meaningful.

## 3.5 Deterministic normalization

Canonical values are selected using documented, reproducible precedence rules.

## 3.6 Exact financial representation

Financial values are stored using exact numeric types rather than binary floating-point values.

## 3.7 Certification before publication

A dataset is not considered publishable merely because an ETL completed successfully.

Certification must independently validate completeness, reconciliation, referential integrity, financial preservation, and normalization provenance.

## 3.8 Evidence-backed classification

Interpretive reference domains, including extraordinary-funding classifications, must be supported by authoritative citations.

## 3.9 Idempotent processing

Re-running a completed loader against the same inputs should produce no unintended changes.

## 3.10 Open reasoning

Future contributors should be able to understand not only what the platform does, but why it was designed that way.

---

# 4. Architectural Layers

The platform is organized into the following conceptual layers.

```text
Public Source Data
        ↓
Immutable Raw Observations
        ↓
Canonical Reference and Dimension Tables
        ↓
Canonical Awards
        ↓
Immutable Transactions
        ↓
Relationship Enrichment
        ↓
Classification and Analytical Layers
        ↓
Certification
        ↓
Evidence Publication
        ↓
Dashboard and Public Data Products

5. Database Schemas

The PostgreSQL database currently contains several principal schemas.

5.1 reference

The reference schema contains reusable geographic and analytical reference domains.

Current examples include:

reference.state_registry
reference.county_registry
reference.extraordinary_funding_code

The geographic registries provide stable state and county identifiers.

The extraordinary-funding table provides citation-backed classifications for Disaster Emergency Fund Codes.

5.2 irs

The irs schema contains normalized Internal Revenue Service Statistics of Income data.

The first completed IRS domain is the Washington 2015 county-level SOI dataset.

5.3 procurement

The procurement schema contains the normalized USAspending Procurement subsystem.

It currently also contains several entities that function as shared USAspending dimensions:

procurement.load_batch
procurement.recipient
procurement.agency
procurement.place

These tables were initially created during Procurement development but are reused by Assistance.

Their current schema placement is recognized as a namespace limitation. They are treated architecturally as shared USAspending entities even though they remain physically located in the procurement schema.

5.4 assistance

The assistance schema contains normalized USAspending Assistance awards and transactions.

Current core tables include:

assistance.raw_award_transaction
assistance.assistance_listing
assistance.assistance_type
assistance.funding_opportunity
assistance.award
assistance.award_transaction
assistance.award_transaction_defc
6. Shared USAspending Core

Procurement and Assistance reuse a common architectural foundation.

The shared core currently includes:

load-batch provenance;
canonical recipients;
canonical agencies and subagencies;
canonical places;
raw source preservation;
canonical award identities;
immutable transaction ledgers;
normalization evidence;
certification patterns;
and evidence-package publication.

The shared entities currently reside under the procurement schema because Procurement was the first USAspending domain implemented.

Assistance references those entities through foreign keys rather than duplicating them.

This decision validated the architectural hypothesis that new USAspending domains can be added by extending the platform rather than rebuilding the same infrastructure.

7. Procurement Domain Status

The Procurement domain is the first fully normalized and certified USAspending expenditure domain.

7.1 Source batch

The certified FY2024 Washington Procurement batch is:

load_batch_id = 5
7.2 Certified counts

The certified Procurement batch contains:

Raw observations                  120,813
Normalized transactions           120,813
Canonical awards                  111,083
Award-recipient relationships     111,089
Recipient-parent relationships      5,031
7.3 Certification

The Procurement certification framework validates:

raw and normalized row counts;
award representation;
duplicate detection;
referential integrity;
recipient completeness;
agency and subagency completeness;
place relationships;
NAICS and PSC references;
recipient-history relationships;
normalization provenance;
financial reconciliation;
negative obligations;
zero-dollar transactions;
and exact monetary precision.

The certified batch passed all required checks.

A small number of recipient-history warnings were preserved because several awards contained more than one observed recipient UEI.

Those warnings did not invalidate the batch because the competing observations were preserved and the canonical recipient was selected deterministically.

7.4 Evidence publication

The Procurement evidence package was published as:

Evidence Package ID: PROC-B0005-EPS001

The package includes:

manifest.json
certification.json
metadata/metadata.json
certification_report.txt

The package passed schema validation, cross-document consistency validation, and filesystem-structure validation.

8. Assistance Domain Status

The Assistance subsystem is the second major USAspending expenditure domain.

Its successful implementation demonstrates that the Procurement architecture is reusable.

8.1 Source batch

The FY2024 Washington Assistance raw source was loaded as:

load_batch_id = 6

The source file SHA-256 is:

dba62c9f04983d05c86692c4994fdf662dd22fc4eea8cd9a0b6bf69867c6c5b9
8.2 Raw observations

The raw Assistance landing table contains:

74,116 source observations
74,116 preserved raw JSONB records
0 rejected rows

Each source row retains:

load batch;
source-row number;
Assistance transaction key;
Assistance award key;
complete raw source record;
and creation timestamp.
8.3 Award identity

Assistance profiling established:

74,116 unique transaction keys
55,983 distinct assistance award keys

The canonical source award identity is:

assistance_award_unique_key

FAIN and URI are preserved as optional business identifiers.

No observed award lacked both a FAIN and a URI.

SAI values are not used as award identities because the source field largely contains status-like values such as exempt or unavailable.

8.4 Assistance-native dimensions

The following dimensions have been normalized:

Assistance Listings             1,057
Assistance Types                   11
Funding Opportunities           3,097

Normalization results include:

Assistance Listing title conflicts       16
Assistance Type description conflicts     0
Funding Opportunity goal conflicts      253

All conflicts are preserved in normalization evidence artifacts.

8.5 Canonical awards

The canonical Assistance award table contains:

55,983 awards

Each canonical award may contain:

Assistance award key;
FAIN;
URI;
SAI source value;
Assistance Listing;
Assistance Type;
Funding Opportunity;
performance dates;
cumulative award amounts;
canonical recipient name;
canonical award description;
first action date;
and last action date.

Award normalization is idempotent.

8.6 Immutable transaction ledger

The Assistance transaction ledger contains:

74,116 normalized transactions

The ledger passed the following acceptance checks:

Duplicate transaction keys             0
Orphan award references                0
Blank transaction identities           0
Cross-batch identity conflicts         0
Immutable ledger conflicts             0

The second run produced:

Transactions inserted                  0
Transactions unchanged            74,116

This confirms full idempotency.

The Assistance warehouse is therefore structurally complete.

9. Assistance Transaction Ledger

The Assistance transaction ledger is designed as an immutable accounting record.

Each transaction preserves:

transaction identity;
load-batch provenance;
source-row provenance;
award relationship;
modification number;
action date;
fiscal year;
federal action obligation;
cumulative award obligation;
cumulative award outlay;
indirect-cost amount;
non-federal funding values;
loan values;
COVID overall-award values;
IIJA overall-award values;
raw DEFC value;
Assistance Listing;
Assistance Type;
Funding Opportunity;
transaction description;
action code;
record type;
correction/delete indicator;
USAspending permalink;
initial report date;
and last-modified date.

The ledger does not decide whether a transaction should be included in an analysis.

It records what USAspending reported.

Classification and analytical inclusion occur downstream.

10. Fact and Enrichment Separation

The platform separates normalized financial facts from relationship enrichment.

10.1 Fact layer

The fact layer answers:

What financial event did the source report?

It contains:

transaction identity;
financial amounts;
dates;
award relationship;
source metadata;
and raw classification fields.
10.2 Enrichment layer

The enrichment layer answers:

How does this transaction relate to canonical recipients, agencies, places, and classifications?

Enrichment is intentionally separate so that matching logic can improve without rewriting financial facts.

Current Assistance enrichment targets include:

recipient relationships;
recipient-parent relationships;
awarding agency;
awarding subagency;
funding agency;
funding subagency;
place of performance;
DEFC relationships;
and extraordinary-funding classifications.
11. Extraordinary Funding Framework

The platform treats extraordinary funding as a first-class analytical domain.

Current initial funding families include:

COVID
IIJA
OTHER_DISASTER
WILDFIRE_SUPPRESSION
OTHER_EMERGENCY
NOT_DESIGNATED
UNSPECIFIED_NON_COVID
ORDINARY
UNRESOLVED
11.1 DEFC inventory

The FY2024 Assistance source contained:

38 distinct parsed DEFC codes
0 unparsed segments
11.2 Reference classifications

The first citation-backed reference seed includes:

COVID: L, M, N, O, P, U, V
IIJA:  1, Z
Not designated: Q
Unspecified non-COVID: 9

The reference data are stored in:

reference.extraordinary_funding_code

and loaded from:

data/reference/extraordinary_funding/defc_classification.csv

The loader is idempotent.

11.3 Parser

The reusable DEFC parser supports:

semicolon-delimited codes;
pipe-delimited code groups;
embedded pipes inside descriptions;
duplicate-code suppression;
malformed-segment preservation;
and null or blank inputs.

The parser is protected by a contract test.

11.4 Transaction-to-DEFC bridge

The normalized relationship table is:

assistance.award_transaction_defc

It supports zero, one, or multiple DEFC observations per transaction.

The bridge preserves:

transaction relationship;
reference-code relationship;
observed description;
and complete raw DEFC source value.
11.5 Measurement constraint

Annual fiscal flows must not be inferred by assigning every transaction on a COVID-tagged award to COVID.

Award-level COVID and IIJA fields describe overall-award amounts.

They are useful for:

award classification;
reconciliation;
validation;
and cumulative award analysis.

They are not, by themselves, transaction-level annual-flow measures.

The exact methodology for annual extraordinary-funding flows must respect the reporting grain of the authoritative source data.

12. Normalization Framework

A shared normalization core has been introduced under:

etl/common/normalization/

Current reusable components include:

text.py
canonical.py

The framework provides:

optional text cleaning;
conservative comparison normalization;
deterministic canonical selection;
complete candidate preservation;
and empty-selection rejection.

The normalization core is protected by a contract test.

Existing Assistance Listing and Assistance Type loaders have not yet been refactored to use the shared framework.

The Funding Opportunity loader is the first production loader to use it.

13. Evidence Architecture

The platform produces multiple kinds of evidence artifacts.

13.1 Raw evidence

Raw source rows are preserved in PostgreSQL with batch and source-row provenance.

13.2 Normalization evidence

Assistance normalization outputs are stored under:

evidence/assistance/batch_0006/normalization/

Current evidence areas include:

assistance_listings
assistance_types
funding_opportunities

Each area includes some combination of:

canonical inventory;
conflict inventory;
and normalization summary.
13.3 Certification evidence

Certification evidence packages are structured publication artifacts containing:

manifest;
certification results;
metadata;
human-readable reports;
hashes;
and cross-document identifiers.

The Procurement evidence-package implementation provides the model for Assistance.

14. Current Architectural Boundaries

Several boundaries are intentional.

14.1 Raw versus normalized

Raw observations are immutable.

Normalized entities may evolve when deterministic canonical logic improves.

14.2 Facts versus relationships

Financial facts are loaded before recipients, agencies, places, and classifications are enriched.

14.3 Source values versus classifications

Raw DEFC strings are preserved independently from parsed and classified DEFC relationships.

14.4 Award identity versus business identifiers

The Assistance award key is authoritative for source identity.

FAIN, URI, and SAI remain descriptive source attributes.

14.5 Annual flows versus cumulative award values

Transaction financial actions and cumulative award totals are not interchangeable.

Each must be used only at its correct analytical grain.

15. Known Architectural Debt

The following issues are known and intentionally deferred.

15.1 Shared entities remain under procurement

The following tables serve both Procurement and Assistance but remain physically located in the procurement schema:

procurement.load_batch
procurement.recipient
procurement.agency
procurement.place

A future migration may move or expose them under a neutral shared schema.

This refactor should not occur until all dependent pipelines and certifications can be migrated safely.

15.2 Partial DEFC reference coverage

The database currently contains 11 citation-backed DEFC classifications out of 38 observed codes.

The remaining codes require authoritative research and citation before production classification.

15.3 Assistance relationships remain incomplete

Assistance award and transaction records currently do not yet contain complete recipient, agency, place, or DEFC relationships.

15.4 Assistance certification not yet implemented

The Assistance equivalent of Procurement ETL-114 remains to be built.

15.5 Assistance evidence package not yet published

The Assistance evidence-package publication layer remains pending.

15.6 Multi-year Assistance data not yet loaded

The current Assistance subsystem contains FY2024 Washington data only.

Historical annual datasets are required to produce the planned COVID and ordinary-flow time series.

16. Current Validation and Test Assets

The platform currently includes contract and acceptance tests for:

award-recipient relationship recording;
evidence-package acceptance;
DEFC parsing;
normalization core behavior;
Procurement certification;
publication validation;
and evidence publication.

Additional Assistance-specific tests will be added during enrichment and certification.

17. Next Phase

The next phase is:

ETL-005D — Assistance Relationship Enrichment

Planned work includes:

normalize and link Assistance recipient observations;
preserve Assistance recipient history;
normalize and link awarding agencies and subagencies;
normalize and link funding agencies and subagencies;
link places of performance;
parse raw DEFC observations;
populate assistance.award_transaction_defc;
classify known extraordinary-funding relationships;
validate unresolved relationships;
build Assistance certification checks;
publish the Assistance evidence package.
18. Near-Term Analytical Product

Once Assistance enrichment and certification are complete, the platform will support an initial statewide proof of principle combining:

Procurement obligations;
Assistance obligations;
selected other federal expenditure domains as available;
IRS or other federal receipt measures;
ordinary versus extraordinary funding;
and documented coverage limitations.

The initial public-facing product is expected to be:

Washington Federal Fiscal Flow Dashboard — Proof of Principle

This product will not represent the final county-level fiscal balance.

It will demonstrate the platform’s ability to produce transparent, reproducible, evidence-backed statewide fiscal-flow measurements.

19. Long-Term Roadmap

The long-term roadmap includes:

Procurement
Assistance
Social Security
Medicare and CMS
Veterans Affairs
Treasury programs
Other federal expenditure domains
IRS federal receipts
County allocation methods
Statewide balance
County-level balance
Public dashboard
Open-source publication

The final target remains:

Federal taxes attributed to each Washington county
minus
Federal expenditures attributed to each Washington county
20. Historical Significance of Baseline 2.0

Architecture Baseline 1.0 documented the platform’s initial warehouse vision.

Architecture Baseline 2.0 records the point at which that vision became operational across two USAspending domains.

At this baseline:

Procurement is certified and published as evidence;
Assistance has reached structural warehouse completion;
the shared USAspending architecture has been validated;
immutable raw and transaction layers are established;
canonical award patterns are reused;
normalization evidence is standard practice;
extraordinary funding has become a citation-backed reference domain;
and the platform has begun transitioning from infrastructure construction to fiscal measurement.

The principal architectural conclusion of Baseline 2.0 is:

The project is no longer a collection of ETL pipelines.
It is a reusable federal fiscal measurement platform.

21. Related Documents
docs/architecture/ARCHITECTURE_BASELINE_1.0.md
docs/architecture/USASPENDING_CORE_ARCHITECTURE.md
docs/architecture/adr-001-federal-expenditure-warehouse.md
docs/architecture/adr-002-social-security-source.md
docs/architecture/adr-003-federal-expenditure-phase.md
docs/architecture/adr-004-expenditure-data-model.md
docs/architecture/adr-005-warehouse-dimensional-model.md
docs/architecture/adr-006-cms-expenditure-subsystem.md
docs/architecture/adr-007-extraordinary-funding-classification.md
docs/research/DEFC_CLASSIFICATION.md
22. Baseline Declaration

Architecture Baseline 2.0 is declared active as of 2026-08-05.

Future architectural changes should be documented through:

schema migrations;
Architecture Decision Records;
updated architecture documentation;
certification changes;
and historical milestone records where appropriate.

One filename correction should be made before saving: your extraordinary-funding ADR was renamed to `adr-007-extr