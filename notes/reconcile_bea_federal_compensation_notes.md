# BEA Federal Compensation Reconciliation Notes

## Objective

Develop authoritative Washington State and county federal compensation
measures for WCFFBP for 2015–2024.

Candidate inflow families:

1. FEDERAL_CIVILIAN_COMPENSATION
2. MILITARY_COMPENSATION

## Candidate authoritative source

U.S. Bureau of Economic Analysis (BEA)
Regional Economic Accounts

## Candidate county dataset

CAINC6N — Compensation of Employees by NAICS Industry

## Candidate industry classes

Federal, civilian
Military

## Accounting concept

Compensation of employees =
    wages and salaries
    +
    supplements to wages and salaries

This is broader than payroll alone.

## Questions requiring resolution before ETL

1. Exact current CAINC6N line codes for federal civilian and military.
2. Availability for every Washington county for 2015–2024.
3. Units and scaling.
4. Treatment of suppressed/missing observations.
5. State-total reconciliation against the corresponding BEA state table.
6. Geographic attribution methodology.
7. Calendar-year versus federal-fiscal-year treatment.
8. Relationship to Rockefeller balance-of-payments expenditure categories.
9. Potential overlap with other WCFFBP inflow families.

## Initial BEA API acquisition attempt

Initial requests incorrectly used LineCode 910 and 920.

BEA metadata inspection established the correct CAINC6N line codes:

- 2001 — Federal civilian
- 2002 — Military

The initial acquisition client also failed to detect API errors returned at
BEAAPI.Error and therefore archived zero-row responses.

The acquisition client was corrected to:
- use LineCode 2001 / 2002;
- recognize both BEAAPI.Error and BEAAPI.Results.Error;
- fail on missing or zero-row data responses.
## Methodology gates cleared

### Reference period
BEA annual CAINC6N / SAINC6N compensation observations are calendar-year
measures.

WCFFBP semantic:
reference_period_type = CALENDAR_YEAR

They must not be labeled federal fiscal year observations without an explicit
conversion methodology.

### Geographic basis
Compensation by industry is reported on a place-of-work basis.

WCFFBP semantic:
geographic_basis = PLACE_OF_WORK

County federal civilian estimates correspond principally to the geography of
the employing establishment.

Military county estimates use military personnel/base geography and specialized
BEA allocation procedures.

### Federal civilian compensation
BEA federal civilian compensation includes:

- wages and salaries;
- employer pension contributions, including CSRS/FERS/TSP;
- employer health-insurance contributions;
- employer life-insurance contributions;
- employer government-social-insurance contributions.

It is therefore broader than cash payroll.

### Military compensation
BEA military compensation includes active-duty and reserve personnel, including
National Guard, and consists of:

- monetary wages/pay;
- housing, uniform, ration, and other pay-in-kind;
- employer pension contributions;
- employer social-insurance contributions;
- military life-insurance contributions;
- specified military health-care components.

Beginning in 2002 it also includes DoD accrual funding for retiree health
benefits.

### Future overlap controls
Current employer pension contributions included in compensation are
conceptually distinct from retirement benefits paid to former employees.

Before FEDERAL_CIVILIAN_RETIREMENT or MILITARY_RETIREMENT enters the additive
ledger, those families must be reconciled against the pension/accrual components
embedded in BEA compensation.

Any future DoD/TRICARE health expenditure family must likewise be reconciled
against health-related components included in BEA military compensation.