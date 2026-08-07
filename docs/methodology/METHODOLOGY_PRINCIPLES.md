# METHODOLOGY PRINCIPLES

## Washington County Federal Fiscal Balance Project

Version: 1.0

Status: Foundational Principle

---

# Purpose

The Washington County Federal Fiscal Balance Project exists to construct a scientifically defensible, transparent, and reproducible accounting of the flow of federal dollars into and out of Washington State.

The project does not begin with policy conclusions.

The project begins with methodology.

Every analytical product, evidence package, database table, visualization, and published report derives its credibility from the methodology used to construct it.

Accordingly, methodology is regarded as the highest governing principle of the project.

---

# Methodology Is Primary

The purpose of this project is not to persuade.

The purpose of this project is to measure.

Public policy debates should be informed by accurate measurements rather than assumptions, anecdotes, or incomplete information.

The project therefore seeks to establish a methodology that any independent researcher can evaluate, reproduce, and improve.

Conclusions are products of the methodology.

They are never inputs to it.

---

# Scientific Philosophy

The project adopts a scientific rather than rhetorical approach to public finance.

Accordingly,

Questions precede conclusions.

Evidence precedes interpretation.

Measurement precedes explanation.

When new evidence becomes available, the methodology is refined and analytical conclusions are allowed to change accordingly.

No conclusion is considered permanent.

The methodology, however, should continually improve.

---

# Fundamental Principles

## Principle 1

Measure First. Explain Later.

No analytical conclusion should be reached before the underlying measurements have been validated.

Measurement is the objective.

Explanation is the consequence.

---

## Principle 2

Methodology Before Interpretation.

Interpretation must never influence data collection, normalization, classification, or reconciliation.

Analytical results should emerge naturally from the data.

---

## Principle 3

Preserve Evidence.

Information should never be discarded merely because it is presently difficult to classify.

Unknown observations remain evidence.

Multiple identities remain evidence.

Conflicting observations remain evidence.

Future improvements frequently originate from today's unresolved observations.

---

## Principle 4

Immutable Source Data.

Federal source files are historical records.

They are never modified.

All transformation occurs inside normalized warehouse tables.

The original federal publication remains permanently available for verification.

---

## Principle 5

Deterministic Processing.

Identical source data shall always produce identical warehouse contents.

Every ETL process should be repeatable.

Repeated execution should converge toward:

Inserted ............ 0

Updated ............. 0

Unchanged ........... all

Validation .......... PASS

---

## Principle 6

Transparency.

Every transformation should be understandable.

Every classification should be documented.

Every assumption should be explicit.

Every analytical product should explain how it was constructed.

---

## Principle 7

Reproducibility.

Independent researchers should be capable of reproducing every published figure using:

the published methodology

the original federal source data

the warehouse architecture

the documented ETL process

the accompanying evidence packages

Reproducibility is the primary test of credibility.

---

## Principle 8

Evidence Before Authority.

Published reports, articles, and summaries are valuable.

Whenever possible, however, analytical conclusions should derive directly from authoritative source data rather than secondary interpretations.

Primary evidence is preferred over secondary description.

---

## Principle 9

Internal Reconciliation.

Every analytical result should reconcile internally.

Totals should equal subtotals.

Relationships should reconcile with observations.

Evidence should reconcile with warehouse contents.

Validation is considered complete only after reconciliation succeeds.

---

## Principle 10

Continuous Improvement.

Methodology is never considered finished.

New federal datasets.

Improved normalization.

Better classifications.

Additional validation.

Improved documentation.

All represent progress.

Improving methodology is considered a permanent responsibility.

---

# Architecture Follows Methodology

Database architecture exists to support methodology.

Warehouse normalization exists to support methodology.

Evidence packages exist to support methodology.

Validation exists to support methodology.

Visualization exists to communicate methodology.

Technology is therefore subordinate to methodology.

---

# Treatment of Uncertainty

Uncertainty is not failure.

Unknown classifications.

Incomplete geography.

Changing recipient identities.

Agency reorganizations.

Extraordinary funding classifications.

These represent information requiring further investigation rather than information requiring deletion.

Whenever uncertainty exists, the project preserves evidence rather than making unsupported assumptions.

---

# Validation Philosophy

Validation is performed continuously rather than only at project completion.

Every major ETL process should verify:

identity consistency

referential integrity

duplicate detection

relationship consistency

count reconciliation

warehouse integrity

Evidence generation

Only after validation succeeds should analytical products be published.

---

# Analytical Philosophy

The objective of this project is to establish measurements that are worthy of public confidence.

Policy conclusions belong to readers.

The responsibility of this project is considerably narrower.

The project is responsible for ensuring that published measurements faithfully represent the underlying federal data.

---

# Reproducible Research

Every published analytical report should identify:

Repository version

Architecture baseline

Git commit

Source datasets

Load batches

Warehouse version

Evidence packages

Validation status

Methodology version

An independent researcher should possess sufficient information to reproduce every published result.

---

# Long-Term Vision

The Washington County Federal Fiscal Balance Project begins with Washington State.

Its methodology is intentionally designed to be geographically independent.

Future applications may include:

additional states

additional federal spending domains

additional federal revenue sources

historical comparisons

national analyses

The methodology should remain applicable regardless of geographic scope.

---

# Project Motto

Measure First.

Explain Later.

---

# Professional Standard

This project strives to satisfy a simple professional standard:

If another researcher repeats the work using the same source data and the documented methodology, they should obtain substantially the same results.

If they do not, either the methodology or its implementation requires improvement.

The project welcomes such scrutiny.

Scientific progress depends upon it.

---

# Closing Statement

The Washington County Federal Fiscal Balance Project is founded upon a single guiding belief:

Reliable public discussion begins with reliable measurement.

Accordingly, this project places methodology above advocacy, evidence above assertion, reproducibility above convenience, and scientific integrity above predetermined conclusions.

Every improvement to the methodology improves every future conclusion.

For that reason:

**Methodology is primary.**