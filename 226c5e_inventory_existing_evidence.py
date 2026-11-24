from pathlib import Path
import csv
import re
import subprocess

root = Path.cwd()
queue = root / "226c5d_review_queue.csv"
output = root / "226c5e_existing_evidence_inventory.txt"

with queue.open(encoding="utf-8-sig", newline="") as f:
    programs = list(csv.DictReader(f))

if len(programs) != 35:
    raise SystemExit(
        f"Expected 35 programs; found {len(programs)}"
    )

result = subprocess.run(
    ["git", "ls-files", "--cached", "--others",
     "--exclude-standard"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    check=True,
)

extensions = {".sql", ".py", ".md", ".txt", ".csv"}
files = []

for name in result.stdout.splitlines():
    p = root / name
    if (
        p.is_file()
        and p.suffix.lower() in extensions
        and not p.name.startswith("226c5")
        and p.stat().st_size <= 2_000_000
    ):
        files.append(p)

# Read each eligible repository file once.
contents = {}

for p in files:
    try:
        contents[p] = p.read_text(
            encoding="utf-8-sig", errors="replace"
        )
    except OSError:
        continue

lines = [
    "ETL-226C5E - EXISTING ASSISTANCE EVIDENCE INVENTORY",
    "=" * 76,
    f"Programs: {len(programs)}",
    f"Repository files inspected: {len(contents)}",
    "Database writes: NONE",
    "Registry writes: NONE",
    "",
    "NOTE: Matches are discovery leads, not accounting certifications.",
    "",
]

for program in programs:
    code = program["program_code"]
    title = program["program_title"]

    # Require code boundaries to avoid partial numeric matches.
    pattern = re.compile(
        rf"(?<![\d.]){re.escape(code)}(?![\d.])"
    )

    matches = []

    for path, content in contents.items():
        if pattern.search(content):
            relative = path.relative_to(root).as_posix()
            matches.append(relative)

    lines.extend([
        "-" * 76,
        f"RANK {program['materiality_rank']}: "
        f"{code} - {title}",
        f"NET: {program['net_obligations_usd']}",
        f"ABSOLUTE: {program['absolute_activity_usd']}",
        f"MATCHING FILES: {len(matches)}",
    ])

    for name in sorted(matches)[:25]:
        lines.append(f"  {name}")

    if len(matches) > 25:
        lines.append(
            f"  ... {len(matches) - 25} additional matches"
        )

    if not matches:
        lines.append("  NO DIRECT PROGRAM-CODE MATCH FOUND")

    lines.append("")

lines.append("ETL-226C5E INVENTORY COMPLETE")

output.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)

print(f"Programs inspected: {len(programs)}")
print(f"Repository files inspected: {len(contents)}")
print(f"Evidence inventory: {output.name}")
print("ETL-226C5E PASS")
