# WCFFBP Housekeeping Archive Catalog

**Project:** Washington County Federal Fiscal Balance Project
**Catalog version:** 1 ? November 23, 2026
**Status:** Archive provenance and recovery documentation; not accounting certification

## 1. Purpose

This catalog identifies historical WCFFBP working files preserved outside
the active Git repository. It supports retrieval, reproducibility, historical
review, and protection against accidental loss during repository housekeeping.

The authoritative accounting registry and canonical ledger remain separate.
Archive membership is not evidence of ledger certification.

## 2. Archive location

Local archive directory: `D:\GitHub\WCFFBP_housekeeping_archive`

Portable root variable: `WCFFBP_ARCHIVE_ROOT`

These ZIP archives are outside Git. Committing this catalog does not
upload or back up the ZIP contents. Any project transfer must separately
preserve the archive directory and its documented location.

## 3. ZIP archive inventory

| ZIP archive | Members | Size (bytes) | SHA-256 |
|---|---:|---:|---|
| `250d4b_empty_duplicates.zip` | 308 | 35,858 | `4f9b6059c52395f2c8a7f639cfe99116360408e79d1af42a512316e1277bd6cd` |
| `250d5d_tracked_duplicates.zip` | 7 | 11,630 | `19145c39f6964bc10e8dc0eb2e380c0625de0b9c1b09124d1a141b327a96cf24` |
| `250d6e_diagnostic_outputs.zip` | 6 | 2,028 | `6c2b7881b97b65fb26f52076f5d1b2bf0c509190a664c43bf108c0f77673a491` |
| `250d7d_diagnostic_batch.zip` | 59 | 198,673 | `0616e10143f6e80e84224b1db2eebe775a57ad674450953bc3f4fd9a43a0c983` |
| `250d8d_git_evidence.zip` | 9 | 5,956 | `076cdc183fd813cefd3927be67e544b4e34c9f9703c0fd78033c9483b99ce963` |
| `250d8h_routine_diagnostics.zip` | 10 | 7,213 | `49c60b61e87b3de353dac1708b65296d16e8e0c5c9a7ddc2ec5886b9ef0db089` |
| `252c5_historical_diagnostics.zip` | 964 | 4,677,493 | `3dcc825ac89d29fc6cd930a5619ea973e444f6a97695edf3530c2e76f18ff0f7` |

Seven archives contain 1,363 ZIP members. The ETL-252C5 archive contains
963 historical diagnostic files plus one embedded metadata manifest.

## 4. Indexes and verification records

Historical archive records:

- `250d9b1a_archive_inventory.csv`
- `250d9b1a_archived_file_index.csv`
- `250d9b1a_archive_inventory_summary.txt`

ETL-252C5 and ETL-252C6A records:

- `252c3_current_untracked_reconciliation.csv`
- `252c5_archived_file_index_retry1.csv`
- `252c5_archive_verification_retry1.txt`
- `252c6a_removal_candidate_manifest.csv`
- `252c6a_removal_preflight.txt`

The member indexes, verification reports, and manifests provide the
provenance required to locate and validate archived files. Some historical
records may remain in the local evidence workspace; repository tracking
must be confirmed before treating a reference as portable.

The ETL-250D9B1A audit verified the first six archives on
November 11, 2026. ETL-252C5 verified the seventh archive, and
ETL-252C6A independently reverified its 963 original source files
and corresponding archive members.

## 5. Recovery procedure

1. Search the archived-file indexes by original relative path or filename.
2. Identify the containing ZIP archive.
3. Verify the ZIP SHA-256 against this catalog.
4. Verify the ZIP member SHA-256 against the member index.
5. Extract the file into a separate recovery directory.
6. Review the recovered material against current registry and ledger evidence.

Never automatically overwrite current repository files with archived copies.

## 6. Accounting and evidence safeguards

Archive membership does not establish that a file is obsolete,
superseded, approved for deletion, or certified for ledger inclusion.

Archived diagnostics may contain historical source lineage,
accounting decisions, reconciliation evidence, or information
relevant to county-level attribution.

Restored evidence must undergo normal WCFFBP review before supporting
accounting conclusions.

## 7. Outstanding limitations

- Independent backup storage copies have not been verified.
- Historical manifest and deletion-count reconciliation remains incomplete.
- Accounting-family classifications have not been certified here.
- Successful archive verification does not authorize deletion.
- GitHub does not contain the archived ZIP bytes merely because this
  catalog is tracked.

## 8. Maintenance

Every new archival batch should record its source population,
authorization, ZIP filename and checksum, member index,
verification results, and any separately authorized removal.

Update this catalog whenever archives are added, relocated, or restored.

**Preservation principle:** Never sacrifice source provenance or
reproducibility merely to obtain a clean Git working tree.
