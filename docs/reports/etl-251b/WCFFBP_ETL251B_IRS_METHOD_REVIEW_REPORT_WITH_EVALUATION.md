# WCFFBP — ETL-251B
## Irs Administrative Collections: Accounting Reasonableness And Geographic Attribution
*Evidence-based closeout report | 2026-11-23*
*Disposition: CLOSE LIMITED REVIEW WITH QUALIFICATIONS; NO LEDGER OR PUBLICATION CHANGE*


## 1. EXECUTIVE FINDING

The Washington County Federal Fiscal Balance Project (WCFFBP) has an independently reproducible IRS gross-collections administrative control for Washington. Its accounting registry deliberately adopts Washington-attributed IRS gross collections less IRS-reported refunds as the preferred QUALIFIED PROVISIONAL net-collections reporting scenario for FFY2018–FFY2024. That convention is reasonable as a clearly labeled measure of net federal tax collections administratively attributed to Washington; it is not a direct estimate of the ultimate economic tax burden borne by Washington residents, workers, or businesses. The present limited review found no demonstrated, quantified Washington-specific geographic-assignment error warranting an adjustment to published annual balances. This absence of demonstrated error is NOT proof that reporting-address distortions are immaterial.


## 2. DEFINITION OF THE MEASURE

- **IRS gross collections:** the IRS-published collections geographically attributed to Washington, encompassing multiple tax categories.
- **IRS refunds issued:** IRS-published refunds, including interest and certain payments/credits that are not necessarily repayments of taxes previously collected.
- **Preferred provisional IRS net collections = IRS gross collections minus IRS refunds issued.**
- **Statewide balance sign convention:** federal inflows attributed to Washington minus federal outflows attributed to Washington.
These are administrative accounting constructs. Avoid unqualified descriptions such as 'corporate taxes extracted from Washington's economy' or 'tax burden borne by Washington residents.'


## 3. TAX CATEGORY AND REFUND SEMANTICS — REQUIRED FOR ALL FOLLOW-ON REPORTS

- **a.** IRS individual income tax collections: a distinct administrative receipts category, not all taxes economically borne by individuals.
- **b.** IRS individual income tax refunds: distinct from business refunds; published totals for certain years include Economic Impact Payments and advance Child Tax Credit amounts nested within refund reporting. Do not add nested components again.
- **c.** IRS business income tax collections: the IRS administrative category; do not relabel as corporation income taxes without confirming category scope. The broader category can include unrelated business income taxes.
- **d.** IRS business income tax refunds: keep separate from individual refunds and refundable-credit/payment categories.
- **e.** Federal corporation income tax receipts: a different national fiscal receipts concept, particularly when derived from OMB and allocated by an economic-incidence formula.
- **f.** IRS total collections/refunds: aggregates of categories; distinguish gross, refunds, and net. Do not imply a category-specific allocation when only aggregate figures have been certified.
An earlier comparison of $91.472 billion net IRS business-income-tax collections with $64.851 billion OMB/BEA-allocated corporation-income-tax receipts for FFY2018–FFY2024 is NOT a validated like-for-like corporate tax discrepancy.


## 4. DOCUMENTED VALIDATION AND GOVERNANCE

IRS gross-collections semantic certification v0.1 reports PASS for nested components, top-level totals, and existing WCFFBP reporting controls for FY2015–FY2024, with $0.00 reporting differences. Certification expressly excludes economic incidence, refund treatment, and final ledger authorization.
The v0.3.3 registry IRS_AUTHORIZATION_DECISION.md authorizes FY2018–FY2024 IRS gross collections as QUALIFIED_PROVISIONAL_OUTFLOW administrative controls, not final resident tax incidence.
The v0.3.3 registry IRS_NET_COLLECTIONS_PROVISIONAL_DECISION.md (ETL-239B1G3) adopts net collections as the preferred qualified provisional reporting scenario, retaining gross as a control; it withholds canonical ledger authorization.
The earlier IRS_REFUND_AND_DRAFT1_LINEAGE_REVIEW.md (ETL-238B7) documents an older stage before later refund reconstruction and does not supersede ETL-239B1G3. Its unrecovered DRAFT-1 chart calculation should not be confused with later ETL-244B published reconciliation.


## 5. SEVEN-YEAR IRS ACCOUNTING CONTROLS, FFY2018–FFY2024

- **Gross IRS collections attributed to Washington:** $877,156,759,000.00
- **IRS refunds issued (including interest):**   $92,094,284,000.00
- **Preferred provisional IRS net collections:** $785,062,475,000.00
These are aggregate IRS amounts, NOT solely corporate or business taxes.
The registry's earlier net-basis provisional balance of -$208,011,901,827.46 used an earlier inflow coverage set. The later published balance of approximately -$198,142,554,212.81 incorporates subsequent inflow work (including Medicare Part D). The older balance is not a contradiction and must not be presented as the current published result.


## 5A. ANNUAL BUSINESS/CORPORATION TAX METHOD COMPARISON, FFY2018–FFY2024

The following figures are presented as a methodological comparison, not as directly interchangeable measurements. The first column uses IRS net BUSINESS INCOME TAX collections attributed to Washington (gross business-income-tax collections less business-income-tax refunds), not individual income taxes or total IRS collections. The second uses the ETL-172H-4 reconstructed allocation of national OMB CORPORATION INCOME TAX receipts to Washington, applying 75% BEA capital-income share and 25% BEA wages-and-salaries share. ETL-172H-4 uses final calendar-year t BEA shares with federal fiscal-year t national receipts and does not purport to reproduce Rockefeller's historical data vintages.

| FFY | IRS WA net business income taxes | ETL-172H-4 allocated corporation income taxes | IRS minus allocated |
| --- | --- | --- | --- |
| 2018 | $4.057B | $5.403B | -$1.346B |
| 2019 | $8.227B | $6.272B | +$1.955B |
| 2020 | $7.179B | $5.853B | +$1.327B |
| 2021 | $10.570B | $10.058B | +$0.512B |
| 2022 | $14.891B | $11.574B | +$3.317B |
| 2023 | $23.761B | $11.380B | +$12.381B |
| 2024 | $22.787B | $14.311B | +$8.476B |
| TOTAL | $91.472B | $64.851B | +$26.621B |

The seven-year totals at full underlying precision are IRS net business income taxes $91,472,114,000.00, allocated corporation income taxes $64,850,672,834.83, and numerical difference $26,621,441,165.17. The figures are shown to three decimals in billions for readability; annual differences are calculated from the displayed cent-precision values. The previously certified aggregate ETL-172H-4 control is $64,850,672,834.83, one cent above the sum of annual figures reproduced here; the aggregate difference using that control is $26,621,441,165.17. This one-cent presentation/control difference should be reconciled against the original machine-readable ETL output before treating the annual comparison as newly certified.

**Interpretation:** These are different tax categories and different attribution concepts. A difference is not itself a measured reporting-address error, a validated like-for-like corporate-tax gap, or a demonstrated explanation for the difference between WCFFBP and Rockefeller published statewide balances. The allocation is Rockefeller-inspired but independently reconstructed under ETL-172H-4; it is not a verified Rockefeller-published Washington annual series. No inference about Rockefeller's actual published fiscal balance should be drawn without aligning category scope, source vintage, year convention, and all other receipt/expenditure components.

**Source Trace:** IRS business-tax annual values and gross-minus-refund category treatment from the earlier ETL-251A corporate-tax review; ETL-172H-4 annual allocations from data/raw/bea/corporate_incidence/validation/washington_corporate_income_tax_receipts_v0_1/certification_report.txt, reproduced in 251a9_corporate_tax_certification_review.txt. These numbers were not re-extracted from primary IRS worksheets in ETL-251B1/B2; retain this as a previously reconstructed comparison, not a new certification.


## 5B. RATIONALE FOR RETAINING IRS-BASED COLLECTIONS RATHER THAN SUBSTITUTING ETL-172H-4

WCFFBP selected IRS-reported collections attributable to Washington State, adjusted for IRS-reported refunds, as its preferred QUALIFIED PROVISIONAL federal tax revenue measure because the resulting series represents an identifiable and independently reproducible administrative accounting quantity. The project certified the gross-collections source semantics and reporting reconciliation, and subsequently documented the net-collections convention and its qualifications. The decision is a reporting choice, not final canonical ledger authorization.

The project separately reconstructed an alternative method for allocating national federal corporation income tax receipts to Washington using OMB national receipts and BEA state economic indicators. Under ETL-172H-4, 75 percent of the allocation weight is assigned to capital-income share and 25 percent to wages-and-salaries share. The calculation is reproducible under its specified inputs and formula, but its weights are economic-incidence assumptions, not observations of IRS collections geographically attributed to Washington. ETL-172H-4's validation of source inputs and arithmetic did not authorize substitution into the WCFFBP receipts ledger.

The reviewed decisions do not establish that the 75/25 allocation is uniquely appropriate for WCFFBP's administrative accounting objective. Nor do numerical differences between the allocated estimates and IRS-reported collections, standing alone, demonstrate an error in IRS administrative reporting. The IRS BUSINESS INCOME TAX category and OMB CORPORATION INCOME TAX receipts are not established as directly equivalent. Their differences cannot be assigned exclusively to geographic allocation without reconciling category scope, refunds, timing, and source vintages. Individual income tax collections and refunds must remain separate from business-income-tax collections and refunds in all such comparisons.

Accordingly, WCFFBP retained IRS-based net collections as its preferred qualified-provisional administrative revenue measure and preserved the OMB/BEA corporate allocation as a separate, non-additive methodological comparison. This is not a conclusion that the alternative incidence approach is inherently invalid, nor that IRS reporting addresses reveal where the ultimate tax burden falls. Geographic reporting conventions, refund composition, and other material limitations remain disclosed.


### Evidence And Status Of Rationale:

- Explicit registry authorization: accounting_registry/v0_3_3_working/IRS_AUTHORIZATION_DECISION.md (qualified provisional gross administrative outflow; ETL-225K, ETL-227C, ETL-227C2 checks).
- Explicit later reporting decision: accounting_registry/v0_3_3_working/IRS_NET_COLLECTIONS_PROVISIONAL_DECISION.md (ETL-239B1G3; net preferred, gross retained as control, canonical authorization withheld; ETL-239B1E8, ETL-239B1E9, ETL-239B1E9F, ETL-239B1G1, ETL-239B1G2 cited).
- Source semantics: data/raw/irs/gross_collections/validation/semantic_certification_v0_1/certification_report.txt (FY2015-FY2024 PASS, excluding incidence and refund certification).
- Alternative allocation: data/raw/bea/corporate_incidence/validation/washington_corporate_income_tax_receipts_v0_1/certification_report.txt (ETL-172H-4, as summarized in earlier ETL-251A9 review; source document not independently re-opened during ETL-251B1/B2).
- Interpretive distinction: the reasoning about suitability of the 75/25 weighting for WCFFBP's objective is a methodological inference from the documented measures, not a separately certified historical finding about the original authors' motives.


## 5C. COMPARATIVE EVALUATION: SHOULD ETL-172H-4 REPLACE THE PUBLISHED IRS COMPONENT?

The following evaluation considers the methods on their own merits. It is a decision framework, not a newly certified finding that either method more accurately measures Washington's ultimate economic tax burden. In particular, ETL-172H-4 is a model of allocated national corporation income tax receipts, while the published IRS component is an administrative net-collections measure. The categories must be reconciled before any replacement or quantified fiscal-balance adjustment.

| CRITERION | CURRENT IRS-BASED METHOD | ETL-172H-4 ALLOCATION |
| --- | --- | --- |
| Direct administrative observations | Published Washington-attributed IRS collections and refunds | National corporation receipts observed; state share modeled |
| Reproducibility | Gross source and reporting checks passed; net decision traced | Source inputs and specified calculation reproducible |
| Geographic economic attribution | Reporting-address conventions may misplace multistate activity | Explicit economic allocation, but depends on proxy validity |
| Economic-incidence assumptions | Not required to report administrative collections | 75% capital / 25% labor weighting requires justification |
| Corporate tax category comparability | IRS business-income-tax category; refunds separately treated | OMB corporation-income-tax receipts; not yet scope-matched |
| Fiscal/calendar period consistency | IRS fiscal-year administrative series | Federal fiscal-year receipts with calendar-year BEA shares |
| Consistency with published WCFFBP basis | Already used in qualified-provisional balance | Substitution would change the measurement construct |
| Authorization status | Preferred qualified-provisional reporting scenario | Validated alternative; not authorized for ledger substitution |


### Reasons That Could Favor Etl-172H-4


## 1. A company's IRS reporting address or principal office may be in Washington even when much of its economic activity occurs elsewhere; the reverse can also occur. An economic allocation might better capture interstate economic relationships than administrative filing geography.


## 2. Allocating a defined national corporation-income-tax receipts total by state economic indicators creates a transparent national-total control, provided the shares are consistently normalized.


## 3. The method offers an explicit, independently reproducible way to test the sensitivity of Washington's assigned corporate tax contribution to geographic attribution assumptions.

These are potential advantages, not proof of improved accuracy for Washington. The current evidence does not quantify net reporting-address distortion or validate the allocation as the best measure of ultimate incidence.


### Reasons Against Immediate Substitution


## 1. The 75/25 capital/labor weights are assumptions about tax incidence. Their empirical suitability for Washington and the years examined has not been established.


## 2. State capital-income and wage shares are imperfect geographic proxies for the actual persons or entities bearing corporate tax costs; economic incidence can involve capital owners, workers, consumers, and cross-border effects.


## 3. IRS BUSINESS INCOME TAX collections net of business refunds and OMB CORPORATION INCOME TAX receipts are not demonstrated to be equivalent tax categories. Individual income taxes and individual refunds are not part of this corporate substitution question and must remain distinct.


## 4. ETL-172H-4 combines fiscal-year national receipts with calendar-year state indicators. Timing and source-vintage differences must be reconciled before treating the results as like-for-like.


## 5. Replacing an administrative component with an incidence-model estimate could create a hybrid fiscal-balance measure. That may be defensible only after an explicit definition of the accounting objective and a consistent treatment of other components.


## 6. ETL-172H-4 has not been authorized for canonical-ledger inclusion or substitution in the published qualified-provisional balance.


### Decision And Conditions For Reconsideration

Retain the existing IRS-based net-collections component in the published FY2018-FY2024 balance. Preserve ETL-172H-4 as a separately labeled, non-additive sensitivity analysis. The approximately $26.621 billion seven-year numerical difference between the currently compared business-tax and corporation-tax series is not an authorized adjustment to the fiscal balance because the categories and attribution constructs are not yet aligned.
Before proposing substitution: (i) establish a like-for-like corporation-income-tax category bridge, including refund treatment; (ii) test the 75/25 weights and BEA geographic proxies against plausible alternatives; (iii) address fiscal/calendar alignment and geographic reporting conventions; (iv) quantify annual effects and uncertainties; and (v) obtain explicit registry, ledger, and publication authorization. This section adds a comparative evaluation; it does not alter the ETL-251B closeout disposition.


## 6. GEOGRAPHIC ATTRIBUTION — LIMITS OF THE FINDING

IRS state collections are classified under IRS administrative reporting conventions. Business taxpayer addresses or principal-office locations can differ from the geography of multistate economic operations or ultimate incidence. Therefore Washington-attributed collections should not be represented as a comprehensive measurement of economic taxes borne in Washington. The two uploaded ETL-251B diagnostics did not independently extract and certify the official IRS state-classification footnote or quantify the net effect of business reporting addresses on Washington. This report makes no numerical claim about that effect.


## 7. REFUND AND TIMING LIMITATIONS

Refund totals may include refundable credits, Economic Impact Payments, advance Child Tax Credit payments, and interest. Such items are deducted once in the adopted administrative net convention; not every component is repayment of previously collected tax. Gross collections and refunds can concern different underlying tax periods. COVID-era composition affects FY2020–FY2022 comparisons. Earlier overlap reviews reduced but did not eliminate all possible cross-family duplication. The preferred net measure remains QUALIFIED PROVISIONAL.


## 8. INDEPENDENT REASONABLENESS TEST

The approach has a clear object (IRS administrative collections attributed to Washington), identified official source data, a documented net convention, tested source arithmetic, and explicit limits. Those characteristics support its reasonableness and reproducibility as an administrative fiscal reporting measure independently of Rockefeller's allocation approach. They do not establish that it measures geographic economic incidence, that no significant reporting-location bias exists, or that the full federal fiscal balance has achieved final ledger certification. Other methods may reasonably answer different accounting questions.


## 9. DISPOSITION AND REOPENING CRITERIA

CLOSE the limited ETL-251B inquiry with qualified findings. RETAIN the current published FFY2018–FFY2024 balances and charts unchanged. DO NOT authorize new canonical ledger entries or modify source-family classifications on the strength of this review.
Reopen only upon credible evidence of (i) a material Washington-specific geographic attribution error or reporting-rule change; (ii) a category-definition mismatch materially affecting published interpretation; (iii) a material refund classification or duplicate-counting error; or (iv) a reproducibility discrepancy in certified inputs or published annual figures. Any proposed revision requires a documented quantified bridge, registry review, approval, and separately versioned publication.


## 10. SOURCE CHAIN / REPRODUCIBILITY

User-supplied diagnostic: 251b1_irs_geographic_attribution_screen.txt (ETL-251B1), inventory of 3,055 tracked files and 14 filename-selected candidates; this was a selective inventory, not exhaustive proof of absence.
User-supplied diagnostic: 251b2_irs_accounting_decision_review.txt (ETL-251B2), full text of four governing documents.
Original repository sources as reproduced in ETL-251B2:
- accounting_registry/v0_3_3_working/IRS_AUTHORIZATION_DECISION.md
- accounting_registry/v0_3_3_working/IRS_NET_COLLECTIONS_PROVISIONAL_DECISION.md
- accounting_registry/v0_3_3_working/IRS_REFUND_AND_DRAFT1_LINEAGE_REVIEW.md
- data/raw/irs/gross_collections/validation/semantic_certification_v0_1/certification_report.txt
Official IRS geographic classification documentation was identified as a follow-up pointer in ETL-251B1 but NOT independently verified in this closeout; the reporting-location limitation is therefore carried as a disclosed qualification.


## 11. CHANGE CONTROL

This report is an analytical artifact prepared from supplied evidence. It is not a repository commit, registry update, ledger certification, external peer review, or publication change. Formal archival in the repository requires a separate authorized step.

---
*End of report.*
