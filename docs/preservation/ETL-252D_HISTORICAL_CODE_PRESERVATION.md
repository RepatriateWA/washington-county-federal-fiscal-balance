# ETL-252D ? Historical Research Code Preservation

## Purpose

This record documents preservation of historical Python and SQL
research scripts recovered during WCFFBP repository housekeeping.

Preservation establishes source availability and byte-level
provenance. It does not certify analytical conclusions, authorize
execution, or establish accounting-ledger eligibility.

## Preservation scope

| Asset category | Count |
|---|---:|
| Python scripts | 65 |
| SQL scripts | 319 |
| Total historical code assets | 384 |

The authoritative asset-level inventory is:

`asset_registry/asset_manifest.csv`

The permanent preservation manifest is:

`docs/preservation/ETL-252D_CODE_MANIFEST.csv`

It is a byte-identical copy of
`252d8a_code_preservation_manifest.csv` and records the
selected 384-file population and original SHA-256 fingerprints.

## Original source integrity

Each preserved source file was checked against:

1. Its registered SHA-256 fingerprint.
2. Its corresponding staged Git blob.
3. The previously verified independent backup.

The original files were not rewritten or reformatted.

## Independent backup

The historical working-asset backup is located at:

`C:\WCFFBP_archive_backup\working_assets_252c9`

This backup is separate from the Git repository.

The backup contains the broader original working-asset
population, not merely the 384 code assets.

The backup location is an operational recovery reference,
not a guarantee that the backup remains available indefinitely.

## Git line-ending preservation

The repository's `.gitattributes` file contains 385
exact-path rules using `-text`: 384 historical script
rules and one permanent manifest rule.

These rules disable Git's automatic line-ending conversion
for the preserved historical scripts.

This is necessary because the Windows Git configuration
has `core.autocrlf=true`.

The preservation rules do not intentionally alter the
line-ending treatment of unrelated repository files.

## Security screening

The historical scripts underwent preliminary security
screening, including Gitleaks.

Two generic API-key findings in:

`etl/sql/204c_2b7_railroad_geographic_concordance.sql`

were reviewed and classified as false positives.

Security screening is not a guarantee that historical
scripts are safe to execute without further review.

## Historical whitespace characteristics

A CRLF-aware whitespace audit identified:

- 348 files containing CRLF line endings.
- Three lines with genuine trailing spaces or tabs.
- Four files with additional blank lines at EOF.

These characteristics were retained to preserve the
original SHA-256 fingerprints.

The seven formatting exceptions are documented in
`252d9b_whitespace_classification.txt`.

## Registry and certification boundaries

The original asset registry recorded these assets as
`HOLD_FOR_REVIEW` during the housekeeping process.

Git preservation is a separate disposition from:

- Analytical validation.
- Accounting registry authorization.
- Canonical ledger certification.
- Permission to execute historical scripts.

The registry must be reconciled after successful Git
publication, without erasing original provenance or
historical disposition records.

## Recovery and reproducibility

For each preserved script, the registered SHA-256
fingerprint provides the principal integrity check.

The Git version and independent backup should be
compared against that fingerprint when recovering files.

The repository's `.gitattributes` rules are necessary
for byte-exact working-tree restoration under the
documented Windows Git configuration.

## Publication status

This document is a pre-commit preservation record.

Successful Git commit and remote publication must be
verified separately before this status is updated.
