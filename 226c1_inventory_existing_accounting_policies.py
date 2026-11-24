from pathlib import Path
from collections import Counter
import re
import subprocess

ROOT = Path.cwd()
OUTPUT = ROOT / "226c1_existing_accounting_policy_inventory.txt"

SEARCH_ROOTS = [
    ROOT / "etl",
    ROOT / "docs",
    ROOT / "notes",
    ROOT / "accounting_registry",
]

EXTENSIONS = {".sql", ".py", ".md", ".txt", ".csv"}

PATTERNS = {
    "SOURCE_POLICY": re.compile(
        r"source.policy|source_policy|preferred_source",
        re.I
    ),
    "PROGRAM_MAPPING": re.compile(
        r"program.mapping|program_mapping",
        re.I
    ),
    "ACCOUNTING_CLASSIFICATION": re.compile(
        r"EXCLUDE_DUPLICATE|INCLUDE_ADDITIVE|"
        r"NO_PROGRAM_MAPPING|accounting.classification|"
        r"accounting_classification",
        re.I
    ),
    "ASSISTANCE": re.compile(
        r"USASPENDING_ASSISTANCE|assistance\.award_transaction|"
        r"historical.assistance",
        re.I
    ),
    "PROCUREMENT": re.compile(
        r"USASPENDING_PROCUREMENT|raw_award_transaction|"
        r"procurement",
        re.I
    ),
    "CERTIFICATION": re.compile(
        r"PRE.MIGRATION CONTROLS PASS|"
        r"certif|reconcil|validation",
        re.I
    ),
}

lines = [
    "ETL-226C1 - EXISTING ACCOUNTING POLICY INVENTORY",
    "=" * 100,
    "READ ONLY - NO DATABASE OR REGISTRY WRITES",
    "",
]

# Confirm the repository and record its current revision.
git = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True,
    text=True,
    errors="replace",
)

if git.returncode != 0:
    raise RuntimeError("Not inside a Git repository")

lines.append("Repository: " + git.stdout.strip())

head = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"],
    capture_output=True,
    text=True,
    errors="replace",
)

lines.append("HEAD: " + head.stdout.strip())
lines.append("")

matches = []
scanned = 0
errors = []

for search_root in SEARCH_ROOTS:
    if not search_root.exists():
        continue

    for path in search_root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in EXTENSIONS:
            continue

        scanned += 1

        try:
            content = path.read_text(
                encoding="utf-8-sig",
                errors="replace"
            )
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            continue

        categories = []
        hit_counts = {}

        for category, pattern in PATTERNS.items():
            hits = pattern.findall(content)

            if hits:
                categories.append(category)
                hit_counts[category] = len(hits)

        if not categories:
            continue

        relative = path.relative_to(ROOT).as_posix()

        matches.append({
            "path": relative,
            "categories": categories,
            "counts": hit_counts,
        })

matches.sort(
    key=lambda item: (
        -len(item["categories"]),
        item["path"]
    )
)

lines.extend([
    f"Files scanned: {scanned}",
    f"Files matching policy indicators: {len(matches)}",
    f"Read errors: {len(errors)}",
    "",
    "MATCHED FILES",
    "-" * 100,
])

for item in matches:
    lines.append(item["path"])
    lines.append(
        "  Categories: " +
        ", ".join(item["categories"])
    )
    lines.append(
        "  Hits: " +
        ", ".join(
            f"{key}={value}"
            for key, value in item["counts"].items()
        )
    )

if errors:
    lines.extend([
        "",
        "READ ERRORS",
        "-" * 100,
        *errors,
    ])

OUTPUT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("ETL-226C1 PASS")
print("Files scanned:", scanned)
print("Matching files:", len(matches))
print("Read errors:", len(errors))
print("Output:", OUTPUT)
