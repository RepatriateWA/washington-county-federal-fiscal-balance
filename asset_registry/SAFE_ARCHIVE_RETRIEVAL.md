# WCFFBP - Safe Archived-File Retrieval

## Purpose

Retrieve individual archived evidence files without
overwriting or altering the working repository.

## Required identifiers

- Exact ZIP archive filename.
- Exact internal ZIP-member path.
- Expected member SHA-256.
- Expected uncompressed size.
- Expected CRC32, when available.

## Retrieval procedure

1. Consult the Asset Preservation Registry.
2. Locate the archive through the permanent archive catalog.
3. Identify the exact member using the archive/member pair.
4. Verify the ZIP package against its recorded SHA-256.
5. Open the member with Python `zipfile`.
6. Stream the member bytes to compute SHA-256 and CRC32.
7. Compare the computed values with the historical index.
8. If a disk copy is needed, write only to a dedicated
   review directory outside the working repository.
9. Refuse to overwrite any existing destination file.
10. Preserve the archive/member identity and verification
    result in the review record.

## Safety requirements

Do not use unrestricted bulk extraction.

Do not trust archived member paths as filesystem paths
without validation.

Reject absolute paths, parent-directory traversal,
duplicate ZIP-member names, and unexpected destinations.

Never replace an existing working source file with an
archived copy without separate authorization.

## Certification distinction

A successful sample test demonstrates selective
retrievability for the sampled members.

It does not certify that all archived members were
content-verified during the sample test.

Historical checksum verification evidence must remain
available for the remaining members.
