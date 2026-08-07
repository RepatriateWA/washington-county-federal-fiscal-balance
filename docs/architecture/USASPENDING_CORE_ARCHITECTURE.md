USAspending Core Architecture

Project: Washington County Federal Fiscal Balance PlatformDocument status: Draft architecture baselinePrimary scope: Shared architecture for USAspending procurement and assistance domainsGuiding principle: Measure first. Explain later.

1. Purpose

This document defines the shared architecture used to ingest, normalize, validate, certify, and publish USAspending data for the Washington County Federal Fiscal Balance Platform.

The architecture is designed to support multiple federal expenditure domains while preserving source provenance, deterministic normalization, auditability, reproducibility, and financial integrity.

The immediate domains are:

Federal procurement contracts

Federal financial assistance

The architecture is also intended to support future expenditure domains that can reuse the same core services, such as Treasury transfers, Social Security, Medicare, Medicaid, and Veterans Affairs expenditures.

This document is both:

an explanation of the current system; and

a design contract for future ETL development.

2. Project Objective

The platform’s long-term objective is to compare, for each of Washington State’s 39 counties:

federal dollars withdrawn through federal taxation; and

federal dollars returned through federal expenditures.

The final analytical metric is a county-level federal fiscal balance:

Federal taxes originating from the county minus federal expenditures attributable to the county

USAspending is one of the principal expenditure sources. Procurement and assistance data are therefore modeled as certified expenditure domains within a larger fiscal-balance platform.

3. Architectural Principles

3.1 Measure first. Explain later.

The platform prioritizes measurement, source fidelity, and reproducibility before interpretation. Analytical narratives must be traceable to certified data.

3.2 Preserve every observed fact

Source observations are not silently overwritten when values change across time or transactions.

Examples include:

recipient changes during an award;

recipient-parent changes;

classification description drift;

reversed performance dates;

agency and subagency variation.

3.3 Deterministic canonicalization

Where the source contains multiple valid observations for one conceptual entity, the platform:

preserves all observations;

selects one canonical representation using an explicit deterministic rule;

records the normalization action; and

records a warning when appropriate.

3.4 No silent data loss

Every normalization decision must either:

preserve the original information; or

explain why the information cannot be preserved.

3.5 Raw data is immutable

Original source files and raw database observations are treated as immutable evidence.

Corrections occur through:

new load batches;

normalized tables;

relationship-history tables;

aliases;

exception records;

migration-controlled schema changes.

3.6 Certification precedes analytical use

A load batch is not considered ready for downstream fiscal analysis until it has passed the applicable certification suite.

Warnings may be permitted where:

the source anomaly is preserved;

the canonical action is deterministic; and

the warning does not invalidate financial or referential integrity.

3.7 Evidence is a first-class output

The output of an ETL is not only normalized tables. It also includes a published evidence package containing:

machine-readable certification results;

metadata;

a manifest;

a human-readable certification report;

hashes and artifact inventory where applicable.

4. Platform Overview

Federal Fiscal Balance Platform
│
├── Shared Core
│   ├── Geography
│   ├── Load batches
│   ├── Raw observation storage
│   ├── Recipients
│   ├── Recipient-parent history
│   ├── Agencies and subagencies
│   ├── Places and geography linkage
│   ├── Normalization exceptions
│   ├── Certification
│   ├── Evidence publication
│   └── Audit metadata
│
├── Procurement Domain
│   ├── Contract awards
│   ├── Contract transactions
│   ├── NAICS
│   ├── PSC
│   ├── Classification aliases
│   ├── Award-recipient history
│   └── Procurement-specific attributes
│
├── Assistance Domain
│   ├── Assistance awards
│   ├── Assistance transactions
│   ├── Assistance listings / CFDA
│   ├── Assistance types
│   ├── Funding opportunities
│   ├── Business-funds indicators
│   ├── Business types
│   └── Assistance-specific financial measures
│
└── Future Expenditure Domains
    ├── Treasury
    ├── Social Security
    ├── Medicare
    ├── Medicaid
    ├── Veterans Affairs
    └── Other federal expenditure sources

5. Shared USAspending Core

5.1 Load batch

Every source ingestion is registered as a load batch.

A load batch records, at minimum:

source file;

load status;

batch identifier;

source row count;

timestamps;

source metadata;

rejection or completion status.

Load batches provide the primary unit of reproducibility, certification, evidence publication, rerun isolation, and auditability.

5.2 Raw observations

Raw source rows are preserved in a landing table as source-aligned observations.

Each row includes:

load_batch_id;

source_row_number;

original raw record;

ingestion metadata.

The pair load_batch_id + source_row_number is the core source-row identity used for reconciliation.

5.3 Recipient dimension

Recipient identity is resolved using this precedence:

UEI;

DUNS;

normalized recipient name only when both identifiers are absent.

A recipient name must not be used to collapse two otherwise identified legal entities.

5.4 Recipient-parent history

Recipient-parent relationships may change over time.

The platform therefore preserves every observed recipient UEI → parent UEI relationship by load batch, including occurrence count, observed parent name, action-date range, and source-row range.

5.5 Agency hierarchy

Top-tier agencies and subagencies share one hierarchical agency dimension.

Source field names must be handled exactly. USAspending uses:

awarding_sub_agency_code

awarding_sub_agency_name

funding_sub_agency_code

funding_sub_agency_name

The underscore form is authoritative.

5.6 Places and geography

Places of performance are normalized into a canonical place dimension.

Canonical identity uses a deterministic, null-aware identity key based on:

country code;

state FIPS;

county FIPS;

city name;

ZIP or ZIP+4.

Transactions link to canonical places through a relationship table.

5.7 Normalization exceptions

Nonfatal anomalies are stored with:

load batch;

entity type and key;

anomaly code;

severity;

source row numbers;

raw values;

normalized action;

explanatory message.

Warnings preserve anomalies with deterministic handling. Errors block reliable normalization.

5.8 Certification framework

Each certification check returns a typed result containing:

check code;

section;

label;

status;

observed and expected values;

detail;

evidence.

Supported statuses are PASS, FAIL, and WARN.

A batch is certified when failed checks equal zero. Warnings do not invalidate certification when the anomaly is preserved and explained.

5.9 Evidence publication

Certified batches are published as versioned evidence packages.

Current package version:

EPS-001

Canonical package path:

evidence/<dataset>/batch_<NNNN>/EPS-001/

Core artifacts include:

manifest.json

certification.json

metadata/metadata.json

certification_report.txt

6. Procurement Domain

6.1 Scope

The procurement domain models USAspending contract prime transactions and their normalized entities.

The first certified production batch is:

PROC-B0005-EPS001

6.2 Core procurement entities

The procurement domain contains:

contract awards;

award transactions;

recipient linkage;

agency and subagency linkage;

canonical place linkage;

NAICS;

PSC;

award-recipient history;

normalization exceptions.

6.3 Award-recipient history

An award may legitimately have multiple observed recipients over time.

All relationships are preserved. The canonical award recipient is selected by:

latest action date;

highest source-row number;

deterministic identifier tie-break.

A warning is recorded when multiple recipient UEIs are observed.

6.4 Classification aliases

NAICS and PSC description drift is preserved through alias tables containing every observed code-description pair, occurrence counts, and source-row ranges.

6.5 Performance-date anomalies

When a source performance end date precedes its start date:

the observation is preserved;

the invalid end date is excluded from canonical aggregation;

a warning is recorded;

no silent correction is made.

6.6 Procurement certification

The current procurement certification suite covers:

batch completeness;

duplicate detection;

referential integrity;

relationship completeness;

normalization provenance;

financial reconciliation.

The certified FY2024 Washington procurement batch passed 37 checks with 0 failures and 1 expected warning.

7. Assistance Domain

7.1 Source profile

The FY2024 Washington Assistance Prime Transactions file contains:

112 columns;

74 exact columns shared with Contracts Prime Transactions;

38 assistance-only columns.

Shared fields include recipients, parents, agencies, subagencies, offices, geography, places, dates, federal action obligations, Treasury accounts, federal accounts, object classes, program activities, and USAspending permalinks.

7.2 Reuse decisions

Component

Decision

Confidence

Notes

Load batch

Reuse

High

Same lifecycle and provenance role

Raw observation model

Reuse

High

Same source-row identity pattern

Recipient dimension

Reuse

High

Same UEI/DUNS identity model

Recipient-parent history

Reuse

High

Same relationship pattern

Agency hierarchy

Reuse

High

Same agency and subagency fields

Place dimension

Reuse

High

Same place concepts

State and county linkage

Reuse

High

Same registries

Normalization exceptions

Reuse

High

Same anomaly contract

Certification engine

Reuse

High

Extend with assistance checks

Evidence publication

Reuse

High

EPS-001 unchanged

NAICS

Not applicable

High

Not present in assistance transactions

PSC

Not applicable

High

Not present in assistance transactions

Procurement award model

Extend

High

Assistance identity differs

Procurement transaction model

Extend

High

Assistance financial fields differ

7.3 Assistance-specific entities

Assistance listing

Source fields:

cfda_number

cfda_title

Assistance type

Source fields:

assistance_type_code

assistance_type_description

Funding opportunity

Source fields:

funding_opportunity_number

funding_opportunity_goals_text

Business-funds indicator

Source fields:

business_funds_indicator_code

business_funds_indicator_description

Business type

Source fields:

business_types_code

business_types_description

7.4 Assistance award identity

Candidate identity fields include:

assistance_award_unique_key

award_id_fain

award_id_uri

sai_number

The authoritative identity hierarchy must be finalized through profiling.

7.5 Assistance financial extensions

The assistance model must distinguish:

transaction obligation;

total award obligation;

total award outlay;

indirect federal share;

nonfederal funding;

loan face value;

loan subsidy cost;

generated pragmatic obligations.

These measures must not be conflated or double counted.

7.6 Assistance certification additions

New checks should cover:

assistance award identity;

transaction uniqueness;

assistance listing references;

assistance type references;

funding opportunity references where populated;

financial reconciliation;

loan measure validity;

nonfederal funding validity;

correction/delete handling;

obligation/outlay distinction.

8. Data Flow

Official source file
        ↓
Immutable original file
        ↓
Registered load batch
        ↓
Raw source observations
        ↓
Domain normalization
        ↓
Shared dimensions and relationships
        ↓
Domain-specific dimensions
        ↓
Validation and certification
        ↓
Evidence package publication
        ↓
Certified analytical tables

9. Transaction Ownership and Idempotency

Loaders own transaction boundaries.

Reusable recorder objects do not commit or roll back; they operate inside the caller’s transaction.

Rerunning a completed batch must not create duplicate:

source rows;

normalized facts;

relationship-history rows;

aliases;

exceptions.

Unchanged canonical values should not be rewritten.

10. Migration Discipline

All schema changes use ordered SQL migrations.

Requirements include:

explicit sequence;

named constraints;

indexes for expected query paths;

comments for non-obvious objects;

no manual production-only schema edits;

information-schema verification;

focused contract tests;

end-to-end reruns;

certification.

11. Validation Strategy

Validation occurs through:

focused contract tests;

loader-level validation;

independent batch certification;

evidence-package acceptance tests.

Publication acceptance verifies filesystem structure, JSON schemas, cross-document consistency, invalid-document rejection, and deterministic package identity.

12. Evidence Package Identity

Evidence package IDs follow:

<DATASET_CODE>-B<BATCH_ID>-EPS001

Example:

PROC-B0005-EPS001

Identity must match across the manifest, certification, metadata, and report.

13. Namespace Strategy

Shared functionality may later move into broader namespaces such as:

etl.common.usaspending
etl.validation.usaspending
etl.normalization.common

This should occur only after the Assistance ETL proves which components are genuinely shared.

14. Repository Structure

data/raw/usaspending/FY2024_WA/
├── original/
├── inventory/
├── profiling/
└── evidence/

etl/
├── common/
├── loaders/
├── sql/
└── validation/
    ├── common/
    ├── procurement/
    └── assistance/

scripts/
├── inspect_*.py
├── normalize_*.py
├── validate_*.py
├── certify_*.py
├── publish_*_evidence.py
└── test_*.py

evidence/
└── procurement/
    └── batch_0005/
        └── EPS-001/

docs/
└── architecture/
    ├── USASPENDING_CORE_ARCHITECTURE.md
    └── ETL-005A_REUSE_MATRIX.md

15. Current Certified Baseline

Evidence package:

PROC-B0005-EPS001

Certification result:

Passed:   37
Failed:    0
Warnings:  1
Status: CERTIFIED

The warning reflects preserved award-recipient history and does not represent data loss or financial inconsistency.

16. Next Implementation Steps

ETL-005A — Assistance Architecture

Complete profiling.

Finalize the reuse matrix.

Define assistance award identity.

Define assistance transaction identity.

Define assistance-specific dimensions.

Define financial semantics.

Define certification checks.

ETL-005B — Assistance Raw Ingestion

Create assistance schema.

Create the raw table.

Build the loader.

Reconcile source rows.

Register source hash and metadata.

ETL-005C — Assistance Normalization

Normalize awards.

Normalize transactions.

Reuse recipients and parent history.

Reuse agencies and places.

Normalize listings, types, and opportunities.

Record exceptions and aliases.

ETL-005D — Assistance Certification and Publication

Add assistance certification modules.

Certify the completed batch.

Publish EPS-001 evidence.

Validate the package.

Commit and tag the release.

17. Open Design Questions

What is the authoritative assistance award identity hierarchy?

Can one award contain multiple FAIN or URI observations?

How should correction/delete indicators affect canonical transactions?

How often do assistance listing titles drift?

Should funding opportunities be dimensions or award attributes?

Are business type codes single-valued or multi-valued?

How should loan face value and subsidy cost contribute to expenditure reporting?

Which measure is appropriate for county-level allocation?

How should outlays and obligations be presented without double counting?

Which recipient and place fields differ materially from procurement?

No implementation should silently answer these questions without profiling evidence.

18. Closing Principle

The architecture exists to make every published fiscal number explainable from source to result.

Preserve the evidence.Normalize deterministically.Validate independently.Certify before analysis.Publish the audit trail.