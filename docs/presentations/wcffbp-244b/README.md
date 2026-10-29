# WCFFBP interactive presentation — ETL-244B (working, 2026-10-28)

## Four views

Open `index.html` locally, or host the entire directory using GitHub Pages. It is **self-contained**: all data, CSS, and JavaScript are embedded in the HTML, with no external runtime dependencies.

1. Federal inflows vs net IRS collections (Provisional Reference).
2. Eleven-component annual inflow composition.
3. COVID-tagged assistance **subset** (ETL-238A / ETL-236I tags); incomplete award-level coverage, not all COVID spending.
4. DoD and DOE procurement obligations (not cash or additional inflows). Hanford is explicitly **unquantified** pending a verified site-specific series.

## Reproducibility

`build_dashboard.py` reads preserved source extracts in `evidence/` and `data/243e1_first_draft_annual_balance.csv`, validates all seven annual 11-component inflow totals and balance identities at exact cent precision, and regenerates `index.html` and `data/244b_chart_data.csv`. Run from this folder with `python build_dashboard.py`. The `evidence/` files preserve the precise ETL-244A4 and ETL-244A5 user-provided diagnostic outputs. The original two existing graphic versions and original stacked chart are preserved as separate HTML files.

ETL lineage: 238A -> 238B8 -> 239B1G2 (IRS net) + 242A5 (Part D) -> 243E1 -> 244A5 -> 244B. No database writes, source data updates, or canonical ledger authorizations.

## Qualifications

Qualified provisional, **not a certified cash-flow ledger**. SSA is annualized December snapshots, Medicare A/B/C calendar-year, Part C 2024 partial January–September, VA and Medicaid use source fiscal-year bases, and assistance uses obligations. IRS refunds are a qualified provisional net adjustment. DoD and DOE obligations are context-only, with overlap/economic incidence unresolved. COVID/IIJA tags may overlap; COVID-tagged amounts cover a subset of assistance. The Hanford number has not been independently verified.

## Suggested GitHub Pages publication

Place this directory under `docs/presentations/wcffbp-244b/` in the repository. If Pages is configured to publish `main` `/docs`, the eventual URL is:

`https://repatriatewa.github.io/washington-county-federal-fiscal-balance/presentations/wcffbp-244b/`

This is a **predicted** URL, not an active verified link. Check Pages settings and test the deployed page before emailing. If Pages publishes a different branch or folder, use the actual URL shown in Settings > Pages. Commit the whole directory, including `build_dashboard.py`, source extracts, and generated HTML; never commit only the chart.

## Revision discipline

Keep this release folder immutable after sharing. Make a new dated/versioned folder for future public revisions, or use a Git tag and record the commit hash shared with collaborators. Every new chart should have a generator, source-data snapshots, reconciliation assertions, methodology notes, and an explicit publication status. Verify that the Git commit contains all these files and that the Pages deployment matches the committed HTML.
