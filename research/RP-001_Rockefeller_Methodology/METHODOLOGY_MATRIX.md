# Rockefeller Methodology Matrix

## Objective

Reconstruct the Rockefeller Institute Balance of Payments methodology for Washington State using only publicly available federal data.

Success criterion:

Reproduce Rockefeller's published Washington receipts, expenditures, and federal fiscal balance to within 0.5%.

---

# Receipts

| Individual Income Tax | IRS SOI tax liability allocator | IRS SOI | Researching | Rockefeller appears to allocate federal budget individual income tax totals by state tax liability, not IRS Table 5 gross collections. |
| Corporate Income Tax | BEA capital income / wages allocator | BEA | Researching | Rockefeller uses proxy allocation because corporate tax location is not directly assignable to one state. |
| Estate & Gift Taxes | IRS Gross Collections Table 5 | IRS Data Book Table 5 | High confidence | This may align closely with our IRS Table 5 data. |
| Railroad Retirement | IRS Gross Collections Table 5 | IRS Data Book Table 5 | High confidence | Rockefeller uses IRS gross collections for this component. |


| Receipt Category                 | Rockefeller National Total Source   | Rockefeller State Allocator                             | Difference from our IRS Table 5 approach            |
| -------------------------------- | ----------------------------------- | ------------------------------------------------------- | --------------------------------------------------- |
| Individual income tax            | Federal Budget Historical Table 2.1 | IRS SOI Table 2 tax liability: A06500 + A85530 + A85300 | Major difference: not IRS Table 5 gross collections |
| OASDI / Social Security          | Federal Budget Table 2.4            | SSA covered earnings / contributions data               | Not Table 5                                         |
| Medicare HI                      | Federal Budget Table 2.4            | SSA Medicare covered earnings / contributions data      | Not Table 5                                         |
| Railroad retirement              | Federal Budget Table 2.4            | IRS Gross Collections Table 5                           | Possible alignment                                  |
| Unemployment insurance           | Federal Budget Table 2.4            | U.S. DOL UI Financial Transaction Summary               | Not Table 5                                         |
| Other retirement                 | Federal Budget Table 2.4            | Census population                                       | Not Table 5                                         |
| Corporate income tax             | Federal Budget Table 2.1            | BEA: 75% capital income + 25% wages                     | Major difference                                    |
| Transportation excise            | Federal Budget Table 2.4            | FHWA Highway Trust Fund receipts                        | Not Table 5                                         |
| Alcohol excise                   | Federal Budget Table 2.4            | NIAAA alcohol consumption                               | Not Table 5                                         |
| Tobacco / airport / other excise | Federal Budget Table 2.4            | Census population                                       | Not Table 5                                         |
| Estate & gift taxes              | Federal Budget Table 2.5            | IRS Gross Collections Table 5                           | Possible alignment                                  |
| Customs / Fed deposits / misc.   | Federal Budget Table 2.5            | Treated as unallocable                                  | Excluded from state allocation                      |


---

# Expenditures

| Category | Rockefeller Source | Our Source | Status | Notes |
|----------|-------------------|------------|--------|------|
| Social Security | | | | |
| Medicare | | | | |
| Medicaid | | | | |
| Defense Contracts | | | | |
| Defense Payroll | | | | |
| Veterans Benefits | | | | |
| Federal Salaries | | | | |
| Procurement | | | | |
| Grants | | | | |
| Transportation | | | | |
| Agriculture | | | | |
| Education | | | | |
| COVID Programs | | | | |

---

# Validation

| Item | Published | Reconstructed | Difference |
|------|----------:|--------------:|-----------:|
| Receipts | | | |
| Expenditures | | | |
| Fiscal Balance | | | |
| Excluding COVID | | | |

---

# Open Questions

(keep a running list)