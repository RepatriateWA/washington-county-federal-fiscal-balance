# Assistance Accounting Policy — Execution Evidence

This directory contains preserved execution outputs supporting the Washington
County Federal Fiscal Balance Project (WCFFBP) assistance-accounting methodology.

## Purpose

These files document the analytical progression used to classify federal
assistance transactions and prevent double counting in the statewide federal
inflow ledger.

The outputs include:

- source-universe and materiality profiles;
- overlap and duplication analyses;
- accounting-bridge reconstructions;
- program-family reconciliation;
- residual/unresolved-assistance analysis;
- hard validation and closure assertions; and
- execution evidence associated with accounting-policy decisions.

The corresponding analytical SQL is maintained separately under `etl/sql/`.

## Interpretation of execution output

Many analyses were intentionally designed as read-only diagnostic runs.
Accordingly, output may end with statements such as:

- `NO DATABASE WRITES`
- `NO PERSISTENT DATABASE WRITES`
- `ROLLBACK`

These statements are expected and do not indicate analytical failure.

Some files also contain PowerShell `NativeCommandError` text associated with
PostgreSQL `NOTICE` messages such as a temporary table or schema not existing
before a `DROP` operation. These messages can occur during successful execution.

The relevant indicators of analytical completion are the script's explicit
validation assertions, closure tests, `PASS` notices, and terminal completion
messages.

## Evidentiary role

These outputs are retained as execution evidence rather than as the project's
primary public results.

They should be interpreted together with:

1. the corresponding SQL in `etl/sql/`;
2. persisted accounting-policy and source-policy definitions where applicable;
3. source and validation evidence elsewhere in the repository; and
4. the published statewide reporting layer.

A diagnostic profile does not by itself establish an accounting treatment
unless the associated methodology explicitly makes that determination.

## Reproducibility principle

WCFFBP distinguishes among:

- measurement and profiling;
- overlap/reconciliation evidence;
- accounting-policy decisions; and
- final ledger inclusion.

Preserving these stages separately is intentional. It allows an outside reviewer
to reconstruct not only the resulting accounting treatment, but the evidence
and intermediate reasoning that led to it.

WCFFBP methodology principle:

> Measure first. Explain later.
