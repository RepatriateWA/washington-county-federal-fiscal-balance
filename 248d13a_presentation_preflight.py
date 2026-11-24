import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()

PRESENTATION = ROOT / "docs/presentations/wcffbp-247d/index.html"
CANDIDATE = ROOT / "248d12b6_eight_year_candidate.csv"
COVERAGE = ROOT / "248d12b6_fy2025_coverage_status.csv"
REPORT = ROOT / "248d13a_presentation_preflight.txt"

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return (
        result.stdout.strip()
        if result.returncode == 0
        else f"ERROR: {result.stderr.strip()}"
    )

for path in (PRESENTATION, CANDIDATE, COVERAGE):
    if not path.is_file():
        raise RuntimeError(f"Missing required file: {path}")

if REPORT.exists():
    raise RuntimeError(f"Refusing to overwrite: {REPORT}")

html = PRESENTATION.read_text(
    encoding="utf-8-sig",
    errors="replace"
)

candidate = read_csv(CANDIDATE)
coverage = read_csv(COVERAGE)

lines = []

def section(title):
    lines.append("")
    lines.append("=" * 76)
    lines.append(title)
    lines.append("=" * 76)

lines.extend([
    "ETL-248D13A - EIGHT-YEAR PRESENTATION COMPATIBILITY PREFLIGHT",
    "READ ONLY - NO PRESENTATION, DATABASE, REGISTRY, OR LEDGER MODIFICATIONS",
])

section("1. GIT CONTEXT")

lines.append(f"Branch: {git('branch', '--show-current')}")
lines.append(f"HEAD: {git('rev-parse', 'HEAD')}")
lines.append(f"Presentation tracked: {git('ls-files', '--', str(PRESENTATION.relative_to(ROOT)))}")

section("2. SOURCE FILES")

for path in (PRESENTATION, CANDIDATE, COVERAGE):
    lines.append(f"Path: {path.relative_to(ROOT)}")
    lines.append(f"Size: {path.stat().st_size:,} bytes")
    lines.append(f"SHA256: {sha256(path)}")
    lines.append("")

section("3. CANDIDATE DATASET")

lines.append(f"Rows: {len(candidate)}")
lines.append(f"Columns: {len(candidate[0]) if candidate else 0}")

if candidate:
    lines.append("Column names:")
    for column in candidate[0]:
        lines.append(f"  {column}")

    lines.append("Fiscal years:")
    for row in candidate:
        lines.append(
            f"  FY{row['fiscal_year']} | "
            f"inflows={row['revised_inflows_usd']} | "
            f"IRS={row['irs_net_collections_usd']} | "
            f"balance={row['revised_balance_usd']}"
        )

    lines.append("")
    lines.append("FY2025 blank fields:")

    for key, value in candidate[-1].items():
        if value is None or not str(value).strip():
            lines.append(f"  {key}")

section("4. FY2025 COVERAGE STATUS")

for row in coverage:
    lines.append(json.dumps(row, ensure_ascii=False))

section("5. PRESENTATION TITLE AND STRUCTURE")

patterns = [
    r"<title[^>]*>.*?</title>",
    r"<h1[^>]*>.*?</h1>",
    r"<h2[^>]*>.*?</h2>",
    r"<h3[^>]*>.*?</h3>",
    r"<button[^>]*>.*?</button>",
    r"<select[^>]*>.*?</select>",
]

for pattern in patterns:
    matches = re.findall(
        pattern,
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    lines.append(f"Pattern: {pattern}")
    lines.append(f"Matches: {len(matches)}")

    for match in matches[:20]:
        compact = re.sub(r"\s+", " ", match)
        lines.append(f"  {compact[:350]}")

section("6. DATA AND CHART DEFINITIONS")

terms = [
    "const DATA",
    "const YEARS",
    "2018",
    "2024",
    "2025",
    "15-component",
    "COVID",
    "IIJA",
    "selectedYear",
    "selectedFY",
    "fiscal_year",
    "revised_inflows_usd",
    "irs_net_collections_usd",
    "ADDITIONAL_QUALIFIED_ASSISTANCE",
    "MILITARY_RETIREMENT_MODELED",
    "chart",
    "canvas",
    "svg",
    "Plotly",
    "Chart.js",
    "ApexCharts",
    "D3",
]

html_lines = html.splitlines()

for term in terms:
    matches = [
        (i + 1, line)
        for i, line in enumerate(html_lines)
        if term.lower() in line.lower()
    ]

    lines.append("")
    lines.append(f"TERM: {term}")
    lines.append(f"Matching lines: {len(matches)}")

    for number, line in matches[:12]:
        compact = line.strip()
        lines.append(
            f"  L{number}: {compact[:500]}"
        )

section("7. JAVASCRIPT DATA ARRAY LOCATION")

match = re.search(
    r"\b(?:const|let|var)\s+DATA\s*=",
    html
)

if match:
    start = match.start()
    lines.append(f"DATA assignment character offset: {start}")
    lines.append(
        "DATA opening excerpt: "
        + html[start:start + 1000].replace("\n", " ")
    )
else:
    lines.append("No simple DATA assignment located")

section("8. FY2024/FY2025 REFERENCES")

for i, line in enumerate(html_lines, start=1):
    if "2024" in line or "2025" in line:
        compact = line.strip()
        lines.append(f"L{i}: {compact[:650]}")

section("9. PRESENTATION JAVASCRIPT FUNCTIONS")

functions = re.findall(
    r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(",
    html
)

arrow_functions = re.findall(
    r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*="
    r"\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
    html
)

lines.append("Named functions:")
lines.extend(f"  {name}" for name in functions)

lines.append("Arrow functions:")
lines.extend(f"  {name}" for name in arrow_functions)

section("10. PRELIMINARY COMPATIBILITY FLAGS")

flags = {
    "Has embedded DATA assignment":
        bool(match),

    "Mentions FY2024":
        "2024" in html,

    "Mentions FY2025":
        "2025" in html,

    "Has COVID references":
        "COVID" in html.upper(),

    "Has IIJA references":
        "IIJA" in html.upper(),

    "Has additional qualified assistance":
        "ADDITIONAL_QUALIFIED_ASSISTANCE" in html,

    "Candidate has eight rows":
        len(candidate) == 8,

    "FY2025 additional qualified assistance blank":
        bool(candidate)
        and not candidate[-1].get(
            "ADDITIONAL_QUALIFIED_ASSISTANCE", ""
        ).strip()
}

for key, value in flags.items():
    lines.append(f"{key}: {value}")

section("11. NEXT STEP")

lines.extend([
    "Inspect embedded DATA schema and presentation rendering logic.",
    "Preserve all seven historical rows.",
    "Treat FY2025 unquantified components as missing, not zero.",
    "Inspect COVID/IIJA FY2025 handling before extending third view.",
    "No presentation modification authorized by this diagnostic.",
])

REPORT.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8"
)

print("ETL-248D13A - PREFLIGHT COMPLETE")
print(f"Report: {REPORT.name}")
print(f"Report lines: {len(lines)}")
print(f"Candidate rows: {len(candidate)}")
print(f"HTML lines: {len(html_lines)}")
print(f"Embedded DATA assignment found: {bool(match)}")
print("No existing files modified.")
