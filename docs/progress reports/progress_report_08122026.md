Washington County Federal Fiscal Balance — Project Status

Status date: August 12, 2026

Ultimate analytical question: For each of Washington’s 39 counties, by federal fiscal year, how many federal dollars originate in the county versus how many federal dollars are expended in or attributable to the county?

Our principal analytical window remains FY2015–FY2024. FY2025 data are being preserved where already available, but FY2025 is not necessary to complete the original ten-year series.

1. Federal receipts — money Washington sends to the federal government

This remains the most difficult side to resolve at the county level.

Dataset/category	Years needed	Current status	County-level role
IRS SOI county income/tax data	2015–2024	2015 loaded and validated; 360 observations, 39 counties + WA total	Principal empirical basis for county allocation of federal receipts
IRS Data Book Table 5 — gross collections	2015–2024	Partial; FY2020 and FY2024 loaded in later work; historical series still incomplete	State/national control totals and reconciliation
IRS historical receipt evidence	2015–2024	Incomplete	Needed to establish defensible annual state receipt controls
Rockefeller federal receipts estimates	approx. 2010–2023	Evidence/reconciliation work underway	Independent state-level benchmark, not county source

The important distinction here is that county IRS SOI is not itself a complete measure of all federal receipts. It gives us powerful geographic information for allocating receipts, while IRS/Data Book/Rockefeller controls help determine the state total that ultimately must be distributed among counties.

So I would currently rate the receipts side as PARTIAL / major work remaining.

2. Federal expenditures — money flowing into Washington

This side is much farther along.

A. Social Security

OASDI has been implemented and validated at the Washington-state level.

The current model uses annualized December benefits, with the known limitation that we still need federal-fiscal-year control reconciliation before treating the resulting annual figures as final.

Status: 🟡 State model operational; county allocation/reconciliation remains.

B. Medicare

Medicare has also been implemented and validated at the Washington-state level.

The principal known limitation is Medicare Advantage, which is not yet fully represented in the existing model.

Status: 🟡 Substantial progress; reconciliation/completeness work remains.

C. Medicaid and CHIP

Washington totals have been acquired and incorporated into the tracked-expenditures structure.

The major unresolved problem is geographic rather than financial: state totals still require an explicit defensible county-allocation methodology.

Status: 🟡 State totals operational; county allocation remains.

Those three categories are already integrated into our Washington tracked-expenditures reporting architecture.

3. Federal procurement/contracts

This is the category we are working on now.

And there is an important milestone here:

FY2024 — COMPLETE AND CERTIFIED

Our native USAspending FY2024 Washington Contracts Prime Transactions dataset contains:

120,813 transactions
111,083 awards
all 39 Washington counties
$15,355,300,329.56 in federal action obligations
4,508 negative-obligation transactions preserved
6,367 zero-dollar transactions preserved
complete recipient, agency, NAICS, PSC and place-of-performance relationships

It passed 37 certification checks with zero failures and one documented warning, and EPS-001 was published.

So FY2024 Procurement is our first genuine production-quality county expenditure dataset.

Procurement year coverage
FY	Native WA dataset	Loaded	Normalized	Certified
2015	❌	❌	❌	❌
2016	❌	❌	❌	❌
2017	❌	❌	❌	❌
2018	❌	❌	❌	❌
2019	❌	❌	❌	❌
2020	Acquisition in progress	❌	❌	❌
2021	❌	❌	❌	❌
2022	❌	❌	❌	❌
2023	❌	❌	❌	❌
2024	✅	✅	✅	✅

For FY2020 we have independently established the correct universe:

110,244 Contracts Prime Transactions, Washington Place of Performance, with no recipient-state restriction.

The native USAspending acquisition is presently blocked by apparent USAspending service problems. Our fallback paginated acquisition successfully preserved 49,900 records, but we have intentionally parked that approach rather than alter the project's production methodology because of what may simply be a temporary upstream outage.

Status: 🟢 architecture complete; FY2024 certified; historical acquisition remains.

4. Federal assistance — grants and other assistance awards

This is another area where we've made substantial acquisition progress.

We have native USAspending Assistance archives for:

FY	Raw archive acquired	Prime transactions present	COVID relevance
2015	❌	—	—
2016	❌	—	—
2017	❌	—	—
2018	❌	—	—
2019	❌	—	—
2020	✅	✅	Critical
2021	✅	✅	Critical
2022	✅	✅	High
2023	✅	✅	Relevant
2024	✅	✅	Lower
2025	✅	✅	Supplemental

The raw Prime Transaction counts we observed include approximately:

FY2020 — 391,015
FY2021 — 261,008
FY2022 — 130,341
FY2023 — 85,700
FY2024 — 74,116
FY2025 — 83,464

Importantly, our assistance architecture explicitly preserves COVID and extraordinary-spending identification rather than deleting those observations.

The eventual analytical output will therefore support:

Federal expenditures including COVID relief

and

Federal expenditures excluding separately identified COVID relief

That is particularly important for interpreting FY2020–FY2022.

Status: 🟡 Excellent raw-data acquisition for FY2020–25; normalization/certification and pre-2020 acquisition remain.

5. Other major expenditure categories still required

These are the major gaps between our current expenditure ledger and a comprehensive Rockefeller-style federal balance-of-payments measure.

Category	2015–24 requirement	Current status
Social Security/OASDI	All years	🟡 State implementation exists
Medicare	All years	🟡 State implementation exists; MA gap
Medicaid	All years	🟡 State totals; county allocation needed
CHIP	All years	🟡 State totals; county allocation needed
Procurement/contracts	All years	🟢 FY2024 certified; others pending
Grants/assistance	All years	🟡 FY2020–25 raw data acquired
Veterans benefits	All years	🔴 Major category remaining
Federal civilian wages	All years	🔴 Remaining
Active-duty military wages	All years	🔴 Remaining
Federal civilian retirement	All years	🔴 Remaining
Military retirement	All years	🔴 Remaining
SSI	All years	🔴 Remaining
Nutrition assistance	All years	🔴 Remaining
Housing assistance	All years	🔴 Remaining
Education/student assistance	All years	🔴 Remaining
Refundable federal tax credits/direct payments	All years	🔴 Remaining
Other federal direct payments	All years	🔴 Requires inventory/reconciliation

This table probably gives the clearest picture of what remains.

6. Geographic/allocation infrastructure

This foundational layer is in good shape.

Our PostgreSQL reference system contains:

57 state/territory records and all 39 Washington counties, with state and county FIPS relationships established.

Procurement has already demonstrated that the geographic architecture works in practice: FY2024 transactions successfully resolve to all 39 counties, with 100% place relationships in the certification run.

That is a significant milestone because it demonstrates that this is no longer merely a proposed county methodology—we have actually produced a complete county-resolved federal expenditure category.

Status: 🟢 Operational.

7. Population denominators

Washington population data are needed for the secondary per-capita measures.

The intended source is Census Population Estimates Program (PEP) data, with consistent annual population definitions for state and county calculations.

This is important, but it isn't blocking the core dollar balance calculation.

Status: 🟡 Supporting dataset; needs final annual series/certification.

8. Rockefeller Institute — external benchmark

Rockefeller is extremely important, but I would classify it as a benchmark/control dataset, not as the source from which we intend to manufacture county numbers.

We are building the Rockefeller master evidence framework and coverage matrix, with the purpose of comparing our independently constructed Washington totals against Rockefeller's State Balance of Payments estimates.

The Rockefeller conceptual categories give us an excellent completeness test:

Direct Payments + Grants + Contracts/Procurement + Federal Wages

with extraordinary/COVID spending separately identifiable where possible.

That means Rockefeller ultimately answers an extremely useful question:

“After adding all of our independently constructed categories, are we reproducing a credible Washington statewide federal expenditure total?”

Only after the state-level reconciliation succeeds should we place strong confidence in the sum of the county allocations.

Status: 🟡 Evidence/reconciliation framework established; historical master series still being completed.

9. COVID/extraordinary spending

I would give this its own line in the status report because it has become a major methodological principle of the project.

We are not removing COVID spending from the raw data.

Instead:

Preserve → identify → tag → measure → report both ways.

This allows us eventually to produce, for example:

King County FY2021 federal fiscal balance
including extraordinary COVID spending

versus

King County FY2021 underlying federal fiscal balance
excluding identified COVID spending

That prevents an extraordinary historical event from silently distorting conclusions about Washington's normal fiscal relationship with the federal government.

Status: 🟢 methodological treatment established; transaction-level classification remains ongoing.

Overall project assessment

I would summarize the project today as follows:

Project component	Status
Database architecture	🟢 Established
Washington county geography	🟢 Complete
Provenance/evidence architecture	🟢 Established
Certification framework	🟢 Operational
County IRS framework	🟡 Partially populated
State federal-receipts controls	🟡 Partial
Social Security	🟡 Substantially developed
Medicare	🟡 Substantially developed
Medicaid/CHIP	🟡 State totals developed
Procurement	🟢 First complete/certified FY: 2024
Assistance	🟡 FY2020–25 raw acquisition strong
COVID identification	🟡 Infrastructure/method established
Veterans	🔴 Not yet built
Federal civilian/military wages	🔴 Not yet built
Federal/military retirement	🔴 Not yet built
Remaining direct payments	🔴 Not yet built
Census population controls	🟡 Needs completion
Rockefeller reconciliation	🟡 In progress
Final 39-county balance calculation	Not yet appropriate
The larger picture

We have finished much of the infrastructure problem and are now squarely in the coverage problem.

Earlier in the project, we still had to prove that we could reliably ingest government data, preserve source provenance, normalize entities, resolve geography, prevent duplicates, reconcile dollars, and certify the result.

FY2024 Procurement demonstrated that the machinery actually works end-to-end.

The job ahead is consequently much more repetitive and measurable: fill the year/category matrix.

Conceptually, our final calculation becomes:

County federal fiscal balance =

federal expenditures attributable to county
− federal receipts attributable to county

for each of the 39 counties and each fiscal year.

And the expenditure side becomes approximately:

**Direct payments

Social Security
Medicare
Medicaid/CHIP
grants/assistance
procurement/contracts
Veterans benefits
federal civilian compensation
military compensation
federal/military retirement
other federal payments**

with COVID/extraordinary expenditures separately tagged.

So I would characterize our position as well beyond proof-of-concept, but not yet at comprehensive coverage. The biggest remaining substantive gaps are the historical receipts controls/allocation, pre-2020 assistance, pre-2024 procurement, Veterans spending, federal/military compensation and retirement, and the remaining direct-payment programs.

And today's USAspending difficulty doesn't change that assessment. It is an acquisition interruption affecting one portion of one source, not a problem with the underlying architecture.

