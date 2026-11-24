# External Archive Crosswalk

The permanent archive catalog is:

`docs/archives/WCFFBP_HOUSEKEEPING_ARCHIVE_CATALOG.md`

The primary archive directory is:

`D:\GitHub\WCFFBP_housekeeping_archive`

The independently verified second-disk ZIP backup is:

`C:\WCFFBP_archive_backup`

Seven historical ZIP packages have verified primary and
backup checksums, as recorded by ETL-252C7F.

The historical diagnostics archived in those ZIPs are
not included as individual rows in the initial 717-file
asset manifest.

Use the existing archive catalog and its archived-file
indexes to locate individual ZIP members and confirm
their expected checksums.

The external ZIP contents are not stored in GitHub.

The separate physical disks protect against an individual
disk failure, but not all site-wide risks.

## Permanent member-level retrieval index

Consult
[`archive_member_index.csv`](archive_member_index.csv)
to locate an archived file by its exact ZIP filename
and internal member path.

Each record includes historical SHA-256 evidence,
uncompressed size, CRC32, member classification,
retrieval-test status, and primary/backup archive paths.

The index distinguishes the 1,362 historical source
members from the administrative manifest.

Eight members were independently read during
ETL-252C8G. The remaining 1,355 members were not
retested during that selective retrieval exercise.

Follow
[`SAFE_ARCHIVE_RETRIEVAL.md`](SAFE_ARCHIVE_RETRIEVAL.md)
for verification and safe recovery instructions.

Primary and backup paths describe the current
Windows storage arrangement. They are not GitHub
download links and must be updated if archives move.
