import glob
import json
from pathlib import Path


files = sorted(
    glob.glob(
        "data/raw/bea/compensation/county/"
        "cainc6n_federal_civilian_*.json"
    )
)

if not files:
    raise SystemExit("No CAINC6N federal civilian response found.")

path = Path(files[-1])

with path.open("r", encoding="utf-8") as f:
    payload = json.load(f)

print(f"Response file: {path}")
print()

beaapi = payload.get("BEAAPI", {})

print("Top-level BEAAPI keys:")
print(list(beaapi.keys()))
print()

print("Results:")
print(
    json.dumps(
        beaapi.get("Results"),
        indent=2,
    )
)