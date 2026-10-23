# WCFFBP Unified Accounting Model — v0.3.0 WORKING

## Canonical sign convention
**Federal fiscal balance = federal inflows to Washington − federal outflows from Washington.**

`B_y = I_y - O_y`

A **negative** federal fiscal balance means payments from Washington to the federal
government exceed federal expenditures and other qualifying payments flowing into
Washington: net federal dollars are removed from Washington's economic activity
under the project's accounting definition. A positive balance means the reverse.
This is a fiscal-flow accounting characterization, not a comprehensive welfare measure.

## Model layers
1. `source_family_registry.csv`: one canonical family catalog; retains source,
   certification, and authorization as distinct dimensions.
2. `annual_accounting_matrix.csv`: existing source-year observations; preserved
   verbatim from v0.2.7 to avoid conflating gross source amounts with additive
   classifications or authorized ledger amounts.
3. `canonical_annual_ledger.csv`: one family-year row with distinct candidate and
   authorized amounts. **All authorization amounts intentionally blank** until
   individually certified. Reference and reporting-parent rows excluded.
4. `evidence_crosswalk.csv` and historical control files: provenance and
   reconciliation controls.

## Historical assistance updates
`historical_assistance_224g_certified_controls.csv` records ETL-224G
post-224M/224N WA geography totals. These are additive-classified *net
obligations*, not necessarily cash expenditures or final ledger-authorized amounts.
`historical_assistance_223a_224g_reconciliation.csv` preserves the earlier ETL-223A
values and quantifies the differences. Their cause has **not** been demonstrated
by a transaction-level reconciliation; do not assert that geography repair alone
explains the difference. Both control sets remain accessible.

## ETL-216C eligibility rules
ETL-216C labels are **diagnostic**, not authorization. Distinguish actual FFY
Medicaid/CHIP, calendar-year Original Medicare, annualized December OASDI,
VA GDX, and allocated compensation. Its program-mapping conflict checks
remain a required pre-authorization control.

## Existing reporting compatibility
ETL-222B's `partial_fiscal_balance_dollars` reports revenue minus tracked
expenditures, the **opposite sign** of the canonical model. Treat legacy values
as legacy diagnostics, never as canonical signed balances. Do not silently
rewrite historical source files or database views.

## Next review gates
- Verify source-family definitions and potential overlap, particularly
  Medicare parent/child components and HCV within assistance.
- Inspect ETL-216C outputs and certification evidence before authorizing rows.
- Reconcile ETL-223A vs ETL-224G policy/disposition differences.
- Build certified statewide inflow/outflow aggregates only from authorized rows.
- Validate sign, non-double-counting, fiscal-year basis, and missingness.
