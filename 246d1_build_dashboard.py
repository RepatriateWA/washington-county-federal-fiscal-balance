import csv
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "docs/presentations/wcffbp-246d"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE = ROOT / "246c3_stacked_components_candidate.csv"
CONTEXT = ROOT / "docs/presentations/wcffbp-244b/data/244b_chart_data.csv"

def read(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

rows = read(SOURCE)
context = {int(r["fiscal_year"]): r for r in read(CONTEXT)}

names = [
    ("SSA_OASDI", "Social Security"),
    ("MEDICARE_FFS_AB", "Medicare A/B"),
    ("MEDICARE_PART_C", "Medicare C"),
    ("MEDICARE_PART_D", "Medicare D"),
    ("MEDICAID", "Medicaid"),
    ("CHIP", "CHIP"),
    ("VA_GDX", "Veterans / VA"),
    ("FEDERAL_CIVILIAN_WAGES", "Civilian wages"),
    ("FEDERAL_MILITARY_WAGES", "Military wages"),
    ("USASPENDING_ASSISTANCE_ADDITIVE", "Assistance obligations"),
    ("ADDITIONAL_QUALIFIED_ASSISTANCE", "Additional assistance"),
    ("DOD_PROCUREMENT_OBLIGATIONS", "DoD procurement"),
    ("DOE_PROCUREMENT_OBLIGATIONS", "DOE procurement"),
    ("OTHER_NON_VA_PROCUREMENT_OBLIGATIONS", "Other procurement"),
    ("MILITARY_RETIREMENT_MODELED", "Military retirement (modeled)"),
]

colors = [
    "#4263a3", "#327fa4", "#4ba3b1", "#91cbd0",
    "#47865e", "#8fbf7c", "#9063a5", "#c58c48",
    "#e1b65f", "#c26b5b", "#e7a28b", "#305b91",
    "#d19b42", "#8796a6", "#785c9d"
]

data = []
seven = Decimal("0")
for r in rows:
    year = int(r["fiscal_year"])
    parts = [Decimal(r[k]) for k, _ in names]
    inflows = Decimal(r["revised_inflows_usd"])
    taxes = Decimal(r["irs_net_collections_usd"])
    balance = Decimal(r["revised_balance_usd"])

    assert len(parts) == 15
    assert sum(parts) == inflows
    assert inflows - taxes == balance

    seven += balance
    c = context[year]

    data.append({
        "year": year,
        "parts": [float(x / Decimal("1e9")) for x in parts],
        "inflows": float(inflows / Decimal("1e9")),
        "taxes": float(taxes / Decimal("1e9")),
        "balance": float(balance / Decimal("1e9")),
        "covid": float(c["covid_tagged_assistance_billion_usd"]),
        "iija": float(c["iija_tagged_assistance_billion_usd"]),
        "both": float(c["covid_iija_overlap_billion_usd"]),
    })

assert len(data) == 7
assert seven == Decimal("-85863188344.12")

html = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Washington Federal Fiscal Balance — Revised Candidate</title>
<style>
:root{font-family:system-ui,Segoe UI,Arial,sans-serif;color:#183345;background:#f3f7fa}
*{box-sizing:border-box}
body{margin:0}
main{max-width:1200px;margin:auto;padding:24px}
h1{margin-bottom:6px}
h2{font-size:1.2rem}
p{line-height:1.55}
.muted{color:#536d7d}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}
button{padding:11px 15px;border:1px solid #bacdd8;background:white;border-radius:8px;cursor:pointer;font:inherit}
button.active{background:#204d68;color:white}
.card{background:white;border:1px solid #dae4ea;border-radius:12px;padding:20px;margin:14px 0}
.stats{display:flex;flex-wrap:wrap;gap:12px}
.stat{flex:1;min-width:180px;padding:14px;background:#eef3f6;border-radius:8px}
.stat strong{display:block;font-size:1.45rem;margin-top:5px}
.warning{font-weight:700;color:#84552c}
svg{width:100%;height:auto}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:.82rem;margin-top:12px}
.swatch{display:inline-block;width:12px;height:12px;margin-right:5px}
table{width:100%;border-collapse:collapse}
td{padding:8px;border-bottom:1px solid #e6edf0}
td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:14px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
<h1>Washington's Federal Fiscal Balance</h1>
<p class="muted">FY2018–2024 · Revised fifteen-component provisional candidate</p>
<p class="warning">MIXED MEASURES · NOT CERTIFIED CASH FLOWS · NOT LEDGER-AUTHORIZED</p>

<div class="stats">
<div class="stat">Selected year<strong id="year"></strong></div>
<div class="stat">Federal inflows<strong id="inflows"></strong></div>
<div class="stat">IRS net collections<strong id="taxes"></strong></div>
<div class="stat">Fiscal balance<strong id="balance"></strong></div>
</div>

<div class="tabs">
<button class="active" data-view="annual">1 · Annual balance</button>
<button data-view="stacked">2 · Stacked inflows</button>
<button data-view="covid">3 · COVID / IIJA</button>
<button data-view="agency">4 · DoD / DOE / Hanford</button>
</div>

<section id="annual" class="card">
<h2>Annual identified inflows versus IRS net collections</h2>
<div id="annualChart"></div>
<p>Seven-year revised provisional balance: <strong>−$85.863 billion</strong>.</p>
</section>

<section id="stacked" class="card" hidden>
<h2>Fifteen-component federal inflows</h2>
<p class="muted">Click a year to inspect the component values. All segments reconcile to the annual candidate balance.</p>
<div class="grid">
<div><div id="stackedChart"></div><div id="legend" class="legend"></div></div>
<div><h2 id="detailTitle"></h2><table id="details"></table></div>
</div>
</section>

<section id="covid" class="card" hidden>
<h2>COVID and IIJA assistance tags</h2>
<p>These are annotations within previously included assistance, not additional inflows.</p>
<div id="covidChart"></div>
<p id="covidDetail"></p>
</section>

<section id="agency" class="card" hidden>
<h2>DoD and DOE procurement obligations</h2>
<p class="muted">These amounts are now included in the statewide candidate balance and stacked inflows.</p>
<div id="agencyChart"></div>
<p id="agencyDetail"></p>
<p><strong>Hanford:</strong> A separately verified site-specific series has not yet been isolated. DOE procurement is not synonymous with Hanford expenditure.</p>
</section>

<div class="card">
<h2>Evidence and qualifications</h2>
<p>Source: ETL-246C3 fifteen-component reconciliation, ETL-246C2 annual balance, and ETL-244B COVID/IIJA tags. Procurement and assistance include federal obligations rather than necessarily cash outlays. Military retirement is modeled. VA procurement is withheld pending overlap review. Timing differences, overlap, geographic economic incidence, and other coverage limitations remain unresolved. No canonical ledger authorization is implied.</p>
</div>
</main>
<script>
const DATA=__DATA__;
const NAMES=__NAMES__;
const COLORS=__COLORS__;
let selected=2024;
const $=id=>document.getElementById(id);
const fmt=x=>(x<0?"−":"")+"$"+Math.abs(x).toFixed(2)+"B";
const current=()=>DATA.find(d=>d.year===selected);
function svg(w,h,content){return `<svg viewBox="0 0 ${w} ${h}" role="img">${content}</svg>`}
function rect(x,y,w,h,color){return `<rect x="${x}" y="${y}" width="${w}" height="${Math.max(0,h)}" fill="${color}"/>`}
function label(x,y,s,anchor="middle"){return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-size="12" fill="#4f6574">${s}</text>`}
function choose(y){selected=y;render()}
function render(){
 const d=current();
 $("year").textContent="FY"+selected;
 $("inflows").textContent=fmt(d.inflows);
 $("taxes").textContent=fmt(d.taxes);
 $("balance").textContent=fmt(d.balance);
 renderAnnual();renderStacked();renderCovid();renderAgency();
}
function renderAnnual(){
 let s="";
 DATA.forEach((d,i)=>{
   const x=60+i*110,b=340,scale=2.0;
   s+=rect(x,b-d.inflows*scale,32,d.inflows*scale,"#357b9f");
   s+=rect(x+36,b-d.taxes*scale,32,d.taxes*scale,"#a0adb9");
   s+=label(x+34,364,d.year);
   s+=`<rect x="${x}" y="15" width="75" height="350" fill="transparent" onclick="choose(${d.year})" style="cursor:pointer"/>`;
 });
 $("annualChart").innerHTML=svg(850,385,s)+
 '<p class="muted">Blue: revised inflows · Gray: IRS net collections · Click a year</p>';
}
function renderStacked(){
 let s="";
 DATA.forEach((d,i)=>{
   let x=55+i*96,y=385;
   d.parts.forEach((v,j)=>{
     const h=v*2.8;y-=h;
     s+=rect(x,y,58,h,COLORS[j]);
   });
   s+=label(x+29,410,d.year);
   s+=`<rect x="${x}" y="0" width="58" height="385" fill="transparent" onclick="choose(${d.year})" style="cursor:pointer"/>`;
 });
 $("stackedChart").innerHTML=svg(760,430,s);
 $("legend").innerHTML=NAMES.map((n,i)=>`<span><i class="swatch" style="background:${COLORS[i]}"></i>${n}</span>`).join("");
 $("detailTitle").textContent="FY"+selected+" components";
 $("details").innerHTML=current().parts.map((v,i)=>`<tr><td>${NAMES[i]}</td><td>${fmt(v)}</td></tr>`).join("")+
 `<tr><td><strong>Total inflows</strong></td><td><strong>${fmt(current().inflows)}</strong></td></tr>`;
}
function renderCovid(){
 let s="";
 DATA.forEach((d,i)=>{
   let x=55+i*96,b=310;
   s+=rect(x,b-d.covid*8,26,d.covid*8,"#cb7654");
   s+=rect(x+30,b-d.iija*8,26,d.iija*8,"#7b9eaf");
   s+=label(x+28,332,d.year);
   s+=`<rect x="${x}" y="0" width="62" height="310" fill="transparent" onclick="choose(${d.year})" style="cursor:pointer"/>`;
 });
 $("covidChart").innerHTML=svg(760,350,s)+
 '<p class="muted">Orange: COVID-tagged assistance · Blue-gray: IIJA-tagged assistance · Tags may overlap</p>';
 let d=current();
 $("covidDetail").textContent=`FY${selected}: COVID ${fmt(d.covid)}, IIJA ${fmt(d.iija)}, overlapping tags ${fmt(d.both)}. These amounts must not be added again.`;
}
function renderAgency(){
 let s="";
 DATA.forEach((d,i)=>{
   let x=55+i*96,b=320,scale=14;
   let dod=d.parts[11],doe=d.parts[12],other=d.parts[13];
   s+=rect(x,b-dod*scale,19,dod*scale,"#305b91");
   s+=rect(x+22,b-doe*scale,19,doe*scale,"#d19b42");
   s+=rect(x+44,b-other*scale,19,other*scale,"#8796a6");
   s+=label(x+31,344,d.year);
   s+=`<rect x="${x}" y="0" width="65" height="320" fill="transparent" onclick="choose(${d.year})" style="cursor:pointer"/>`;
 });
 $("agencyChart").innerHTML=svg(760,360,s)+
 '<p class="muted">Blue: DoD · Gold: DOE · Gray: other non-VA procurement · Click a year</p>';
 let d=current();
 $("agencyDetail").textContent=`FY${selected}: DoD ${fmt(d.parts[11])}; DOE ${fmt(d.parts[12])}; other non-VA ${fmt(d.parts[13])}. All three are included in revised statewide inflows.`;
}
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>{
 document.querySelectorAll("[data-view]").forEach(z=>z.classList.toggle("active",z===b));
 document.querySelectorAll("section[id]").forEach(s=>s.hidden=s.id!==b.dataset.view);
});
render();
</script>
</body></html>"""

page = (
    html.replace("__DATA__", json.dumps(data, separators=(",", ":")))
        .replace("__NAMES__", json.dumps([label for _, label in names]))
        .replace("__COLORS__", json.dumps(colors))
)

target = OUT / "index.html"
target.write_text(page, encoding="utf-8")

report = [
    "ETL-246D1 - REVISED INTERACTIVE DASHBOARD",
    "PASS: Seven years",
    "PASS: Fifteen components per year",
    "PASS: Exact annual source-dollar reconciliation",
    f"PASS: Seven-year balance {seven:,.2f}",
    f"HTML: {target}",
    "STATUS: QUALIFIED_PROVISIONAL_CANDIDATE",
    "Original ETL-244B presentation unchanged",
]
(OUT / "246d1_validation.txt").write_text(
    "\n".join(report) + "\n", encoding="utf-8"
)
print("\n".join(report))
