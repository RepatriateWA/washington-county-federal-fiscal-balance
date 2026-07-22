ADR-001

Decision:
Use surrogate integer keys internally.

Reason:
Federal identifiers change format over time.

Alternatives:
Natural keys.

Consequences:
Stable joins.
Simpler ETLs.

ADR-002

Decision:
Never overwrite raw federal data.

Reason:
Evidence preservation.

Alternatives:
Normalize in-place.

Consequences:
Higher storage usage.
Complete reproducibility.