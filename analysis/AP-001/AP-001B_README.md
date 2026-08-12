# AP-001B — Washington Transaction Attribution

## Washington County Federal Fiscal Balance Project

---

# Purpose

AP-001B establishes the certified analytical universe of USAspending Assistance transactions attributable to Washington State.

It builds directly upon the AP-001A Certified Assistance Analytical Ledger and assigns every certified Assistance transaction to exactly one geographic attribution class.

The objective is not simply to identify transactions associated with Washington.

The objective is to create a transparent, reproducible, and auditable attribution framework that preserves uncertainty and explicitly distinguishes:

* confidently county-resolved Washington transactions;
* Washington transactions lacking county-level precision;
* conflicting source geography;
* non-Washington transactions.

AP-001B does not alter warehouse data.

It creates analytical views derived from certified transaction-level records.

---

# Governing Principle

> **Preserve uncertainty rather than manufacture precision.**

Geographic attribution shall be based only upon information supported by certified source and reference data.

A transaction shall never be assigned to a county solely to force complete geographic coverage.

---

# Dependency

AP-001B depends upon:

```text
analysis.v_certified_assistance_ledger
```

created and certified under AP-001A.

AP-001B shall not query raw USAspending tables directly for analytical measurements except when performing documented diagnostic or validation work.

---

# Certified Source Universe

The AP-001A certified Assistance ledger currently contains:

* 1,025,644 canonical Assistance transactions;
* fiscal years FY2020 through FY2025;
* $422,228,719,171.09 in federal action obligations;
* zero transaction-row reconciliation difference;
* zero obligation reconciliation difference;
* zero duplicate transaction identities.

These values constitute the certified source universe against which AP-001B attribution must reconcile.

---

# Attribution Classes

Every certified Assistance transaction shall be assigned to exactly one of the following mutually exclusive classes.

## WA_COUNTY

The transaction is attributable to Washington State and has a valid Washington county assignment supported by the canonical place-of-performance geography and county reference data.

Requirements:

* Washington state identity is confirmed;
* county identity resolves to `reference.county_registry`;
* no geography-conflict condition applies.

These transactions are eligible for county-level aggregation.

---

## WA_UNSPECIFIED

The transaction is attributable to Washington State, but the source data do not support a defensible county assignment.

These records remain part of Washington statewide totals but shall not be assigned to any Washington county.

The existing source condition:

```text
WASHINGTON_UNSPECIFIED
```

is an example of this class.

These transactions must remain separately visible in county reconciliation outputs.

---

## GEOGRAPHY_CONFLICT

The transaction contains internally contradictory geographic information that prevents confident Washington attribution.

An example is documented in:

```text
DQ-001 — Lewiston Geography Conflict
```

where source records contain:

* Washington state code and FIPS;
* Lewiston city;
* ZIP Code 83501.

These records remain in the certified national ledger but are excluded from ordinary Washington county attribution.

They shall be separately reportable as data-quality exceptions.

---

## NON_WASHINGTON

The transaction does not meet the certified criteria for Washington attribution.

These transactions remain part of the national certified Assistance ledger but are excluded from Washington analytical views.

---

# Attribution Invariant

The four attribution classes must be mutually exclusive and collectively exhaustive.

Therefore:

```text
WA_COUNTY
+ WA_UNSPECIFIED
+ GEOGRAPHY_CONFLICT
+ NON_WASHINGTON
=
Total Certified Assistance Transactions
```

For the current certified ledger:

```text
Total Certified Assistance Transactions = 1,025,644
```

Any deviation from this identity constitutes a validation failure.

---

# Financial Reconciliation Invariant

Federal action obligations must reconcile across attribution classes.

Therefore:

```text
WA_COUNTY obligations
+ WA_UNSPECIFIED obligations
+ GEOGRAPHY_CONFLICT obligations
+ NON_WASHINGTON obligations
=
Certified National Assistance Obligations
```

Current certified national Assistance obligations:

```text
$422,228,719,171.09
```

The attribution process must introduce no financial difference.

---

# Primary Views

AP-001B will produce the following certified analytical views.

## Transaction Attribution View

```text
analysis.v_assistance_geographic_attribution
```

Purpose:

Assign every AP-001A transaction to exactly one geographic attribution class.

This remains a national view.

One row remains one transaction.

---

## Washington Transaction View

```text
analysis.v_wa_transactions
```

Purpose:

Expose the certified Washington transaction universe.

This view shall include:

* WA_COUNTY;
* WA_UNSPECIFIED.

GEOGRAPHY_CONFLICT records shall be separately exposed and shall not silently enter ordinary Washington measurements.

---

## Washington Geography Conflict View

```text
analysis.v_wa_geography_conflicts
```

Purpose:

Preserve and expose transactions whose source geography contains documented conflicts relevant to Washington attribution.

---

## Washington County Transaction View

```text
analysis.v_wa_county_transactions
```

Purpose:

Expose only transactions certified as `WA_COUNTY`.

This becomes the authoritative transaction-level input for county aggregations.

---

# Planned Aggregate Views

Once transaction attribution is certified, AP-001B may produce:

```text
analysis.v_wa_county_obligations
analysis.v_wa_county_extraordinary_funding
analysis.v_wa_county_covid
analysis.v_wa_county_covid_excluded
analysis.v_wa_county_iija
```

No aggregate view shall be certified until its transaction-level source view has passed reconciliation.

---

# County Reconciliation

County totals must never be presented as equivalent to statewide Washington totals without also accounting for transactions classified as `WA_UNSPECIFIED`.

The required reconciliation is:

```text
Sum of Washington County Transactions
+ Washington Unspecified
=
Certified Washington Attributed Total
```

Geography-conflict transactions shall be disclosed separately.

This prevents artificial county allocation of statewide or geographically incomplete records.

---

# Extraordinary Funding Treatment

AP-001B inherits the certified DEFC classifications established under ETL-005 and RP-002.

Transactions may therefore be analyzed by:

* COVID;
* IIJA;
* Other Disaster;
* Other Emergency;
* Wildfire Suppression;
* other certified extraordinary-funding families.

COVID classification shall remain DEFC-based.

Public Law alone shall not be treated as sufficient evidence of COVID classification.

---

# Certified Fiscal Measure

The principal transaction-level fiscal-flow measure is:

```text
federal_action_obligation
```

Cumulative overall-award fields such as:

```text
covid_overall_award_obligation
covid_overall_award_outlay
iija_overall_award_obligation
iija_overall_award_outlay
```

shall not be substituted for transaction-level annual fiscal-flow measurement.

They may be used for reconciliation, classification support, or diagnostic work when explicitly documented.

---

# Data Quality Policy

Data-quality anomalies discovered during AP-001B shall not be silently corrected.

Material or methodologically significant findings shall be documented using the project's DQ evidence series.

Existing example:

```text
DQ-001 — Lewiston Geography Conflict
```

Future findings shall be documented as:

```text
DQ-002
DQ-003
...
```

as needed.

---

# Validation Requirements

AP-001B shall not be certified until the following tests pass.

## Transaction Coverage

Every AP-001A transaction appears exactly once in the attribution view.

Expected:

```text
1,025,644 source transactions
1,025,644 attributed transactions
difference = 0
```

---

## Attribution Exclusivity

No transaction belongs to more than one attribution class.

Expected:

```text
duplicate attribution assignments = 0
```

---

## Attribution Completeness

No transaction lacks an attribution class.

Expected:

```text
unclassified transactions = 0
```

---

## Financial Reconciliation

The sum of `federal_action_obligation` across all attribution classes must exactly equal the certified AP-001A total.

Expected:

```text
obligation difference = $0.00
```

---

## County Integrity

Every `WA_COUNTY` transaction must reference a valid Washington county.

Expected:

```text
orphan Washington county references = 0
```

---

## Washington Unspecified Integrity

`WA_UNSPECIFIED` records shall contain no asserted county identity.

Expected:

```text
WA_UNSPECIFIED records with county assignment = 0
```

---

## Geography Conflict Integrity

All `GEOGRAPHY_CONFLICT` records must be traceable to a documented data-quality finding.

Expected:

```text
undocumented geography conflicts = 0
```

---

# Evidence Requirements

AP-001B shall produce evidence documenting:

* attribution logic;
* source counts;
* financial reconciliation;
* attribution-class counts;
* fiscal-year counts;
* county resolution statistics;
* Washington unspecified totals;
* geography-conflict totals;
* known limitations;
* certification status.

Evidence shall be retained under:

```text
analysis/AP-001/evidence/
```

or another explicitly documented project evidence location.

---

# Repository Artifacts

Planned AP-001B artifacts include:

```text
analysis/AP-001/
├── AP-001B_README.md
├── sql/
│   ├── 010_create_wa_transaction_attribution.sql
│   ├── 011_validate_wa_transaction_attribution.sql
│   └── additional certified views
├── python/
│   └── validate_wa_transaction_attribution.py
└── evidence/
```

---

# Acceptance Criteria

AP-001B shall be considered complete when:

1. every AP-001A transaction receives exactly one certified geographic attribution class;
2. Washington transactions are reproducibly separated from non-Washington transactions;
3. county-resolved and county-unspecified Washington transactions remain distinct;
4. geography conflicts are explicitly preserved and documented;
5. transaction counts reconcile exactly;
6. federal action obligations reconcile exactly;
7. county assignments contain no unsupported geographic inference;
8. all SQL, validation, evidence, and documentation are committed to the repository.

---

# Certification Statement

Upon successful completion, AP-001B will establish the authoritative analytical definition of:

> **The certified universe of USAspending Assistance transactions attributable to Washington State.**

All downstream Washington Assistance measurements shall derive from the certified AP-001B attribution layer.
