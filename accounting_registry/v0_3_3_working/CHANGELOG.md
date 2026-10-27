## Current working checkpoint: v0.3.3 ? ETL-229

- Status: validated working registry; not a final fiscal balance.
- 23 source families; 161 annual family-year observations.
- 21 of 147 potential additive ledger observations authorized.
- IRS gross collections: seven qualified provisional outflows,
  FY2018?FY2024, totaling $877,156,759,000.
- Medicaid: seven qualified provisional inflows,
  FY2018?FY2024, totaling $73,016,313,670.
- CHIP: seven qualified provisional inflows,
  FY2018?FY2024, totaling $1,137,550,029.
- CHIP source: CMS-21 CHIP plus MCHIP federal-share expenditures;
  MCHIP 20% financing adjustments excluded.
- USAspending AL 93.767: tested transactions excluded as duplicates
  or withheld unresolved; no separate additive authorization.
- Independent regression validation: ETL-229C PASS.
- Existing IRS and Medicaid authorizations unchanged.
- No county allocation or complete statewide balance certified.

See IRS_AUTHORIZATION_DECISION.md,
MEDICAID_AUTHORIZATION_DECISION.md, and
CHIP_AUTHORIZATION_DECISION.md.

---

## Current working checkpoint: v0.3.2 ? ETL-228

- Status: validated working registry; not a final fiscal balance.
- 23 source families; 161 annual family observations.
- 14 of 147 potential ledger observations authorized.
- IRS gross collections: seven qualified provisional outflows,
  FY2018-FY2024, totaling $877,156,759,000.
- Medicaid: seven qualified provisional inflows,
  FY2018-FY2024, totaling $73,016,313,670.
- Medicaid source: CMS MBES federal-share Total Net Expenditures.
- USAspending AL 93.778: duplicate exclusion for tested transactions.
- No county allocation or complete statewide balance certified.
- Independent regression validation: ETL-228D PASS.
- Next family: CHIP, subject to its own authorization review.

See IRS_AUTHORIZATION_DECISION.md and
MEDICAID_AUTHORIZATION_DECISION.md.

---

# Registry changelog

## v0.2 working candidate — 2026-10-21
- Preserved 21 original source-family rows and added `MEDICARE_CORE` as a non-additive reporting parent.
- Separated source availability, accounting certification, and ledger authorization fields.
- Used the preferred wage source-view names documented in the statewide readiness audit; local database existence remains unverified.
- Preserved 9 original evidence references; added 2 family-specific crosswalk rows; distinguished reviewed GitHub report content from pending review.
- Created 154 source-year rows for 22 families across 2018–2024.
- Populated only 28 Medicare source-calendar-year amount observations recovered from the original accounting integration report.
- Did not infer other annual values from aggregate audit totals, nor authorize ledger inclusion.
- **Open question:** MSSP economic-overlap report distinguishes positive EarnSaveLoss from FFS claim payments; reconcile this with historical EXCLUDE_DUPLICATE policy before treating disposition as fully settled.
- **Open question:** Verify 2018–2019 assistance transaction-year coverage separately from ETL-221U policy-mapping certification.
- **Open question:** Verify 2024 Medicare Part C/D completeness and Part D partial-dollar coverage; preserve county suppression/missingness.

## v0.2.1 evidence checkpoint — 2026-10-21
- Entered seven IRS gross collection and seven VA GDX statewide values from the user-provided ETL-222B checkpoint, explicitly marked not reverified against the repository report.
- Did not insert the ETL-222B tracked-expenditure subtotal as an independent family because it aggregates Medicaid, CHIP, OASDI and Original Medicare and would duplicate them.
- Explicitly flagged MSSP conflicting source-policy and economic-overlap conclusions. The latter certifies positive EarnSaveLoss ADDITIVE_IN_PRINCIPLE but withholds Washington dollars and cash/FFY timing. This does not authorize addition to the ledger.

## v0.2.2 — statewide audit annual schedule recovered
- Added 47 source-year amount observations: seven each for OASDI, Medicaid, CHIP, civilian wages, military wages and procurement, plus five FY2020–2024 gross assistance observations.
- Values transcribed from `evidence/statewide/draft_1/statewide_readiness_v0_2.txt` and tagged as prior-audit reported, not independently database-recertified.
- FY2018–2019 assistance gross amount cells remain empty because this older audit did not provide them; ETL-221U policy coverage does not establish gross annual totals.
- Gross USAspending assistance and procurement remain withheld; no additive residual is inferred.
- OASDI annualized December snapshot is not treated as FFY cash benefits; wages remain OMB-controlled allocations.

## v0.2.3 — historical RRB/HCV bridge evidence
- Recovered original ETL-205, ETL-209D, ETL-209E, and ETL-221U7 SQL directly from GitHub; no local DB execution.
- Confirmed historical RRB FY2018–2019 combined obligations $519,180,042.71, partitioned into $515,006,959.71 additive-classified and $4,173,083.00 withheld. These are net obligations, not independently verified cash benefits.
- Confirmed historical HCV AL 14.871 combined additive-classified obligations $1,237,486,410.00. Combined HCV/RRB bridge 4,895 rows and $1,756,666,452.71.
- Created `historical_combined_controls.csv` rather than falsely distributing combined values between FY2018 and FY2019.
- Existing RRB family retained, with corrected obligation measure and provenance. Annual cells intentionally remain empty pending split.
- Next action: run existing read-only verification SQL on local database and capture output; note ETL-209D/209E use temporary tables inside normal transactions and end with ROLLBACK, so do not wrap in `BEGIN READ ONLY`.

## v0.2.4 — local ETL-209E verification
- User-supplied local PostgreSQL stdout and stderr show ETL-209E PASS and ROLLBACK; stderr notice is a PowerShell native-command formatting artifact, not a SQL failure.
- Added HOUSING_CHOICE_VOUCHERS family (AL 14.871), with seven year slots; only FY2018–FY2019 amounts populated.
- Entered FY2018/FY2019 HCV additive obligations 604856102.00/632630308.00 and RRB additive obligations 255582541.10/259424418.61.
- Preserved RRB withheld 2077269.00/2095814.00 in `historical_annual_bridge_controls.csv`, not as additive amounts.
- Confirmed zero unclassified rows and zero policy collisions for each program-year group.
- No cash-disbursement certification or ledger authorization implied.

## v0.2.5 — HCV seven-year evidence completed
- Recovered ETL-184 source-policy migration and its certified FY2020–FY2024 HCV obligations: 722577370.00; 785519054.00; 802217748.00; 990811243.74; 1006955221.91 USD (sum $4,308,080,637.65).
- Joined to FY2018 and FY2019 HCV annual amounts independently reproduced from ETL-209E in v0.2.4; HCV now has seven annual observed net-obligation controls, without treating them as cash expenditure or county incidence.
- Recovered ETL-208A and ETL-209W SQL. ETL-209W is a frozen post-VA historical bridge with fixed earlier controls, so it should not be assumed to certify the newer ETL-221U disposition state.
- Next: use ETL-221U7 or an updated read-only current-state bridge to certify FY2018–2019 all-program disposition totals, rather than rerun historical migrations or presume stale controls remain valid.

## v0.2.6 — ETL-221U7 independent local verification
- Local ETL-221U7 stdout confirms 17 source policies, 33 program mappings, 7 EXCLUDE_DUPLICATE, 14 INCLUDE_ADDITIVE, 3 REFERENCE_ONLY, 9 WITHHOLD_UNRESOLVED program dispositions; zero invalid linkages/collisions; completed ROLLBACK.
- Recovered 8 FY2018–2019 disposition-year observations into historical_program_mapping_controls.csv. Totals: 2018 $1,400,346,198.98; 2019 $1,726,961,155.56; both mapped scope only.
- Kept all-assistance gross amount blank in annual_accounting_matrix.csv because the mapped program population is not the complete transaction universe. No addition of mapped amount to HCV/RRB without overlap audit.
- No database or repository writes; this is an offline working candidate.

## v0.2.7 — ETL-223A full historical assistance diagnostic
- User-executed read-only SQL covered 100,426 FY2018 and 106,917 FY2019 assistance transactions, with zero both-layer policy matches or differing dispositions.
- Gross FY2018 source net obligations $46,583,743,538.62; FY2019 $50,513,498,984.96. These are source obligations, not ledger-authorized expenditure.
- Additive-classified FY2018 $6,846,554,251.80; FY2019 $7,349,955,510.22. Unclassified FY2018 $4,530,231,729.37; FY2019 $4,789,685,892.75.
- Preserved ten annual disposition partitions in `historical_current_state_assistance_controls.csv`; populated two previously blank gross source controls.
- Diagnostic is not an independent hard certification gate, and the audit does not establish cash timing or county incidence.


## v0.3.0 working consolidation — 2026-10-21
- Adopted canonical sign: inflows minus outflows; negative means net federal dollars removed from Washington's economy.
- Retained v0.2.7 source and annual files, added a single ledger authorization scaffold and explicit model specification.
- Added ETL-224G historical assistance geographic controls and ETL-223A-to-224G difference tracking without assuming causality.
- No PostgreSQL writes, no Git changes, no ledger authorization.


## v0.3.1 working — ETL-225L1 statewide evidence verification

- Re-executed the existing ETL-216C statewide source eligibility audit (ETL-225J); baseline controls passed.
- Re-executed the existing ETL-222B statewide component matrix (ETL-225K); seven annual observations reproduced for FY2018–FY2024.
- Confirmed zero IRS revenue differences against the existing baseline view.
- Updated 14 IRS collections and VA GDX annual coverage statuses from prior checkpoint not reverified to current database control reproduced.
- Preserved all observed amounts, accounting statuses, and ledger authorizations.
- Medicare remains subject to calendar-year, completeness, and authorization restrictions.
- CHIP, Medicaid, SSA OASDI, and federal wage evidence updates remain to be processed separately.
- No database writes or new accounting authorizations.

## v0.3.2 working — ETL-225M federal wage evidence verification

- Reproduced seven FY2018–FY2024 federal civilian wage allocations directly from analysis.v_wa_federal_wage_allocation.
- Reproduced seven FY2018–FY2024 federal military wage allocations from the same existing database view.
- Confirmed civilian plus military allocations equal combined federal wage allocations for every year, with $0.00 differences.
- Preserved MEDIUM allocation confidence for all seven years.
- Updated coverage_status and evidence_path for exactly 14 wage observations in annual_accounting_matrix.csv.
- Independently verified the changes using ETL-225M4.
- Confirmed zero unexpected changes, zero observed amount changes, and zero accounting or ledger authorization changes.
- Retained REQUIRES_FAMILY_SCOPED_REVIEW and NOT_YET_AUTHORIZED.
- No database writes or new accounting authorizations.






## v0.3.3 working � ETL-225N Medicaid/CHIP evidence verification

- Verified 14 annual Washington CMS expenditure observations:
  Medicaid and CHIP, federal fiscal years 2018�2024.
- Reproduced all 14 observed amounts exactly from PostgreSQL
  reporting views, with one reporting row per family-year.
- Confirmed Medicaid MBES Total Net Expenditures federal-share
  controls and CHIP/MCHIP additive federal-share controls.
- Preserved exclusion of MCHIP financing adjustments.
- Reused ANALYSIS-218-v1 Qualified PASS evidence for tested
  USAspending overlap dispositions and reporting lineage.
- Updated only annual matrix coverage_status and evidence_path.
- Preserved all amounts, time bases, accounting statuses,
  ledger authorizations, and other registry fields.
- ETL-225N6 verification: PASS; 14 target rows; zero unexpected
  field changes; zero ledger authorization changes.
- Evidence-verified annual observations: 42 of 161.
- No canonical ledger authorization or statewide balance
  certification implied.

## v0.3.4 working - ETL-225O SSA OASDI evidence verification

- Verified seven Washington SSA OASDI observations, 2018-2024.
- Reproduced all seven registry amounts exactly from the current
  PostgreSQL reporting view.
- Confirmed three reporting components and 39 published county
  TOTAL observations per year.
- Independently reproduced authoritative SSA published TOTAL
  controls from the underlying benefit_payments table.
- Reconciled all seven reporting-versus-published differences
  to the certified SSA source-rounding evidence.
- Reused EP-SSA-OASDI-001, certified with 17 validation checks
  passed and zero failed.
- Preserved ANNUALIZED_DECEMBER_SNAPSHOT measurement semantics.
- These observations are not observed federal fiscal-year
  cash expenditures.
- Updated only coverage_status and evidence_path in the
  annual accounting matrix.
- Preserved observed amounts, accounting statuses, and all
  ledger authorizations.
- Evidence-verified annual observations: 49 of 161.
- No canonical ledger authorization or statewide fiscal
  balance certification implied.

## v0.3.5 working - ETL-225Q Medicare FFS A/B verification

- Verified seven Washington Original Medicare FFS A/B
  calendar-year observations, 2018-2024.
- Reproduced all seven registry amounts exactly from
  cms.medicare_core_state_year.
- Confirmed Washington state linkage and 39 county
  observations for every year.
- Confirmed seven unique annual database observations.
- Preserved the existing source SHA-256 provenance.
- Reused the certified CMS Medicare accounting-integration
  profile without reopening the underlying reconstruction.
- Preserved CALENDAR_YEAR measurement semantics.
- Confirmed FFY conversion remains unauthorized.
- Updated only coverage_status and evidence_path in the
  annual accounting matrix.
- Preserved observed amounts, accounting statuses, and
  all ledger authorizations.
- Standardized evidence-verified observations: 56 of 161.
- Two previously verified HCV observations remain separately
  classified outside this standardized count.
- No canonical ledger authorization or statewide fiscal
  balance certification implied.

## v0.3.6 working - ETL-225R Medicare Part C verification

- Verified seven Washington Medicare Part C annual
  observations for calendar years 2018-2024.
- Reproduced the seven registry dollar amounts from
  cms.medicare_core_state_year to exact cent precision.
- Preserved the source reconstruction's additional
  fractional-cent precision in reconciliation evidence.
- Confirmed six complete calendar-year observations
  for 2018-2023.
- Explicitly retained the January-September partial
  reporting period for 2024.
- Confirmed Washington state linkage, source SHA-256,
  and existing CMS accounting-integration provenance.
- Preserved original CALENDAR_YEAR measurement semantics.
- Confirmed FFY conversion remains unauthorized.
- Updated only coverage_status and evidence_path in
  the annual accounting matrix.
- Preserved observed amounts, accounting statuses,
  and all ledger authorizations.
- Standardized evidence-verified observations: 63 of 161.
- Two previously verified HCV observations remain
  separately classified outside this standardized count.
- No canonical ledger authorization or statewide fiscal
  balance certification implied.

## v0.3.7 working - ETL-230E VA GDX authorization

- Authorized seven Washington VA GDX annual expenditure controls,
  FY2018-FY2024, as QUALIFIED_PROVISIONAL_INFLOW.
- Seven-year authorized total: $39,565,398,612.58.
- Reused EP-VA-001 and ETL-219B5 source certification.
- Reused ETL-220D source-policy and reporting-boundary evidence.
- Preserved VA procurement duplicate-exclusion safeguards.
- Withheld unresolved VA assistance from independent addition.
- Did not subtract USAspending obligations from GDX expenditures.
- Preserved qualifications concerning cross-family duplication,
  county economic incidence, and complete fiscal-balance coverage.
- ETL-230E3 independent regression PASS:
  all 140 non-VA canonical ledger rows unchanged.
- Qualified provisional authorizations increased from 21 to 28
  of 147 candidate annual ledger observations.
- No PostgreSQL database or reporting-view modifications.

## ETL-231 - Federal wage authorization review

- Reviewed OMB wage obligations, OPM civilian allocation, and BEA military allocation.
- Confirmed existing ANALYSIS-157-v1, ANALYSIS-158-v1, and ANALYSIS-160-v1 methodology.
- Retained 14 reproduced FY2018-FY2024 wage observations.
- Withheld additive authorization pending accounting-basis and cross-family overlap reconciliation.
- Qualified provisional ledger remains 28 of 147 entries.
- No database writes or annual accounting amount changes.
## ETL-232 - SSA OASDI authorization review

- Reviewed existing SSA source certification and reporting basis.
- Confirmed seven FY2018-FY2024 candidate observations.
- Preserved ANNUALIZED_DECEMBER_SNAPSHOT semantics.
- Withheld additive authorization pending actual FFY payment evidence.
- Preserved existing OASDI USAspending overlap safeguards.
- Retained all seven candidate amounts without modification.
- Qualified provisional ledger remains 28 of 147 entries.
- No database writes or canonical ledger changes.
## ETL-233 - Housing Choice Voucher authorization review

- Reviewed existing FY2018-FY2024 HCV source controls.
- Preserved ETL-184 and ETL-208 additive program-policy treatment.
- Confirmed USAspending net federal action obligation basis.
- Reviewed prior HUD VMS expenditure/use reconciliation.
- Preserved VMS non-addition and county-incidence safeguards.
- Withheld principal-ledger authorization pending expenditure evidence.
- Retained all seven candidate observations without modification.
- Qualified provisional ledger remains 28 of 147 entries.
- No database writes or canonical ledger changes.

## ETL-234 - Railroad Retirement authorization review

- Recovered ETL-189/190 award-level benefit classifications.
- Confirmed FY2020-FY2024 $1,357,308,008.42 obligation control.
- Preserved FY2018-FY2019 additive and withheld partitions.
- Confirmed net federal action obligation accounting basis.
- Preserved SSA/OASDI overlap and nonduplication safeguards.
- Withheld expenditure-ledger authorization.
- No annual matrix, canonical ledger, or database changes.
- Qualified provisional ledger remains 28 of 147 entries.
