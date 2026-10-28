# AL 10.561 — SNAP Administrative Matching Grants
## Materiality closure and authorization qualification

Decision reference: ETL-240A2H11
Status: SOURCE_RECONCILED; FURTHER_SOURCE_RESEARCH_DEFERRED
Scope: Washington State, FFY2018–FFY2024
Decision type: Documentation only
Ledger authorization changes: NONE

### 1. Program and source identity

Assistance Listing 10.561 concerns SNAP State Administrative
Matching Grants.

Primary transaction source:
USAspending assistance transactions, Washington attribution.

Independent expenditure source:
USDA Food and Nutrition Service SNAP State Activity Reports.

The two sources represent related program activity but use
different measurement bases. They must not be added together.

### 2. Verified USAspending obligations

Fiscal year | Washington obligations (USD) | Rows
2018 | 113371102.13 | 53
2019 | 117359163.02 | 45
2020 | 130715687.79 | 43
2021 | 140821290.39 | 40
2022 | 131634502.34 | 42
2023 | 147533605.75 | 41
2024 | 130186308.88 | 39

Seven-year total: 911621660.30 USD
FY2018–FY2019 total: 230730265.15 USD
FY2020–FY2024 total: 680891395.15 USD
Total transaction rows: 303

All 303 Washington-attributed transaction observations matched
analysis.v_certified_assistance_ledger by transaction ID.

IMPORTANT:
Membership in the certified assistance view does not itself
establish canonical statewide ledger authorization.

The established FY2018–FY2019 additive policy is preserved.
FY2020–FY2024 authorization remains subject to the existing
accounting policy and canonical ledger verification.

### 3. Independent USDA expenditure controls

FY2018 ordinary federal share: 100351208 USD
FY2019 ordinary federal share: 107364488 USD
FY2020 ordinary federal share: 110112584 USD
FY2021 ordinary federal share: 113833181 USD
FY2022 ordinary federal share: 113928759 USD
FY2023 ordinary federal share: 124767005 USD
FY2024: report not located.

FY2020 SOURCE ANOMALY:
The FY2020 report's administrative-cost Table 7 reproduces
FY2019 amounts, including Washington's 107364488 USD federal
share and the national total. The FY2020 report's Table 9
instead reports Washington federal costs of 110112584 USD.
The report's other administrative-cost table and narrative
also contain FY2020-specific observations.

The Table 7 duplication is treated as an apparent published
source error, not as an independently confirmed USDA erratum.
Table 9 is the preferred provisional FY2020 control.

COVID/ARPA distinctions:
FY2021 separately reported COVID funding: 185291 USD,
with scope and inclusion relationship not fully resolved.
FY2022 ARPA column: 3163178 USD.
FY2023 ARPA column: 2221984 USD.

FY2022 and FY2023 ARPA columns are separate from ordinary
federal-share columns. Do not add any of these USDA amounts
to USAspending obligations without an overlap reconciliation.

USAspending COVID-tagged net obligations, FY2021–FY2024:
13173024.72 USD. This is a subset, not an additive amount.

### 4. Accounting disposition

The source evidence is sufficient to establish the magnitude
of this program for statewide materiality assessment.

No new canonical ledger authorization is granted here.
No prior authorization is withdrawn or altered.
No USDA expenditure measure is substituted into the ledger.

The entire FY2020–FY2024 USAspending obligation population,
680891395.15 USD, represents approximately 0.33 percent of
the absolute provisional seven-year statewide net balance
of approximately 208.012 billion USD.

This is a gross inclusion/exclusion sensitivity, not an
estimate of missing federal expenditure.

Further USDA source research is deferred under the project's
materiality and diminishing-returns principles.

### 5. Criteria for reopening

Reopen this investigation only if one or more occurs:

1. Canonical ledger verification identifies a material
   omission or double-counting issue.
2. A corrected USDA FY2020 report or authoritative FY2024
   control materially changes the reconciliation.
3. New evidence demonstrates that USAspending obligations
   substantially misrepresent Washington program incidence.
4. County allocation or publication certification requires
   a more precise treatment.

Otherwise preserve this disposition and proceed to larger
unresolved federal inflow families.

### 6. Evidence chain

ETL-223N2 / ETL-223N3:
Historical FY2018–FY2019 additive policy and certification.

ETL-240A2H2:
USDA report acquisition and SHA256 manifest.

ETL-240A2H3 through ETL-240A2H7:
USDA table identification, extraction, spatial verification,
and FY2020 anomaly review.

ETL-240A2H8 / ETL-240A2H9:
Database schema and view profiling.

ETL-240A2H10:
Read-only seven-year obligation and certified-view comparison.

Primary local evidence:
data/raw/usda/snap/state_activity_reports/
240a2h10_stdout.txt

No database writes or canonical ledger changes were made
during this closure investigation.