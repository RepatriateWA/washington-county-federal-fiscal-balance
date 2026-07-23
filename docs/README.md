## Procurement Geography

The procurement geography subsystem links each normalized USAspending award transaction to a canonical place and Washington reference geography.

```text
raw_award_transaction
        ↓
award_transaction
        ↓
place_of_performance
        ↓
place
```

Core components:

```text
etl/sql/111_create_procurement_place_of_performance.sql
etl/loaders/normalize_usaspending_places.py
etl/sql/113_add_place_id_to_place_of_performance.sql
etl/loaders/link_procurement_places.py
scripts/validate_procurement_geography.py
```

Validation commands:

```powershell
python -m scripts.validate_procurement_geography --load-batch-id 2
python -m scripts.validate_procurement_geography
```

Current validated result:

```text
517 normalized transactions
517 linked place relationships
5 canonical places
0 unresolved locations
0 duplicates
0 orphaned references
OVERALL RESULT: PASS
```

Full design and reproduction notes are documented in:

```text
docs/procurement_geography.md
```