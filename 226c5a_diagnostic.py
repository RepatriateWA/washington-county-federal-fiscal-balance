from pathlib import Path
import re

p = Path("226c4_stdout.txt")

print("File:", p.resolve())
print("Exists:", p.exists())

if not p.exists():
    raise SystemExit(1)

lines = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()

print("Total lines:", len(lines))

for i, line in enumerate(lines[:15], 1):
    print(f"{i:03d}: {line[:180]!r}")

matches = [
    line for line in lines
    if re.match(r"^\s*20(?:18|19|20|21|22|23|24)\s*\|", line)
]

print("Matching data rows:", len(matches))

if matches:
    print("First matching row:", repr(matches[0][:250]))
