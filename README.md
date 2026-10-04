Washington County Federal Fiscal Balance Project

An open, reproducible research project measuring federal dollars flowing into and out of Washington State, with the ultimate objective of calculating the annual federal fiscal balance of each of Washington's 39 counties.
Measure first. Explain later.

The Research Question

How much does Washington send to the federal government, how much does it receive in return, and what is the resulting fiscal balance?

WCFFBP reports the fiscal balance from the perspective of Washington:

Federal Fiscal Balance = Federal Inflows to Washington − Federal Outflows from Washington
For purposes of this accounting:
- Federal inflows are federal expenditures attributable to Washington.
- Federal outflows are federal taxes and other federal receipts attributable to Washington.

Under this convention:
- a positive balance means Washington receives more from the federal government than it sends;
- a negative balance means Washington sends more to the federal government than it receives; and
- a zero balance means measured federal inflows and outflows are equal.

The same convention applies to county-level balances.

The arithmetic is simple. Determining which dollars properly belong on each side of the ledger—without omission, duplication, incompatible timing, or unsupported geographic attribution—is not.

Current Status
DRAFT-1 / active research.

Statewide accounting is substantially developed. County-level fiscal balances remain under development. No final 39-county fiscal-balance dataset has yet been published.
The principal historical research period is federal fiscal years 2015–2024. The current DRAFT-1 statewide accounting is more developed for the recent portion of that period than the complete historical and county-level calculations.

WCFFBP is intended to expand in three directions:
- through time, as additional historical and future fiscal years are incorporated;
- geographically, from statewide controls toward complete accounting for all 39 Washington counties; and
- analytically, as additional sources, stronger reconciliation methods, and better evidence of geographic incidence become available.

DRAFT-1 is therefore a research state, not a claim of finality.

Analytical Framework

WCFFBP deliberately separates six analytical stages:

1. Source measurement — What does the authoritative source report?
2. Source semantics and completeness — What do those values actually mean?
3. Reconciliation and overlap — Does the source duplicate dollars measured elsewhere?
4. Accounting policy — Which source should control a particular fiscal flow?
5. Ledger inclusion — Can the measured amount properly be added to the fiscal balance?
6. Geographic incidence or allocation — Can the amount defensibly be attributed to Washington and, ultimately, to individual counties?

A successful result at one stage does not automatically authorize the next.

Accordingly:
- suppressed or unavailable observations are not silently treated as zero;
- overlapping federal datasets are not automatically added together;
- administrative recipient geography is not assumed to establish economic incidence;
- a source-validation PASS does not automatically authorize ledger inclusion or county allocation; and
- unresolved components remain explicitly unresolved rather than being silently incorporated into the reference calculation.

Scope

WCFFBP measures both directions of Washington's federal fiscal relationship.

Federal Inflows to Washington

Federal expenditures attributable to Washington, including major categories such as benefits, assistance, procurement, federal compensation, veterans' expenditures, and federal health-program expenditures.

Federal Outflows from Washington

Federal taxes and other federal receipts attributable to Washington.
The ultimate geographic scope is all 39 Washington counties, supported by independently reconcilable statewide controls.
Not every federal data series measured by WCFFBP is necessarily additive to the fiscal ledger. Each component must satisfy the applicable reconciliation and accounting requirements before inclusion.

Major Data Sources

WCFFBP currently incorporates or evaluates data from federal sources including:
- Internal Revenue Service (IRS)
- USAspending.gov
- Social Security Administration (SSA)
- U.S. Department of Veterans Affairs (VA)
- Centers for Medicare & Medicaid Services (CMS)
- U.S. Office of Personnel Management (OPM)
- Bureau of Economic Analysis (BEA)
- U.S. Census Bureau
- Office of Management and Budget (OMB)
- U.S. Department of the Treasury
- U.S. Department of Housing and Urban Development (HUD)
- U.S. Department of Labor (DOL)

The project preserves source provenance, acquisition information, validation evidence, and methodological decisions needed to trace material results toward their underlying sources.
WCFFBP does not assume that the present source inventory is exhaustive. Identification of additional authoritative federal sources is an expected part of the continuing research process.

Research Principles

WCFFBP is built around several operating principles.

Traceability. Material published figures should be traceable to supporting source evidence.

Reproducibility. Acquisition, transformation, and calculation should be reproducible wherever source availability permits.

No silent double counting. Overlap among federal programs and datasets must be investigated before amounts are combined.

Geographic conservatism. Administrative geography is not automatically treated as the location of ultimate economic incidence.

Explicit uncertainty. Missing, suppressed, provisional, and unresolved components remain identifiable.

No predetermined result. A source or methodology is evaluated according to the evidence supporting it, not according to whether its inclusion makes Washington's measured balance more positive or more negative.

External balance-of-payments studies may be used for comparison, source discovery, and diagnostic purposes, but WCFFBP results are not calibrated to reproduce an external estimate.

An Open and Versioned Research Project

WCFFBP is intended to be reproduced, challenged, and improved.

The current methodology should not be interpreted as unassailable. Outside review is encouraged, including identification of:
- additional authoritative sources;
- omitted federal fiscal flows;
- possible double counting or overlap;
- alternative source interpretations;
- improved reconciliation methods;
- stronger geographic-incidence evidence; and
- errors in the project's code, data, assumptions, or calculations.

Replication is encouraged.

Proposed improvements should be supported by evidence and, wherever possible, be reproducible. Material changes accepted into WCFFBP will become part of the versioned research record rather than silently replacing earlier results.

The objective is not to produce a particular answer. It is to make the answer progressively harder to dispute.

Reference Calculations and Derivative Work

WCFFBP will identify designated releases and their associated reference methodology.

An official WCFFBP reference calculation is a result produced according to the sources, accounting policies, validation requirements, and methodology specified for that WCFFBP release.
Researchers are free to modify, extend, criticize, and build upon the project. Analyses that materially depart from a released WCFFBP methodology should make those departures clear and should identify the WCFFBP version from which they derive.

A modified analysis may therefore be based on or derived from WCFFBP without being represented as an official WCFFBP reference calculation.

This distinction is intended to preserve provenance, not to discourage alternative analysis.

Evidence and Auditability

This repository intentionally preserves more than final tables.

Depending on the analytical question, the audit trail may include:
- source manifests and retrieval metadata;
- checksums;
- acquisition and ETL code;
- structural and semantic validation;
- reconciliation diagnostics;
- overlap analyses;
- accounting-policy evidence;
- geographic-allocation tests; and
- selected execution output establishing material controls or conclusions.

A PASS in an evidence artifact applies to the specific test documented there. It does not constitute blanket approval of every downstream use of that source.

The intended analytical chain is:
Observed in a source → extracted → reconciled → authorized for the ledger → geographically attributable

Those claims are not interchangeable.

Repository Structure

analysis/ — Registered analyses and analytical work products
data/ — Source, interim, processed, and published data
database/ — Database objects and supporting material
docs/ — Project documentation
etl/ — ETL code, SQL, loaders, and validation logic
evidence/ — Validation, reconciliation, and accounting evidence
notes/ — Methodological and reconciliation notes
scripts/ — Acquisition, profiling, certification, and utility scripts

The analytical code is part of the project's auditable research record and is published to support independent reproduction and review.

Source-Data Preservation

WCFFBP generally uses three approaches to source preservation:

1. Repository-preserved — selected source artifacts and evidence are stored directly when useful and appropriate.
2. Externally reproducible — large authoritative datasets may instead be represented by acquisition information, hashes, manifests, code, and validation evidence when they can be reacquired from their publishers.
3. Citation-only — third-party publications may be represented by citation, retrieval metadata, hashes, extraction methodology, and derived factual evidence rather than redistribution of the original publication.

Third-party data and publications remain subject to the rights and conditions of their original publishers.

Preliminary Results

Preliminary statewide DRAFT-1 accounting evidence is preserved in this repository.

These results are not yet the project's final Washington federal fiscal balance. Known open components and unresolved accounting or geographic questions remain under investigation.
Published WCFFBP fiscal balances will use the Washington-perspective sign convention:

Federal Inflows − Federal Outflows

Historical research artifacts that used another arithmetic presentation remain unchanged as part of the audit record. Published results will state their sign convention explicitly.

A compact published-results layer will provide machine-readable results together with the information necessary to identify the applicable methodology, known limitations, and supporting evidence.

Documentation

The public documentation layer includes or is being developed around:
- DATA_SOURCES.md — source registry and provenance
- METHODOLOGY.md — fiscal-accounting methodology
- DATA_DICTIONARY.md — published data definitions
- REPRODUCIBILITY.md — reproduction instructions
- KNOWN_LIMITATIONS.md — known gaps and unresolved questions
- CONTRIBUTING.md — procedures for proposing corrections and improvements
- CITATION.cff — machine-readable citation information

Detailed evidence remains under evidence/ and alongside the relevant ETL, validation, analysis, and acquisition code.

    License, Attribution, and Third-Party Material

WCFFBP is committed to open research and reproducibility.

The project's licensing, citation, and contribution documentation defines the terms applicable to original WCFFBP code, documentation, and research products. Third-party source data and publications retain their respective rights and are not relicensed merely because they are referenced or analyzed by WCFFBP.

See LICENSE and the project's citation documentation for details.

Washington County Federal Fiscal Balance Project (WCFFBP)
Measure first. Explain later.