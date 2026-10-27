# SSI Authorization Decision - ETL-235

## Disposition

**NOT_YET_AUTHORIZED â€” expenditure basis required.**

Seven annual Washington SSI observations have been
verified from USAspending Assistance Listing 96.006.

The amounts represent net federal action obligations,
not independently certified federal cash expenditures.

## Annual controls

| FFY | Transactions | Obligations USD |
|---|---:|---:|
| 2018 | 848 | 995804337.00 |
| 2019 | 810 | 1088456509.00 |
| 2020 | 908 | 1104856696.00 |
| 2021 | 905 | 1094843681.00 |
| 2022 | 904 | 1191303562.00 |
| 2023 | 924 | 1168650267.00 |
| 2024 | 894 | 1116434589.00 |

**Total: 6,193 transactions; $7,760,349,641.00.**

ETL-176's FY2020-FY2024 certification was reproduced
exactly: 4,535 transactions and $5,676,088,795.00.

FY2018-FY2019 observations were recovered from the
certified assistance view but remain outside the
original ETL-176 SSI-specific policy period.

## Accounting boundary

SSI is distinct from SSA OASDI under the established
ETL-135/176 overlap policy.

Prior inclusion of SSI in an obligation-based assistance
framework does not establish cash-expenditure eligibility
for the current statewide fiscal-balance ledger.

FY2018-FY2019 records have missing recipient names and
FAIN identifiers in the profiled view.

## Reopening requirements

- Identify an official SSI expenditure/payment source.
- Verify Washington geographic attribution.
- Establish federal fiscal-year cash-payment timing.
- Reconcile payments against obligation controls.
- Preserve OASDI nonduplication safeguards.
- Review FY2018-FY2019 historical semantics.
- Complete a separate ledger authorization decision.

## Registry effect

Seven annual accounting matrix observations populated.
Seven SSI ledger authorizations remain withheld.
Canonical annual ledger unchanged.

## Evidence

- `etl/sql/135_seed_oasdi_overlap_policy.sql`
- `etl/sql/176_seed_ssi_inflow_source_policy.sql`
- `etl/validation/assistance/174b_5b_profile_ssi.sql`
- `etl/validation/235c_ssi_annual_controls.txt`
