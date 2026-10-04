# OPM FedScope Salary-Suppression Evidence

## Purpose

This directory preserves selected validation evidence concerning salary-field
completeness in the U.S. Office of Personnel Management (OPM) FedScope
employment microdata used by WCFFBP.

The evidence was produced while evaluating whether FedScope salary observations
could support Washington federal civilian compensation measurement and
allocation.

## Preserved evidence

### opm_salary_suppression_diagnostic_2015_2024.txt

Human-readable diagnostic output profiling the September FedScope employment
files for 2015 through 2024.

The diagnostic examines:

- WORKSTAT=1 employment observations;
- blank SALARY observations;
- salary-level (SALLVL) classifications;
- agency/subagency patterns;
- geographic-location patterns; and
- cross-year changes in salary-field completeness.

A compact machine-readable summary is preserved separately at:

    data/interim/opm/opm_fedscope_salary_suppression_diagnostic_2015_2024.csv

## Principal finding

FedScope salary-field completeness changes materially between 2016 and 2017.

For WORKSTAT=1 observations, the percentage of employment associated with a
blank SALARY field is:

| Year | Blank salary employment | Percent |
|------|-------------------------|---------|
| 2015 | 1,604 | 0.0873% |
| 2016 | 952 | 0.0510% |
| 2017 | 259,449 | 13.8744% |
| 2018 | 248,606 | 13.2792% |
| 2019 | 254,387 | 13.3998% |
| 2020 | 256,023 | 13.2212% |
| 2021 | 258,626 | 13.2185% |
| 2022 | 257,935 | 13.1587% |
| 2023 | 263,255 | 12.9029% |
| 2024 | 274,400 | 13.1091% |

The discontinuity beginning in 2017 is analytically material. WCFFBP therefore
does not treat missing FedScope salary observations as a negligible random
omission and does not silently interpret blank salary values as zero.

## Evidentiary role

This package is validation evidence. It does not by itself establish a final
federal-wage accounting or geographic-allocation rule.

WCFFBP maintains the distinction between:

1. source measurement;
2. source semantics and completeness;
3. reconciliation to independent controls;
4. accounting policy;
5. ledger inclusion; and
6. geographic incidence or allocation.

A PASS or completed diagnostic at one stage does not automatically authorize a
downstream accounting or incidence decision.

## Reproducibility

The detailed console output is retained so that reviewers can inspect the
observed suppression patterns rather than relying solely on the summarized
annual percentages.

The compact CSV provides the corresponding machine-readable cross-year
measurements.
