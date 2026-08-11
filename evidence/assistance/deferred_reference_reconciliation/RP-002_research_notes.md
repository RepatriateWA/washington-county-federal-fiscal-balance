# RP-002 — Extraordinary Funding (DEFC) Reference Reconciliation

## Purpose

This work package documents the research, evidence, and final classification of Disaster Emergency Fund Codes (DEFCs) observed in USAspending Assistance data that were not yet represented in the project reference dimension.

Each classification shall be supported by authoritative federal documentation and shall be traceable to its source.

No code shall be added to the reference table without supporting evidence.

## RP-002 Classification Findings

The remaining unresolved DEFC values were reconciled using:

1. The official DEFC descriptions preserved in the USAspending Assistance
   source downloads;
2. The U.S. Treasury definition of Disaster Emergency Fund Code (DEFC);
3. USAspending.gov methodology identifying the DEFC values used for its
   COVID-19 and Infrastructure Investment and Jobs Act tracking.

Treasury defines DEFC as distinguishing budgetary resources according to
disaster, emergency, wildfire suppression, or no such designation.

The USAspending methodology identifies L, M, N, O, P, U, and V with the
COVID-related tracking covered by the methodology and Z and 1 with
Infrastructure Investment and Jobs Act tracking.

None of the twelve RP-002 unresolved codes is among those COVID/IIJA codes.

### Final Classification

| DEFC | Official Description | Funding Family | Extraordinary | COVID | IIJA | Confidence |
|------|----------------------|----------------|---------------|-------|------|------------|
| 2 | Emergency P.L. 117-70 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| 5 | Wildfire Suppression P.L. 117-103 | WILDFIRE_SUPPRESSION | TRUE | FALSE | FALSE | HIGH |
| 7 | Emergency P.L. 117-159 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| A | Emergency P.L. 115-56 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| AAA | Emergency P.L. 117-180 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| AAF | Emergency P.L. 118-42 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| AAJ | Emergency P.L. 118-50 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| I | Emergency P.L. 116-94 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| K | Emergency P.L. 116-113 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| R | Emergency P.L. 116-260 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |
| T | Wildfire Suppression P.L. 116-260 | WILDFIRE_SUPPRESSION | TRUE | FALSE | FALSE | HIGH |
| W | Emergency P.L. 117-31 | OTHER_EMERGENCY | TRUE | FALSE | FALSE | HIGH |

### Methodological Note

A Public Law must not itself be treated as a sufficient COVID
classification. Different DEFC values associated with the same Public Law
may carry different designations.

Accordingly, COVID, IIJA, emergency, disaster, and wildfire classifications
shall be assigned at the DEFC-code level.

Transaction-level DEFC associations shall also not be interpreted as proof
that the transaction-level obligation itself was funded by that DEFC.
USAspending documents an important limitation in linking DEFC-tagged
prime-award summary spending to transaction-level award records.