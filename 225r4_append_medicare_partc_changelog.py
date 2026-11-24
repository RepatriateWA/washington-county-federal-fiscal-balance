from pathlib import Path
import sys

path = Path(
    "accounting_registry/v0_3_0_working/CHANGELOG.md"
)

original = path.read_bytes()

try:
    original.decode("utf-8")
except UnicodeDecodeError:
    sys.exit("STOP: changelog is not valid UTF-8")

if b"## v0.3.5 working" not in original:
    sys.exit("STOP: prior changelog version missing")

if b"## v0.3.6 working" in original:
    sys.exit("STOP: v0.3.6 already exists")

entry = """## v0.3.6 working - ETL-225R Medicare Part C verification

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
"""

updated = (
    original.rstrip(b"\r\n")
    + b"\n\n"
    + entry.encode("utf-8").rstrip(b"\r\n")
    + b"\n"
)

path.write_bytes(updated)

assert path.read_bytes() == updated
assert updated.startswith(original.rstrip(b"\r\n"))

print("ETL-225R4 PASS")
print("Existing changelog preserved.")
print("New v0.3.6 entry appended.")
print("UTF-8 encoding verified.")
