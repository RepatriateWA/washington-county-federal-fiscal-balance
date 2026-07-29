from pathlib import Path
import json

from etl.validation.common.json_writer import JsonWriter


output = Path("evidence/test/output.json")

document = {
    "hello": "world",
    "value": 42,
    "items": [
        "A",
        "B",
        "C",
    ],
}

JsonWriter().write(output, document)

loaded = json.loads(output.read_text(encoding="utf-8"))

assert loaded == document

print("JSON written to:")
print(output)

print("\nJsonWriter smoke test passed.")