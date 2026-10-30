# WCFFBP Provisional Publication Coverage Policy

Status: Working procedural control
Established: ETL-245R
Scope: Statewide provisional balances and graphical publications

## 1. Registry-first principle

The accounting registry is the first-stop inventory and progress
control for WCFFBP.

Every significant new work session begins with:

1. GitHub repository and checkpoint review.
2. Current accounting registry review.
3. Annual evidence and coverage-gap review.
4. Identification of the next material unresolved accounting question.

The registry must preserve visibility of identified payment streams
even when they are absent from the current provisional balance.

## 2. Required pre-publication checks

Before regenerating or publishing provisional balance graphics:

1. Run the structural registry-to-presentation coverage audit.
2. Review every unresolved family and missing annual observation.
3. Identify explicit chart inclusion, reference-only treatment,
   possible aggregate membership, or unresolved treatment.
4. Reconcile annual chart arithmetic and the seven-year totals
   against the designated provisional accounting controls.
5. Preserve source-to-chart lineage and the previous published
   version for comparison.
6. Disclose material unresolved coverage and accounting limitations.

The structural audit is necessary but is not sufficient to
establish numerical or accounting certification.

## 3. Accounting safeguards

An observed amount is not necessarily verified.
A verified amount is not necessarily reconciled.
A reconciled amount is not necessarily ledger-authorized.

Missing observations are not zeros.

Obligations must not silently be represented as cash outlays.

Calendar-year and federal-fiscal-year measures must not be
silently equated.

Overlapping source families must not be double-counted.

Non-additive reporting parents must not be summed with children.

A family absent from an explicit chart column must not
automatically be classified as excluded or duplicated.

## 4. Retirement coverage

Federal military retirement and federal civilian retirement
remain identified, potentially material inflow families.

As of ETL-245R6, neither has verified annual observations
in the FY2018–FY2024 accounting matrix.

Their source acquisition, Washington incidence, payment timing,
overlap treatment, and provisional inclusion decisions remain open.

They must remain visible in publication coverage reporting until
their accounting disposition is supported by evidence.

## 5. Interim provisional publication

An interim provisional publication may proceed with unresolved
families only when the omissions and limitations are explicit.

Provisional presentation inclusion does not constitute canonical
ledger authorization.

Numerical reconciliation and an unresolved-coverage disclosure
must accompany the published graphics.

## 6. Restart checkpoints

Every future restart checkpoint must prominently describe:

- The accounting registry's governing role.
- The latest coverage audit and its findings.
- Material unresolved inflow and outflow families.
- The status of provisional inclusion versus ledger authorization.
- The current publication baseline and next required actions.

The next-session opening prompt must instruct the assistant
to review the registry before proposing new accounting work.

## 7. Implementation

Structural coverage audit:

accounting_registry/validation/build_provisional_coverage_audit.py

The audit currently checks registry/chart structural coverage.
It does not independently certify source lineage, chart arithmetic,
aggregate membership, or accounting authorization.

These limitations must remain explicit until additional
validation controls are implemented.
