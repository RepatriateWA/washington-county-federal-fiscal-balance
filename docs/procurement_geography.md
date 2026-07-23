# Procurement Geography Subsystem

## Purpose

The procurement geography subsystem creates a reproducible, auditable link between each normalized USAspending award transaction and a canonical geographic place.

It supports the broader Washington County Federal Fiscal Balance Project objective:

> Compare federal dollars withdrawn from Washington residents with federal dollars expended in Washington, ultimately at the county level.

The subsystem currently processes the Boeing contract transaction-history dataset loaded in procurement batch 2.

---

## Data Lineage

```text
USAspending source file
        ↓
procurement.raw_award_transaction
        ↓
procurement.award_transaction
        ↓
procurement.place_of_performance
        ↓
procurement.place
        ↓
reference.state_registry
reference.county_registry
```

### Source preservation

`procurement.raw_award_transaction` preserves each source record as JSON and identifies it with:

- `load_batch_id`
- `source_row_number`
- `record_sha256`

The normalized transaction table retains `load_batch_id` and `source_row_number`, allowing each normalized record to be traced back to its immutable raw source observation.

---

## Canonical Place Model

Canonical places are stored in:

```text
procurement.place
```

The canonical identity consists of:

```text
country_code
state_fips
county_fips
city_name
zip4
```

Congressional district is not part of the canonical identity because districts can change over time.

The table may retain:

- `congressional_district_current`
- `congressional_district_original`

as descriptive attributes rather than identity fields.

### Design principle

> Stable entities belong in dimensions. Time-varying characteristics belong as descriptive attributes.

---

## Transaction Relationship Model

Transaction-level geography is stored in:

```text
procurement.place_of_performance
```

Each award transaction may have one place-of-performance relationship.

The table contains:

- `award_transaction_id`
- `place_id`
- `state_id`
- `county_id`
- retained source geography fields
- `location_scope`

The current location-scope values are:

```text
OBSERVED
DERIVED_FROM_FIPS
DERIVED_FROM_ZIP
ALLOCATED
UNRESOLVED
```

For the current dataset, all 517 relationships are classified as `OBSERVED`.

---

## Implemented Components

### Migration 111

```text
etl/sql/111_create_procurement_place_of_performance.sql
```

Creates the canonical:

```text
procurement.place
```

table and its uniqueness constraint.

Despite the historical filename, this migration creates the canonical place dimension. The existing `procurement.place_of_performance` transaction relationship table was retained.

### ETL-112

```text
etl/loaders/normalize_usaspending_places.py
```

Extracts and normalizes USAspending place-of-performance fields from raw JSON.

Normalization includes:

- blank values converted to `NULL`
- uppercase country and state codes
- standardized city names
- FIPS validation
- ZIP validation
- congressional-district validation
- grouping by canonical place identity
- idempotent upsert behavior

Validated batch 2 result:

```text
Raw observations ............. 517
Canonical place candidates ... 5
Inserted on first run ........ 5
Inserted on second run ....... 0
Updated on second run ........ 0
Unchanged on second run ...... 5
Validation ................... PASS
```

### Migration 113

```text
etl/sql/113_add_place_id_to_place_of_performance.sql
```

Adds:

```text
place_id
```

to `procurement.place_of_performance`, creates the foreign key to `procurement.place`, and adds an index.

This migration is non-destructive. Existing source geography columns remain available for reconciliation.

### ETL-113

```text
etl/loaders/link_procurement_places.py
```

Links normalized award transactions to canonical places.

The loader:

1. selects a completed load batch;
2. joins normalized transactions to raw observations using `load_batch_id` and `source_row_number`;
3. applies the same normalization rules used by ETL-112;
4. resolves the canonical `place_id`;
5. resolves `state_id` and `county_id`;
6. inserts or updates one relationship per award transaction;
7. validates duplicate, orphan, and unresolved records;
8. commits only after validation succeeds.

Validated batch 2 result:

```text
Transactions examined ............... 517
Relationships inserted, first run ... 517
Relationships inserted, rerun ....... 0
Relationships updated, rerun ........ 0
Relationships unchanged, rerun ...... 517
Canonical places resolved ........... 517
Canonical places unresolved ......... 0
Validation .......................... PASS
```

---

## Validation

The subsystem is validated by:

```text
scripts/validate_procurement_geography.py
```

### Batch-specific validation

```powershell
python -m scripts.validate_procurement_geography --load-batch-id 2
```

### Full-system validation

```powershell
python -m scripts.validate_procurement_geography
```

The validator checks:

- every normalized transaction has one place relationship;
- transaction relationships are unique;
- no award-transaction foreign keys are orphaned;
- no canonical-place foreign keys are orphaned;
- no places are unresolved;
- all location-scope values are permitted;
- canonical place identities are unique;
- canonical places are not completely empty;
- county FIPS prefixes agree with state FIPS;
- retained transaction geography agrees with the canonical place;
- `state_id` agrees with canonical state FIPS;
- `county_id` agrees with canonical county FIPS.

Current full-system result:

```text
Transactions in scope .............. 517
Linked transactions ................ 517
Canonical places ................... 5
All place relationships ............ 517
Observed relationships ............. 517
Washington relationships ........... 517
Washington counties represented .... 1
Overall result ...................... PASS
```

---

## Reproduction Sequence

From the repository root:

```powershell
python run_sql_file.py etl\sql\111_create_procurement_place_of_performance.sql

python -m etl.loaders.normalize_usaspending_places --load-batch-id 2

python run_sql_file.py etl\sql\113_add_place_id_to_place_of_performance.sql

python -m etl.loaders.link_procurement_places --load-batch-id 2

python -m scripts.validate_procurement_geography --load-batch-id 2

python -m scripts.validate_procurement_geography
```

All migrations and loaders are designed to be safe to rerun.

---

## Current Scope and Interpretation

The current source file is:

```text
Boeing Contract_N0001904C3146_TransactionHistory_1.csv
```

It contains 517 normalized award transactions.

All 517 transactions resolve to Washington places, and one Washington county is represented in the current dataset.

This is expected for a single-award transaction-history file and should not be interpreted as statewide procurement coverage.

---

## Audit and Retention Policy

The following fields are temporarily retained in `procurement.place_of_performance`:

- `country_code`
- `state_code`
- `county_code`
- `city_name`
- `congressional_district`
- `zip_code`

They provide a transaction-level snapshot for reconciliation against `procurement.place`.

They should not be removed until:

1. multiple source files and load batches have been processed;
2. all geography validations continue to pass;
3. downstream queries use `place_id`;
4. a migration and rollback plan is documented;
5. an explicit decision is made whether the snapshot has continuing audit value.

---

## Next Recommended Expansion

The next procurement step is to generalize ingestion beyond the single Boeing transaction-history file.

Recommended sequence:

1. ingest a second USAspending award file;
2. rerun ETL-112 and ETL-113 for the new batch;
3. validate both the new batch and the full system;
4. confirm that existing canonical places are reused;
5. confirm that new places are inserted only when their canonical identities are genuinely new;
6. begin county-level aggregation of federal obligations.

This will test whether the canonical geography model remains stable across multiple awards, agencies, cities, counties, and source files.