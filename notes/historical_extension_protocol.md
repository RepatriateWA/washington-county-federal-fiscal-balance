# WCFFBP Historical Extension Protocol — v1

## Purpose

Establish a reproducible procedure for extending Washington
statewide federal fiscal accounting into earlier fiscal years.

Developed from the FY2018–FY2019 reconstruction and
ETL-221U historical policy certification.

## Core procedure

1. Inventory the accounting families needed for the target years.
2. Identify existing later-year data, methods, and preferred sources.
3. Confirm historical source coverage and accounting measures.
4. Reuse established methodology only where historical evidence
   supports the same treatment.
5. Preserve later-year policies and create separately versioned,
   historically scoped source policies and program mappings.
6. Resolve overlap before treating amounts as additive.
7. Establish statewide accounting before county allocation.
8. Preserve signed obligations, including negative adjustments.
9. Distinguish obligations, outlays, benefit payments, and estimates.
10. Maintain explicit withheld, unmapped, and unresolved balances.
11. Run read-only preflight checks with expected row and dollar totals.
12. Execute controlled migrations with collision checks and rollback.
13. Check primary-key sequence alignment before inserts.
14. Independently certify committed results.
15. Commit code and methodology with selective Git staging.

## Lessons from ETL-221U

ETL-221U extended 33 historical program mappings using 17
historical source policies for FY2018–FY2019.

Certified disposition counts:
- INCLUDE_ADDITIVE: 14
- EXCLUDE_DUPLICATE: 7
- REFERENCE_ONLY: 3
- WITHHOLD_UNRESOLVED: 9

AL 86.001 was excluded from the historical extension because
its later ARPA-related authorization was not applicable.

The first migration attempt encountered an out-of-sync mapping
identity sequence. The transaction rolled back completely.
Sequence alignment was repaired and the migration subsequently
committed successfully.

ETL-221U7 independently certified the committed policy records,
source linkages, and absence of overlapping historical mappings.

## Future FY2015–FY2017 extension

Begin with a data-family/year coverage matrix.

Prioritize large accounting components and existing source
precedents before investigating low-materiality residuals.

Do not assume historical data are available merely because
a later-year program or policy exists.

Preserve uncertainty rather than manufacture accounting closure.

## Current priority

Complete a qualified statewide FY2018–FY2024 fiscal balance
before beginning the FY2015–FY2017 extension.

Principle: Measure first. Explain later.
