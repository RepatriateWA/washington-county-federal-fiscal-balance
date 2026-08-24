import glob
import json
from pathlib import Path


files = sorted(
    glob.glob(
        "data/raw/bea/compensation/documentation/"
        "cainc6n_linecode_metadata_*.json"
    )
)

if not files:
    raise SystemExit("No CAINC6N metadata file found.")

path = Path(files[-1])

with path.open("r", encoding="utf-8") as f:
    payload = json.load(f)

print(f"Metadata file: {path}")
print()


def walk(value, path="root"):
    if isinstance(value, dict):
        text = " | ".join(
            str(v)
            for v in value.values()
            if isinstance(v, (str, int, float))
        )

        if any(
            term in text.lower()
            for term in (
                "federal",
                "civilian",
                "military",
            )
        ):
            print(path)
            print(json.dumps(value, indent=2))
            print("-" * 72)

        for key, child in value.items():
            walk(child, f"{path}.{key}")

    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}[{index}]")


walk(payload)