
# WCFFBP — Historical VA Procurement Geographic-Incidence Policy v0.1

**Scope:** Federal fiscal years 2018–2019, USAspending procurement transactions funded by the Department of Veterans Affairs.

**Evidence:** ETL-213J through ETL-213U.

**Status:** Provisional methodological finding. No database policy migration or additive ledger treatment authorized.

## Finding

The geographic location reported as the primary place of performance is not necessarily the location of the ultimate beneficiary of a federal procurement obligation.

In the examined medical imaging population, contracts recorded in Bothell, Snohomish County, Washington, include equipment explicitly identified for VA medical facilities in other states.

The recipient's registered business location, the reported place of performance, and the intended destination may be three distinct locations.

## Supporting evidence

- FY2018–FY2019 VA-funded procurement: 6,422 transactions and $869,852,725.45 in net obligations.
- PSC 6525 medical imaging: $173,873,919.54 in net obligations.
- Philips North America LLC (UEI L39CAPDUSB98): 666 medical imaging transactions recorded in Bothell, Snohomish County, totaling $156,915,946.28 in net obligations.
- The Philips North America LLC recipient address is recorded in Cambridge, Massachusetts, while its primary place of performance is recorded in Bothell, Washington.
- Contract descriptions explicitly identify VA medical facilities outside Washington, including Baltimore, Houston, Kansas City, St. Louis, and Lake City, Florida.
- ETL-213U identified 19 transactions totaling $16,847,096.50 in net obligations matching selected out-of-state geographic keywords. This is a screening result, not an exhaustive or certified beneficiary allocation.
- Multiple performance ZIP+4 values were observed within Bothell.

## Provisional accounting rules

1. Preserve the original place-of-performance geography without alteration.
2. Preserve the original recipient geography separately.
3. Retain documented destination or beneficiary geography as independent evidence, including award-level descriptions and transaction modifications.
4. Do not automatically allocate an obligation to a Washington county solely because its reported place of performance is within that county.
5. Do not automatically reallocate the full obligation to a named destination when the contract may involve activities in multiple locations.
6. Preserve signed obligations, award continuity, fiscal-year attribution, and transaction-level provenance.
7. Do not interpret procurement obligations as actual federal expenditures.
8. Do not add these procurement obligations to the federal expenditure ledger until their relationship to VA Geographic Distribution of Expenditures (GDX) has been reconciled under an explicit source-treatment policy.
9. Classify unresolved geographic incidence as WITHHOLD_UNRESOLVED for county-beneficiary allocation purposes, without deleting or suppressing the underlying evidence.

## Methodological limitations

Recorded performance geography, recipient business geography, and beneficiary geography represent different economic concepts.

The presence of an out-of-state beneficiary does not establish that no supplier-side economic activity occurred in Washington.

Keyword evidence is incomplete and must not be treated as a comprehensive geographic classification.

Obligations are not equivalent to actual federal expenditures. VA GDX overlap and the timing of expenditure recognition remain unresolved for FY2018–FY2019.

## Next investigation

ETL-213V: Read-only inventory and reconciliation of FY2018–FY2019 VA GDX controls and existing source-treatment policies.

No procurement obligations have been authorized for additive ledger inclusion.

---

WCFFBP methodological principle: Measure first. Explain later.
