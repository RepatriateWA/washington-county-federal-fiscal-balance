# ETL-232 - SSA OASDI Authorization Decision

## Decision

NOT_YET_AUTHORIZED - FISCAL-YEAR PAYMENT BASIS REQUIRED

## Scope

SSA Old-Age, Survivors, and Disability Insurance (OASDI),
Washington State, federal fiscal years 2018-2024.

Seven existing annual observations are retained.

## Existing source evidence

- EP-SSA-OASDI-001 certification package.
- ETL-225O annual control reproduction.
- ETL-232B through ETL-232D source and accounting review.
- Reporting view: reporting.v_washington_ssa_summary.
- Existing measurement: ANNUALIZED_DECEMBER_SNAPSHOT.

The existing controls measure December benefits in
current-payment status multiplied by twelve.

They are not independently established as actual
federal-fiscal-year benefit expenditures.

## Accounting boundary

The principal ledger requires a defensible federal
fiscal-year expenditure measure.

A December snapshot multiplied by twelve does not
establish actual payments made from October through
September of the corresponding federal fiscal year.

The seven candidate amounts remain preserved,
but no FFY cash-outlay equivalence is assumed.

## Source overlap

ETL-135 and ETL-209I establish OASDI overlap policy
for corresponding USAspending assistance programs.

SSA remains the preferred source for OASDI accounting.
Corresponding USAspending obligations must not be
added independently as duplicate expenditures.

This decision does not extend the OASDI policy to SSI.

## Registry disposition

SSA_OASDI: NOT_YET_AUTHORIZED.

No candidate amounts are changed.
No annual matrix statuses are promoted.
No canonical ledger authorization is changed.

Qualified provisional ledger: 28 of 147 observations.

## Reopening conditions

Reconsider authorization when:

1. A documented actual-payment or expenditure series
   supports the required annual accounting basis.
2. Federal fiscal-year alignment is established.
3. Washington geographic attribution is reproducible.
4. National and state controls reconcile appropriately.
5. Existing USAspending overlap exclusions are preserved.
6. Independent family-specific validation passes.

## Conclusion

The existing SSA evidence is suitable for county-level
beneficiary analysis and candidate accounting controls.

It is not yet sufficient for additive FFY expenditure
authorization.

ETL-232 closes with all seven observations retained
and authorization withheld.
