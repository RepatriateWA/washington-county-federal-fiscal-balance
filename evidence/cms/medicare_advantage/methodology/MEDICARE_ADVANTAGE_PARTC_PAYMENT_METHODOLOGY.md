# Medicare Advantage Part C Payment Reconstruction Methodology

**Project:** Washington County Federal Fiscal Balance Project (WCFFBP)  
**Component:** Medicare Advantage Part C  
**Geography:** Washington State  
**Methodology status:** VALIDATED — PAYMENT-FIELD INTERPRETATION  
**Historical reconstruction validation:** CY2022 PASS  
**Final Medicare ledger status:** NOT YET STATE LEDGER READY

---

## 1. Purpose

This note documents the methodology used by WCFFBP to reconstruct Medicare
Advantage (MA) Part C payments from CMS Plan Payment Data.

The purpose is to establish, from primary CMS documentation, the mathematical
interpretation of the following county-level Part C fields:

- Average Part C Risk Score
- Average A/B Per Member Per Month (PM/PM) Payment
- Average Rebate PM/PM Payment

This methodology governs interpretation of the payment fields. It does not,
by itself, establish complete Medicare expenditure coverage or final-ledger
eligibility.

---

## 2. Primary CMS Evidence

### 2.1 CMS Plan Payment Data Elements — Payment Year 2022

Source artifact:

`Plan Payment Data Element2022.pdf`

Preserved with the CMS 2022 Plan Payment Data source archive:

`data/raw/cms/medicare_advantage/plan_payment/2022/2022_plan_payment.zip`

CMS states that the files contain summary payment data for Part C and Part D
plans and that CMS releases the summary Part C and Part D payment data after
reconciliation of those payments.

CMS further defines the standardization used in the data:

> Any risk-adjusted payment is standardized to a 1.0 risk score, meaning that
> the included numbers are equal to the average risk-adjusted amount divided
> by the average risk score.

For the county-level Part C file, CMS identifies the following relevant fields:

- Average Risk Score
- Average A/B PM/PM Payment (standardized to 1.0 risk score)
- Average Rebate PM/PM Payment

The CMS documentation explicitly identifies the A/B PM/PM field as
standardized to a 1.0 risk score. It does not identify the Average Rebate
PM/PM Payment field as standardized to a 1.0 risk score.

### 2.2 CMS Final Rule — April 15, 2011

CMS identifies the following rule as the underlying reference for release of
the summary Part C and Part D payment data:

**Medicare Program; Changes to the Medicare Advantage and the Medicare
Prescription Drug Benefit Programs for Contract Year 2012 and Other Changes**

CMS-4144-F  
76 Federal Register 21432  
April 15, 2011

Official GovInfo publication:

`https://www.govinfo.gov/content/pkg/FR-2011-04-15/pdf/2011-8274.pdf`

The rule provides the regulatory and methodological context for release of
Medicare Advantage payment information, including Part C payment amounts,
risk scores, and rebate information.

---

## 3. Reconstruction of the A/B Payment Component

CMS defines a payment standardized to a 1.0 risk score as:

    Standardized Payment =
        Average Risk-Adjusted Payment / Average Risk Score

Therefore, algebraically:

    Average Risk-Adjusted Payment =
        Standardized Payment × Average Risk Score

For the CMS Part C County Payment file, WCFFBP therefore reconstructs the
average A/B PM/PM payment as:

    AB_actual_pmpm =
        AB_standardized_pmpm × average_part_c_risk_score

This equation is a direct algebraic consequence of the CMS definition of
standardization and is not an independently selected WCFFBP adjustment
factor.

---

## 4. Treatment of the Rebate Component

CMS publishes Average Rebate PM/PM Payment as a separate Part C payment
field.

Unlike Average A/B PM/PM Payment, CMS does not designate the rebate field
as "standardized to 1.0 risk score" in the 2022 Plan Payment Data Elements
documentation.

WCFFBP therefore does not apply the average Part C risk score a second time
to the published rebate PM/PM value.

The reconstructed Part C PM/PM amount is:

    part_c_pmpm =
        (AB_standardized_pmpm × average_part_c_risk_score)
        + rebate_pmpm

Accordingly:

    part_c_payment =
        enrollment
        × part_c_pmpm

for the applicable enrollment period.

The published rebate is not multiplied by the average risk score again.

---

## 5. CY2022 Historical Methodological Validation

WCFFBP tested this reconstruction architecture using all twelve months of
calendar year 2022 Washington Medicare Advantage data.

The validation uses:

- CMS 2022 Part C County Payment data;
- monthly CMS CPSC enrollment data;
- monthly CMS contract information;
- monthly CMS SNP comprehensive reports; and
- monthly CMS State/County/Plan enrollment data used for enrollment
  reconciliation and suppression analysis.

All twelve months passed the source-validation architecture.

The reconstruction successfully links published Washington enrollment through
contract, plan, geography, plan type, and SNP dimensions to the applicable
CMS Part C County Payment cells.

The validated CY2022 reconstruction applies to the tested Washington
HMO/HMOPOS and Local PPO Part C population represented by the CMS payment
and enrollment sources.

---

## 6. Enrollment Suppression

CMS enrollment sources contain suppressed observations.

WCFFBP preserves suppressed source values as suppressed. Suppressed values
are not converted to zero and are not represented as recovered CMS values.

For Washington HMO/HMOPOS and Local PPO State/County/Plan enrollment cells
published as ".", the CY2022 reconstruction uses the analytical interval:

    lower bound   = 0
    midpoint      = 5
    upper bound   = 10

The midpoint is used only as a sensitivity-analysis midpoint. It is not an
assertion that the underlying CMS value equals five beneficiaries.

This 0–10 interval is a conservative WCFFBP modeling assumption consistent
with documented CMS small-cell suppression practices. It is not represented
as a CMS-published value.

Source validation and analytical suppression modeling remain separate:

    Source validation:
        preserves and reports what CMS published.

    Reconstruction:
        applies explicitly disclosed analytical bounds where CMS values
        are suppressed.

---

## 7. CY2022 Reconstruction Result

For CY2022, the reconstruction produced:

    CPSC published member-months:
        7,320,015

    SCP published member-months:
        7,379,591

    SCP suppressed target cells:
        8

    SCP member-month analytical bounds:
        lower   7,379,591
        central 7,379,631
        upper   7,379,671

    CPSC residual member-month bounds:
        lower   59,576
        central 59,616
        upper   59,656

    Published-enrollment payment:
        $7,201,202,611.74

    Suppression-corrected payment:
        lower   $7,241,106,325.80
        central $7,259,847,964.35
        upper   $7,384,621,098.48

    Central annual PM/PM:
        $983.77

    Uncertainty interval width:
        $143,514,772.67

    Uncertainty width as percent of central estimate:
        1.976829%

All twelve monthly reconstruction validations passed.

These values constitute a WCFFBP reconstruction from CMS payment and
enrollment components. They are not represented as an independently
published CMS statewide Part C expenditure total.

---

## 8. Accounting and Temporal Boundaries

The CY2022 validation is a calendar/payment-year methodological test.

It is not itself the final federal fiscal year accounting series.

For federal fiscal-year reporting, monthly Medicare Advantage payments must
be aligned to the federal fiscal year:

    FFY t =
        October–December of CY (t - 1)
        + January–September of CY t

Consequently, construction of an FFY2015–FFY2024 Medicare Advantage series
requires source coverage extending at least from CY2014 through CY2024 for
the applicable monthly enrollment and payment-year data.

---

## 9. What This Validation Establishes

The following methodological conclusions are supported:

1. CMS Part C Plan Payment Data are reconciled summary payment data.

2. The published Average A/B PM/PM Payment is standardized to a 1.0
   risk score.

3. CMS defines this standardization as the average risk-adjusted amount
   divided by the average risk score.

4. The corresponding average risk-adjusted A/B PM/PM amount can therefore
   be reconstructed as:

       AB_standardized_pmpm × average_part_c_risk_score

5. The Average Rebate PM/PM Payment is published separately and is not
   identified by CMS as standardized to a 1.0 risk score.

6. WCFFBP therefore adds the published rebate after reconstructing the
   risk-adjusted A/B component and does not risk-adjust the rebate a
   second time.

7. The resulting payment-field architecture has been successfully applied
   across all twelve months of CY2022 for the tested Washington
   HMO/HMOPOS and Local PPO population.

---

## 10. What This Validation Does Not Establish

This methodology note does not establish that:

- the CY2022 reconstructed amount is an independently published CMS
  statewide expenditure control;
- all Medicare Advantage Part C plan/payment categories are represented;
- Medicare Part D expenditures are included;
- Original Medicare and Medicare Advantage have been fully reconciled for
  final fiscal-balance accounting;
- the CY2022 calendar-year reconstruction is already federal-fiscal-year
  aligned;
- Medicare as a whole is ready for inclusion as a complete Washington
  statewide federal inflow category; or
- Medicare is currently STATE LEDGER READY.

Those questions require additional source acquisition, validation,
reconstruction, and accounting reconciliation.

---

## 11. Current WCFFBP Status

### Medicare Advantage Part C payment-field interpretation

**VALIDATED — PRIMARY CMS DOCUMENTATION**

### CY2022 Washington MA Part C reconstruction architecture

**VALIDATED — HISTORICAL METHODOLOGICAL REPLICATION**

### Medicare overall

**VALIDATED — PARTIAL COVERAGE**

Current complete Medicare state-ledger status:

**NOT YET STATE LEDGER READY**

---

## 12. Reproducibility Artifacts

Primary reconstruction code:

`scripts/reconstruct_cms_ma_partc_2022.py`

Source acquisition:

`scripts/acquire_cms_ma_2022_validation_sources.py`

Source validation:

`scripts/validate_cms_ma_2022_validation_sources.py`

CY2022 validation evidence:

`data/raw/cms/medicare_advantage/validation/2022/`

Relevant evidence includes:

- `cms_ma_2022_validation_source_manifest.csv`
- `cms_ma_2022_source_validation_monthly.csv`
- `cms_ma_2022_source_validation_summary.txt`
- `cms_ma_partc_2022_monthly_reconstruction.csv`
- `cms_ma_partc_2022_payment_cells.csv`
- `cms_ma_partc_2022_scp_suppressed_cells.csv`
- `cms_ma_partc_2022_reconstruction_summary.txt`

Repository checkpoint establishing the CY2022 reconstruction:

`e1b38b4 — Validate CY2022 Medicare Advantage Part C reconstruction`