# RP-002 — Extraordinary Funding (DEFC) Reference Reconciliation Recommendation

## Recommendation

Approve the twelve unresolved Disaster Emergency Fund Codes (DEFCs) identified during USAspending Assistance processing for inclusion in `reference.extraordinary_funding_code` through Migration 130.

The twelve codes are:

`2`, `5`, `7`, `A`, `AAA`, `AAF`, `AAJ`, `I`, `K`, `R`, `T`, and `W`.

Together, these codes account for 1,125 previously unresolved DEFC observations across the processed fiscal-year batches.

## Classification Decision

The approved classifications are:

| DEFC | Official Description              | Funding Family       | Extraordinary | COVID | IIJA  | Confidence |
| ---- | --------------------------------- | -------------------- | ------------- | ----- | ----- | ---------- |
| 2    | Emergency P.L. 117-70             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| 5    | Wildfire Suppression P.L. 117-103 | WILDFIRE_SUPPRESSION | TRUE          | FALSE | FALSE | HIGH       |
| 7    | Emergency P.L. 117-159            | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| A    | Emergency P.L. 115-56             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| AAA  | Emergency P.L. 117-180            | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| AAF  | Emergency P.L. 118-42             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| AAJ  | Emergency P.L. 118-50             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| I    | Emergency P.L. 116-94             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| K    | Emergency P.L. 116-113            | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| R    | Emergency P.L. 116-260            | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |
| T    | Wildfire Suppression P.L. 116-260 | WILDFIRE_SUPPRESSION | TRUE          | FALSE | FALSE | HIGH       |
| W    | Emergency P.L. 117-31             | OTHER_EMERGENCY      | TRUE          | FALSE | FALSE | HIGH       |

## Methodological Basis

The classifications are based on:

1. The official DEFC descriptions preserved in the USAspending Assistance source data;
2. U.S. Treasury documentation defining DEFC as a designation mechanism for disaster, emergency, wildfire suppression, or non-designated budgetary resources;
3. USAspending documentation identifying the DEFC values used for COVID-19 and Infrastructure Investment and Jobs Act tracking;
4. The project principle that COVID and other extraordinary funding classifications must be assigned at the DEFC-code level rather than inferred solely from the associated Public Law.

None of the twelve RP-002 codes is classified as COVID-related or IIJA-related.

## Important Analytical Principle

A Public Law alone is not a sufficient basis for extraordinary-funding classification.

Different DEFC values associated with the same Public Law may represent different statutory or budgetary designations.

For example, P.L. 116-260 appears under multiple DEFC values with different analytical meanings. Therefore, the DEFC code—not merely the Public Law—is the authoritative classification unit used by this project.

## Implementation Recommendation

Create:

`etl/sql/130_expand_extraordinary_funding_codes.sql`

The migration should:

* upsert all twelve approved DEFC rows into `reference.extraordinary_funding_code`;
* preserve the approved funding-family classifications;
* set `extraordinary_flag = TRUE`;
* set `covid_flag = FALSE`;
* set `iija_flag = FALSE`;
* set `confidence = 'HIGH'`;
* preserve authoritative citations and research notes;
* include validation that all twelve codes are present with the expected classifications.

## Post-Migration Validation

After Migration 130 is applied, rerun:

`etl.loaders.link_assistance_extraordinary_funding`

for load batches:

* 9
* 10
* 11
* 12

Acceptance criteria:

* `Unknown code observations = 0`
* `Distinct unknown DEFC codes = 0`
* `Unparsed segments = 0`
* `Duplicate relationships = 0`
* `Orphan transaction links = 0`
* `Orphan reference links = 0`
* Validation PASS for every affected batch

## Conclusion

RP-002 recommends approval of all twelve classifications and authorizes implementation through Migration 130.

Upon successful post-migration validation, the extraordinary-funding reference dimension will be considered fully reconciled for the fiscal-year Assistance datasets processed under ETL-005.
