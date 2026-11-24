import csv
import json
import re
import shutil
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path.cwd()
SOURCE_DIR = ROOT / "docs/presentations/wcffbp-247d"
SOURCE_HTML = SOURCE_DIR / "index.html"
CANDIDATE = ROOT / "248d12b6_eight_year_candidate.csv"
COVERAGE = ROOT / "248d12b6_fy2025_coverage_status.csv"

DEST = ROOT / "docs/presentations/wcffbp-248d"
REPORT = ROOT / "248d13c_presentation_validation.txt"

CENT = Decimal("0.01")
BILLION = Decimal("1000000000")

def D(value):
    return Decimal(str(value))

def cents(value):
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

for path in (SOURCE_HTML, CANDIDATE, COVERAGE):
    if not path.is_file():
        raise RuntimeError(f"Required source missing: {path}")

if DEST.exists():
    raise RuntimeError(f"Refusing to overwrite destination: {DEST}")

if REPORT.exists():
    raise RuntimeError(f"Refusing to overwrite report: {REPORT}")

rows = read_csv(CANDIDATE)
coverage = read_csv(COVERAGE)

if [int(r["fiscal_year"]) for r in rows] != list(range(2018, 2026)):
    raise RuntimeError("Expected fiscal years 2018 through 2025")

fields = list(rows[0])
components = fields[
    fields.index("SSA_OASDI"):
    fields.index("revised_inflows_usd")
]

if len(components) != 15:
    raise RuntimeError("Expected exactly 15 components")

if len(coverage) < 1:
    raise RuntimeError("Missing FY2025 coverage records")

unquantified = {
    r["family_or_component"]
    for r in coverage
    if r["coverage_status"] == "NOT_QUANTIFIED"
}

if "ADDITIONAL_QUALIFIED_ASSISTANCE" not in unquantified:
    raise RuntimeError("Missing required unquantified status")

html = SOURCE_HTML.read_text(encoding="utf-8-sig")

pattern = r"const DATA=(\[.*?\]), NAMES="
match = re.search(pattern, html, flags=re.DOTALL)

if not match:
    raise RuntimeError("Embedded DATA array not located")

original_json = match.group(1)
original_data = json.loads(original_json)

if len(original_data) != 7:
    raise RuntimeError("Expected seven historical presentation records")

if [d["year"] for d in original_data] != list(range(2018, 2025)):
    raise RuntimeError("Historical presentation years mismatch")

# Validate source presentation against candidate history.
for old, row in zip(original_data, rows[:7]):
    if old["year"] != int(row["fiscal_year"]):
        raise RuntimeError("Historical year mismatch")

    checks = (
        ("inflows", "revised_inflows_usd"),
        ("taxes", "irs_net_collections_usd"),
        ("balance", "revised_balance_usd")
    )

    for js_field, csv_field in checks:
        actual = cents(D(str(old[js_field])) * BILLION)
        expected = cents(row[csv_field])

        if actual != expected:
            raise RuntimeError(
                f"Historical mismatch FY{old['year']} "
                f"{js_field}: {actual} vs {expected}"
            )

    if len(old["parts"]) != 15:
        raise RuntimeError("Historical component count mismatch")

    for index, component in enumerate(components):
        actual = cents(D(str(old["parts"][index])) * BILLION)
        expected = cents(row[component])

        if actual != expected:
            raise RuntimeError(
                f"Historical component mismatch "
                f"FY{old['year']} {component}"
            )

fy25 = rows[-1]

if fy25["ADDITIONAL_QUALIFIED_ASSISTANCE"].strip():
    raise RuntimeError(
        "FY2025 additional assistance must remain unquantified"
    )

quantified = [
    cents(fy25[c])
    for c in components
    if fy25[c].strip()
]

total = sum(quantified, Decimal(0))

if total != cents(fy25["revised_inflows_usd"]):
    raise RuntimeError("FY2025 components do not reconcile")

taxes = cents(fy25["irs_net_collections_usd"])
balance = cents(fy25["revised_balance_usd"])

if total - taxes != balance:
    raise RuntimeError("FY2025 balance does not reconcile")

def billions(value):
    return float(D(value) / BILLION)

new_record = {
    "year": 2025,
    "inflows": billions(total),
    "taxes": billions(taxes),
    "balance": billions(balance),
    "parts": [
        billions(fy25[c]) if fy25[c].strip() else None
        for c in components
    ],
    "covid": None,
    "iija": None
}

# Preserve the original seven JSON records verbatim.
new_json = (
    original_json[:-1]
    + ","
    + json.dumps(new_record, separators=(",", ":"))
    + "]"
)

html = (
    html[:match.start(1)]
    + new_json
    + html[match.end(1):]
)

if html.count("Washington Federal Fiscal Balance 2018-2024") != 1:
    raise RuntimeError("Expected exactly one presentation year heading")

html = html.replace(
    "Washington Federal Fiscal Balance 2018-2024",
    "Washington Federal Fiscal Balance 2018-2025"
)

if html.count("let selected=2024;") != 1:
    raise RuntimeError("Unexpected selected-year initialization")

html = html.replace("let selected=2024;", "let selected=2025;")

def replace_function(document, name, next_name, replacement):
    start_token = f"function {name}("
    end_token = f"function {next_name}("

    start = document.find(start_token)
    end = document.find(end_token, start + len(start_token))

    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(f"Cannot isolate function {name}")

    return document[:start] + replacement + "\n" + document[end:]

annual = r'''
function renderAnnual(){
  let s=axis(180,[0,40,80,120,160]);
  DATA.forEach((d,i)=>{
    let x=68+i*94,base=340,sc=320/180;
    s+=rect(x,base-d.inflows*sc,29,d.inflows*sc,'#357b9f');
    s+=rect(x+33,base-d.taxes*sc,29,d.taxes*sc,'#a0adb9');
    s+=label(x+31,365,d.year);
    if(d.year===selected)s+=selection(x-2,18,340,72);
    s+=rect(x-7,15,78,356,'transparent',
      `style="cursor:pointer" onclick="choose(${d.year})"`);
  });
  $('annualChart').innerHTML=svg(850,385,s);
}
'''

stacked = r'''
function renderStacked(){
  let s=axis(140,[0,35,70,105,140]);
  DATA.forEach((d,i)=>{
    let x=75+i*94,base=340,acc=0,sc=320/140;
    d.parts.forEach((v,j)=>{
      if(v===null)return;
      s+=rect(x,base-(acc+v)*sc,55,v*sc,COLORS[j]);
      acc+=v;
    });
    s+=label(x+27,365,d.year);
    if(d.year===selected)s+=selection(x-6,18,340,72);
    s+=rect(x-9,15,77,356,'transparent',
      `style="cursor:pointer" onclick="choose(${d.year})"`);
  });
  $('stackedChart').innerHTML=svg(850,385,s);
  $('legend').innerHTML=NAMES.map((n,i)=>
    `<span><i class="swatch" style="background:${COLORS[i]}"></i>${n}</span>`
  ).join('');
  $('detailTitle').textContent='FY'+selected+' components';
  $('details').innerHTML=current().parts.map((v,i)=>
    `<tr><td>${NAMES[i]}</td><td>${v===null?'Not quantified':fmt(v)}</td></tr>`
  ).join('')+
    `<tr><td><b>Identified/modeled inflows</b></td><td><b>${fmt(current().inflows)}</b></td></tr>`;
}
'''

covid = r'''
function renderCovid(){
  let s=axis(25,[0,5,10,15,20,25]);
  DATA.forEach((d,i)=>{
    const x=72+i*94,base=340,sc=320/25;
    const series=[d.covid,d.parts[11],d.parts[12]];
    const colors=['#cb7654','#305b91','#d19b42'];
    series.forEach((v,j)=>{
      if(v===null)return;
      s+=rect(x+j*23,base-v*sc,20,v*sc,colors[j]);
    });
    s+=label(x+33,365,d.year);
    if(d.year===selected)s+=selection(x-7,18,340,82);
    s+=rect(x-9,15,82,356,'transparent',
      `style="cursor:pointer" onclick="choose(${d.year})"`);
  });
  $('covidChart').innerHTML=svg(850,385,s);
}
'''

render = r'''
function render(){
  let d=current();
  $('year').textContent='FY'+selected;
  let covidView=activeView==='covid';
  $('inflowsLabel').textContent=covidView
    ?'COVID-tagged inflows'
    :'Federal inflows into Washington';
  $('taxesLabel').textContent=covidView
    ?'DoD procurement'
    :'IRS net collections';
  $('inflows').textContent=covidView
    ?(d.covid===null?'Not available':fmt(d.covid))
    :fmt(d.inflows);
  $('taxes').textContent=fmt(covidView?d.parts[11]:d.taxes);
  $('balance').textContent=fmt(d.balance);
  $('balanceStat').hidden=covidView;
  $('doeStat').hidden=!covidView;
  $('doeValue').textContent=fmt(d.parts[12]);
  $('years').innerHTML=DATA.map(d=>
    `<button class="${d.year===selected?'active':''}" onclick="choose(${d.year})">${d.year}</button>`
  ).join('');
  renderAnnual();
  renderStacked();
  renderCovid();
}
'''

html = replace_function(html, "renderAnnual", "renderStacked", annual)
html = replace_function(html, "renderStacked", "renderCovid", stacked)
html = replace_function(html, "renderCovid", "render", covid)

start = html.find("function render(){")
end = html.find("let activeView=", start)

if start < 0 or end < 0:
    raise RuntimeError("Cannot isolate final render function")

html = html[:start] + render + "\n" + html[end:]

# Visible disclosure, added without changing existing charts.
disclosure = (
    '<div class="card" id="fy2025Disclosure" '
    'style="border-left:4px solid #85572e">'
    '<strong>FY2025 coverage qualification.</strong> '
    'The FY2025 federal inflow total is an identified and modeled '
    'subtotal, not a comprehensive certified accounting. '
    'Additional qualified assistance and other unresolved families '
    'are not quantified; missing amounts do not mean zero. '
    'Procurement figures represent obligations rather than outlays. '
    'Military retirement is modeled. FY2025 COVID and IIJA '
    'tagging is unavailable. Historical FY2018–FY2024 '
    'presentation data are preserved.'
    '</div>'
)

if html.count("</main>") != 1:
    raise RuntimeError("Cannot locate unique main closing tag")

html = html.replace("</main>", disclosure + "</main>", 1)

# Validate the final embedded array before writing.
updated_match = re.search(
    r"const DATA=(\[.*?\]), NAMES=",
    html,
    flags=re.DOTALL
)

if not updated_match:
    raise RuntimeError("Updated DATA array missing")

updated = json.loads(updated_match.group(1))

if updated[:7] != original_data:
    raise RuntimeError("Historical embedded data changed")

if len(updated) != 8 or updated[-1]["year"] != 2025:
    raise RuntimeError("FY2025 append failed")

if updated[-1]["parts"][10] is not None:
    raise RuntimeError("Missing assistance converted to zero")

if updated[-1]["covid"] is not None:
    raise RuntimeError("Missing COVID value converted to zero")

if updated[-1]["iija"] is not None:
    raise RuntimeError("Missing IIJA value converted to zero")

if "let selected=2025;" not in html:
    raise RuntimeError("Default year not updated")

# Create a new directory; never alter the published source.
DEST.mkdir(parents=True)

assets = []

for source_asset in SOURCE_DIR.iterdir():
    if source_asset.is_file() and source_asset.name != "index.html":
        shutil.copy2(source_asset, DEST / source_asset.name)
        assets.append(source_asset.name)

output_html = DEST / "index.html"
output_html.write_text(html, encoding="utf-8")

report_lines = [
    "ETL-248D13C - EIGHT-YEAR PRESENTATION CANDIDATE",
    "STATUS: PASS",
    "NO DATABASE WRITES",
    "NO LEDGER AUTHORIZATION",
    "NO GIT COMMIT OR PUBLICATION",
    "",
    f"Source: {SOURCE_HTML.relative_to(ROOT)}",
    f"Destination: {output_html.relative_to(ROOT)}",
    f"Source SHA256: {sha(SOURCE_HTML)}",
    f"Candidate CSV SHA256: {sha(CANDIDATE)}",
    f"Output SHA256: {sha(output_html)}",
    "",
    "Historical embedded records preserved: 7/7",
    "Presentation fiscal years: 2018-2025",
    "Presentation components: 15",
    "Default selected fiscal year: 2025",
    "",
    f"FY2025 identified/modeled inflows USD: {total:.2f}",
    f"FY2025 IRS net collections USD: {taxes:.2f}",
    f"FY2025 provisional balance USD: {balance:.2f}",
    "",
    "FY2025 additional qualified assistance: NOT QUANTIFIED",
    "FY2025 COVID-tagged amount: NOT AVAILABLE",
    "FY2025 IIJA-tagged amount: NOT AVAILABLE",
    "Missing values preserved as null, not zero.",
    "",
    "CHART CHANGES:",
    "Annual, stacked and isolated-program charts use eight-year spacing.",
    "FY2025 missing stacked component displays Not quantified.",
    "FY2025 COVID statistic displays Not available.",
    "DoD and DOE procurement remain quantified.",
    "FY2025 coverage disclosure added.",
    "",
    "COPIED PRESENTATION ASSETS:",
    *assets,
    "",
    "REQUIRED NEXT GATE:",
    "Inspect candidate visually in browser.",
    "Confirm chart positions, labels, selections and disclosures.",
    "No publication until approved."
]

REPORT.write_text(
    "\n".join(report_lines) + "\n",
    encoding="utf-8"
)

print("\n".join(report_lines))
