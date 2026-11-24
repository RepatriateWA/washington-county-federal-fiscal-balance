# WCFFBP Asset Preservation Registry

## Purpose

This directory is the permanent discovery and preservation
index for WCFFBP evidence assets, supporting code, and
externally archived materials.

It complements the authoritative accounting registry.
It does not replace accounting-family authorization,
evidence certification, or the canonical ledger.

## Entry points

- `asset_manifest.csv`: baseline inventory of 717 files.
- `backup_coverage.csv`: independently verified backup status.
- `ARCHIVE_CROSSWALK.md`: archived diagnostic packages.
- `../ACCOUNTING_REGISTRY.md`: accounting-registry entry point.
- `../accounting_registry/v0_3_3_working/README.md`:
  current working accounting registry.

## Identity and preservation

Assets are identified by repository-relative path, size,
and SHA-256 fingerprint. Asset IDs are assigned for this
baseline and should remain stable in subsequent revisions.

`INVENTORIED` means a file was present and its checksum
matched the source audit at registry creation.

It does NOT mean the file is independently backed up.

`NOT_YET_VERIFIED` means backup or recovery assurance has
not been established.

`HOLD_FOR_REVIEW` prohibits interpreting a provisional
classification as permission to remove an asset.

## Scope

The initial manifest covers the 717-file ETL-252C8C
baseline, not every tracked file, ignored file, database
record, or externally stored archive member.

The seven existing external ZIP packages are documented
separately in the permanent archive catalog.

## Governance

Before adding, moving, replacing, archiving, or deleting
substantive assets, update the inventory and record
provenance, checksum, disposition, and backup status.

Preserve accounting-registry references and ETL lineage.
Do not equate absence of a text reference with disposability.

Git-tracked manifests preserve metadata, not the contents
of external files. Recovery requires an actual verified
copy of the data.

## Audit provenance

Baseline: ETL-252C7F
Classification: ETL-252C8A
Historical dependency audit: ETL-252C8B
Architecture and checksum preflight: ETL-252C8C
Registry construction: ETL-252C8D

## Archive-member discovery

The permanent archive-member inventory is
[`archive_member_index.csv`](archive_member_index.csv).

It records 1,362 historical source members and one
administrative metadata member across seven ZIP packages.

For individual file recovery, follow
[`SAFE_ARCHIVE_RETRIEVAL.md`](SAFE_ARCHIVE_RETRIEVAL.md).

The seven ZIP packages have separately verified backup
copies. This does not establish independent backup coverage
for the 717 working assets in `backup_coverage.csv`.

Archive paths are machine-specific. GitHub preserves the
catalog and index, not the external ZIP payloads.

## Additional audit provenance

- ETL-252C8E: archive metadata audit
- ETL-252C8F/F2: historical member reconciliation
- ETL-252C8G: selective content retrieval
- ETL-252C8H: permanent index preparation
- ETL-252C8I: index validation
