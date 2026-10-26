# ETL-231 - Federal Wage Authorization Decision

## Decision

NOT_YET_AUTHORIZED ? RECONCILIATION REQUIRED

## Scope

Federal civilian wages and federal military wages,
federal fiscal years 2018-2024.

Fourteen annual observations are retained in the accounting registry.

## Existing accounting controls

Federal civilian wages:
- OMB government-wide nonmilitary wage obligations.
- Object classes 11.1, 11.3, 11.5, and 11.8.
- Washington geographic allocation using OPM FedScope.
- Policy: ANALYSIS-158-v1.
- View: opm.v_omb_civilian_wage_allocation.

Federal military wages:
- OMB government-wide military wage obligations.
- Object classes 11.6 and 11.7.
- Washington geographic allocation using BEA SAINC7N line 2002.
- Policy: ANALYSIS-157-v1.
- View: bea.v_omb_military_wage_allocation.

Combined certification:
- analysis.v_wa_federal_wage_allocation.
- ANALYSIS-160-v1.

## Evidence and reproducibility

ETL-225M2 previously reproduced the seven annual observations
for each wage family.

ETL-231A through ETL-231D reviewed the existing source
architecture, accounting definitions, and allocation policies.

The underlying observations are preserved. No re-acquisition
or replacement of existing wage controls is authorized.

## Accounting boundary

OMB object-class values measure obligations, not directly
observed Washington cash wage payments.

OPM and BEA are geographic allocation sources, not additional
additive expenditure sources.

The military allocation applies matching calendar-year BEA
shares to federal-fiscal-year OMB obligations.

Public OPM FedScope salary suppression materially limits
civilian allocation precision for FY2018-2024.

The existing wage policies specify INCLUDE_AFTER_RECONCILIATION.

## Cross-family overlap

Potential overlap with VA GDX expenditures and other
federal expenditure families has not been resolved.

No zero-overlap assumption is authorized.

Direct BEA or OPM wage amounts must not be added to the
OMB-controlled allocations as separate inflows.

## Registry disposition

FEDERAL_CIVILIAN_WAGES: NOT_YET_AUTHORIZED.
FEDERAL_MILITARY_WAGES: NOT_YET_AUTHORIZED.

All fourteen annual observations remain available as
reproduced candidate controls.

No wage amount is promoted to the qualified provisional
additive ledger.

The existing 28 of 147 qualified provisional ledger
observations remain unchanged.

## Reopening conditions

Reconsider authorization when evidence establishes:

1. A defensible obligations-to-expenditures accounting treatment.
2. Appropriate geographic and temporal qualifications.
3. Cross-family overlap treatment, particularly with VA GDX.
4. An independently verified family-specific authorization decision.

## Conclusion

Source and allocation verification are not equivalent to
additive accounting authorization.

ETL-231 closes with both wage families retained but withheld.
