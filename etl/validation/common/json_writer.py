from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonWriter:
    """
    Writes JSON documents using the project's standard formatting.
    """

    def write(
        self,
        path: Path,
        document: dict[str, Any],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as fp:
            json.dump(
                document,
                fp,
                indent=2,
                sort_keys=False,
                ensure_ascii=False,
            )
            fp.write("\n")