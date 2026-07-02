# Data Dictionary

## Project

Washington County Federal Fiscal Balance Project

Purpose: compare federal dollars withdrawn from Washington counties through federal taxes against federal dollars returned through federal expenditures.

---

## Schema: reference

### reference.state_registry

| Column | Description |
|---|---|
| state_id | Internal state identifier |
| state_fips | Census state FIPS code |
| state_abbreviation | Two-letter state abbreviation |
| state_name | State name |
| census_region | Census region, if available |
| census_division | Census division, if available |
| created_at | Record creation timestamp |

### reference.county_registry

| Column | Description |
|---|---|
| county_id | Internal county identifier |
| state_id | Foreign key to `reference.state_registry` |
| county_fips | Three-digit county FIPS code |
| full_fips | Five-digit state + county FIPS code |
| county_name | County name |
| county_type | County classification |
| created_at | Record creation timestamp |

---

## Schema: irs

### irs.agi_bracket

| Column | Description |
|---|---|
| agi_bracket_id | Internal AGI bracket identifier |
| agi_bracket_code | Sort/order code |
| agi_bracket_label | IRS adjusted gross income bracket label |
| sort_order | Display/order value |

### irs.county_income_tax

Money amounts are stored in **thousands of dollars**, matching the IRS SOI workbook.

| Column | IRS Source | Description |
|---|---|---|
| county_income_tax_id | Generated | Internal record identifier |
| tax_year | Loader input | Tax year |
| county_id | County registry lookup | Internal county identifier |
| state_id | State registry lookup | Internal state identifier |
| county_fips | IRS column 0 | Three-digit county FIPS code |
| full_fips | Derived | Five-digit state + county FIPS code |
| agi_bracket_id | Derived | AGI bracket identifier |
| agi_bracket_label | IRS column 1 | AGI bracket label |
| number_of_returns | IRS column 2 | Number of returns |
| number_of_single_returns | IRS column 3 | Number of single returns |
| number_of_joint_returns | IRS column 4 | Number of joint returns |
| number_of_head_of_household_returns | IRS column 5 | Number of head of household returns |
| adjusted_gross_income | IRS column 16 | Adjusted gross income amount |
| total_income_amount | IRS column 18 | Total income amount |
| salaries_and_wages_amount | IRS column 20 | Salaries and wages amount |
| taxable_interest_amount | IRS column 22 | Taxable interest amount |
| ordinary_dividends_amount | IRS column 24 | Ordinary dividends amount |
| qualified_dividends_amount | IRS column 26 | Qualified dividends amount |
| business_net_income_amount | IRS column 30 | Business or profession net income less loss |
| net_capital_gain_amount | IRS column 32 | Net capital gain less loss in AGI |
| taxable_pensions_amount | IRS column 36 | Pensions and annuities amount |
| taxable_social_security_amount | IRS column 41 | Taxable Social Security benefits amount |
| created_at | Generated | Record creation timestamp |

### irs.import_log

| Column | Description |
|---|---|
| import_log_id | Internal import log identifier |
| tax_year | Tax year imported |
| source_file | Source workbook path |
| rows_loaded | Number of records loaded |
| imported_at | Import timestamp |