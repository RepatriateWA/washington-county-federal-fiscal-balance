# ETL-234 - Railroad Retirement Authorization Decision

## Decision

NOT_YET_AUTHORIZED - EXPENDITURE BASIS REQUIRED

## Scope

Railroad Retirement Board benefit streams, Washington State,
federal fiscal years 2018-2024.

## Existing evidence

- ETL-189B: SSA/OASDI overlap screening.
- ETL-189C: benefit-composition investigation.
- ETL-189D: mutually exclusive benefit partition.
- ETL-190: FY2020-FY2024 award-level accounting policy.
- ETL-205: FY2018-FY2019 historical classification.
- ETL-209D/E: historical verification and reconciliation.
- ETL-234A-C: registry and methodology reconnaissance.

## FY2020-FY2024 controls

Railroad Retirement Act pensions: $1,338,494,529.25
Railroad unemployment/sickness: $18,813,479.17

Combined net federal action obligations: $1,357,308,008.42

The existing policy classifies the heterogeneous AL 57.001
population at award level rather than applying a blanket
program-level INCLUDE_ADDITIVE mapping.

## FY2018-FY2019 controls

Additive-classified obligations: $515,006,959.71
Withheld obligations: $4,173,083.00

These controls are preserved separately.

## Accounting boundary

The existing preferred source is USAspending assistance.

The established accounting measure is
NET_FEDERAL_ACTION_OBLIGATION.

Benefit descriptions and award-level classifications
support economic characterization and overlap review,
but do not independently certify actual cash expenditures.

No complete independently validated FY2018-FY2024
Washington RRB cash-payment series has been identified
in the reviewed repository evidence.

## SSA overlap

Preserve ETL-190's conclusion that the profiled RRB-paid
benefits are distinct from SSA-paid OASDI observations.

Preserve existing SSA/OASDI program mappings and
the RRB award-level reconciliation controls.

## Registry disposition

RAILROAD_RETIREMENT: NOT_YET_AUTHORIZED.

Preserve existing FY2018-FY2019 observations.
Preserve FY2020-FY2024 unpopulated annual cells.
Preserve existing award-level program classifications.

No principal-ledger authorization or amount is changed.

Qualified provisional ledger: 28 of 147 observations.

## Reopening conditions

1. Identify an official RRB payment/expenditure source.
2. Verify federal-fiscal-year timing.
3. Establish Washington geographic attribution.
4. Reconcile retirement and unemployment/sickness streams.
5. Preserve SSA overlap and nonduplication controls.
6. Reproduce all seven annual payment controls.
7. Complete a family-specific authorization review.

## Conclusion

Existing benefit classifications remain valid within
their established USAspending accounting framework.

Principal-ledger expenditure authorization is withheld
pending independently validated payment evidence.
