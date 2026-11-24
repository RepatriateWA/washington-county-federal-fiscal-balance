from pathlib import Path
from decimal import Decimal
import csv
import json
import re

ROOT = Path.cwd()
SOURCE = ROOT / "docs/presentations/wcffbp-246d/index.html"
DOR = ROOT / "data/raw/wa_dor/tax_statistics/247a5_state_tax_collections_2018_2024.csv"
OUT = ROOT / "docs/presentations/wcffbp-247b"
PREVIEW = OUT / "preview.html"

assert SOURCE.is_file(), SOURCE
assert DOR.is_file(), DOR

html = SOURCE.read_text(encoding="utf-8-sig")

with DOR.open(newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

assert len(rows) == 7
assert sorted(int(r["fiscal_year"]) for r in rows) == list(range(2018, 2025))
assert all(r["accounting_status"] == "COMPARISON_ONLY" for r in rows)
assert all(r["fiscal_year_basis"] == "WASHINGTON_STATE_JUL_JUN" for r in rows)

amounts = {
    int(r["fiscal_year"]): Decimal(r["amount_usd"])
    for r in rows
}

assert sum(amounts.values()) == Decimal("209772148267.86")

state_data = [
    {
        "year": year,
        "stateTaxes": float(amounts[year] / Decimal("1000000000"))
    }
    for year in sorted(amounts)
]

def replace_once(old, new, label):
    global html
    count = html.count(old)
    assert count == 1, f"{label}: expected 1 match, found {count}"
    html = html.replace(old, new, 1)

# A separate contextual series: do not alter federal DATA.
replace_once(
    "let selected=2024;",
    "const STATE_TAX_DATA=" + json.dumps(state_data, separators=(",", ":")) +
    ";\nlet selected=2024;",
    "Insert DOR data"
)

# Add a statistic card, visible only on Slide 1.
replace_once(
    '<strong id="balance"></strong></div>',
    '<strong id="balance"></strong></div>'
    '<div class="stat" id="stateTaxStat" hidden>'
    '<span>WA State net tax collections</span>'
    '<strong id="stateTaxes"></strong></div>',
    "State tax statistic card"
)

# Update Slide 1 description.
replace_once(
    '<h2>Annual inflows versus IRS net collections</h2>',
    '<h2>Federal inflows, IRS net collections, and Washington State tax collections</h2>',
    "Slide 1 title"
)

replace_once(
    "Solid outline marks the selected year's paired bars. Click a year to change selection.",
    "Solid outline marks the selected year's three bars. Click a year to change selection.",
    "Slide 1 instructions"
)

# Add legend entry without changing the existing two entries.
replace_once(
    '<span><i class="swatch" style="background:#a0adb9"></i>IRS net collections</span>',
    '<span><i class="swatch" style="background:#a0adb9"></i>IRS net collections</span>'
    '<span><i class="swatch" style="background:#77965b"></i>'
    'WA State net tax collections</span>',
    "State tax legend"
)

# Make the three-entry legend wrap comfortably.
replace_once(
    '#annual .legend-reference-row .legend{display:flex;align-items:center;gap:22px;flex-wrap:wrap;margin:0;font-size:20px;',
    '#annual .legend-reference-row .legend{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:0;font-size:17px;',
    "Legend layout"
)

# Insert the fiscal-year qualification under the chart.
replace_once(
    '<div id="annualChart"></div><div class="legend-reference-row">',
    '<div id="annualChart"></div>'
    '<p class="muted" id="stateTaxNote">'
    '<strong>Fiscal-year comparison:</strong> Washington DOR state tax collections '
    'use July–June fiscal years; federal inflows and IRS collections use '
    'October–September federal fiscal years. State taxes are contextual '
    'and are not included in the federal fiscal balance.'
    '</p>'
    '<div class="legend-reference-row">',
    "Fiscal-year qualification"
)

# Replace only the annual chart renderer.
# The other two renderers remain unchanged.
start = html.index("function renderAnnual(){")
end = html.index("function renderStacked(){", start)

original_annual = html[start:end]

assert original_annual.count("function renderAnnual(){") == 1
assert "axis(180,[0,40,80,120,160])" in original_annual
assert "choose(" in original_annual

new_annual = """
function renderAnnual(){
 let s=axis(180,[0,40,80,120,160]);
 DATA.forEach((d,i)=>{
   const x=74+i*106,base=340,sc=320/180;
   const state=STATE_TAX_DATA.find(z=>z.year===d.year);
   if(!state)throw new Error('Missing DOR state tax year '+d.year);

   // Three narrower bars fit within the original year cluster.
   const width=20,gap=4;
   s+=rect(x,base-d.inflows*sc,width,d.inflows*sc,'#357b9f');
   s+=rect(x+width+gap,base-d.taxes*sc,width,d.taxes*sc,'#a0adb9');
   s+=rect(x+2*(width+gap),base-state.stateTaxes*sc,
           width,state.stateTaxes*sc,'#77965b');

   s+=label(x+34,365,d.year);

   if(d.year===selected)s+=selection(x-2,18,340,84);

   s+=rect(x-7,15,83,356,'transparent',
     `style="cursor:pointer" onclick="choose(${d.year})"`);
 });
 $('annualChart').innerHTML=svg(850,385,s);
}
"""

html = html[:start] + new_annual + html[end:]

replace_once(
    "(activeView==='annual'||activeView==='stacked'?"
    "'Federal inflows into Washington':",
    "(activeView==='annual'?"
    "'Federal inflows into WA':"
    "activeView==='stacked'?"
    "'Federal inflows into Washington':",
    "Slide 1 federal inflow caption"
)

# Update only the common render function's statistic handling.
replace_once(
    "function render(){let d=current();",
    "function render(){let d=current();"
    "let state=STATE_TAX_DATA.find(z=>z.year===selected);"
    "if(!state)throw new Error('Missing DOR year '+selected);"
    "$('stateTaxes').textContent=fmt(state.stateTaxes);"
    "$('stateTaxStat').hidden=activeView!=='annual';",
    "State tax card rendering"
)

# Validate the original federal observations remain byte-for-byte
# identical in the embedded DATA declaration.
def federal_data(source):
    match = re.search(r"const DATA=(.*?), NAMES=", source, re.S)
    assert match, "Federal DATA declaration not found"
    return json.loads(match.group(1))

original = SOURCE.read_text(encoding="utf-8-sig")
assert federal_data(html) == federal_data(original)

# Protect Slides 2 and 3: their render functions are unchanged.
for name, next_name in [
    ("renderStacked", "renderCovid"),
    ("renderCovid", "render"),
]:
    def extract_function(source):
        start = source.index(f"function {name}(){{")
        end = source.index(f"function {next_name}(){{", start)
        return source[start:end]
    assert extract_function(html) == extract_function(original), name

assert "const STATE_TAX_DATA=" in html
assert "stateTaxNote" in html
assert html.count("id=\"stateTaxStat\"") == 1
assert html.count("function renderAnnual(){") == 1

OUT.mkdir(parents=True, exist_ok=True)

# Never silently replace an existing, different preview.
if PREVIEW.exists():
    existing = PREVIEW.read_text(encoding="utf-8-sig")
    if existing != html:
        raise RuntimeError(f"Preview already exists with different content: {PREVIEW}")
else:
    PREVIEW.write_text(html, encoding="utf-8", newline="\n")

print("=== ETL-247B1 THREE-SERIES PREVIEW ===")
print(f"PREVIEW: {PREVIEW}")
print(f"BYTES: {PREVIEW.stat().st_size}")
print(f"DOR YEARS: {len(state_data)}")
print(f"DOR TOTAL: ${sum(amounts.values()):,.2f}")
print("FEDERAL DATA UNCHANGED: PASS")
print("SLIDE 2 RENDERER UNCHANGED: PASS")
print("SLIDE 3 RENDERER UNCHANGED: PASS")
print("FISCAL-YEAR QUALIFICATION: PASS")
print("PREVIEW GENERATION: PASS")
print("PUBLISHED PRESENTATION WRITES: NONE")
print("DATABASE WRITES: NONE")
