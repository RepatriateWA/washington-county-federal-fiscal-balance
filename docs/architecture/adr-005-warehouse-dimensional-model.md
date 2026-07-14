# ADR-005: Warehouse Dimensional Model

**Status:** Accepted

**Date:** 2026-07-14

## Context

The Washington County Federal Fiscal Balance project now contains production-quality revenue and expenditure fact tables.

Current fact tables include:

- `irs.county_income_tax`
- `irs.state_collections`
- `ssa.benefit_payments`

Future fact tables are expected from:

- Centers for Medicare & Medicaid Services
- Department of Veterans Affairs
- USAspending.gov
- Office of Personnel Management
- Additional federal agencies

A shared dimensional model is needed so that these fact tables use consistent agency, program, geography, and time definitions.

## Decision

The warehouse will distinguish between:

### Fact tables

Fact tables store measurable events or amounts, including:

- federal collections
- tax liabilities
- benefit payments
- grants
- contracts
- payroll
- medical expenditures

### Dimension tables

Dimension tables provide stable reference values used across fact tables, including:

- states
- counties
- federal agencies
- federal programs
- years
- expenditure categories

## Core Dimensions

The project will maintain these shared dimensions:

```text
reference.state_registry
reference.county_registry
reference.federal_agency
reference.federal_program
reference.calendar_year