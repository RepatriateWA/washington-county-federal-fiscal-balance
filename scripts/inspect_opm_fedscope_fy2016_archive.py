from __future__ import annotations

import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SOURCE_DIR = (
    ROOT
    / "data"
    / "raw"
    / "opm"
    / "fedscope"
    / "employment"
    / "2016-09"
)


def find_latest_zip() -> Path:
    matches = sorted(
        SOURCE_DIR.glob(
            "opm_fedscope_employment_201609_"
            "raw_data_retrieved_*.zip"
        )
    )

    if not matches:
        raise RuntimeError(
            f"No FY2016 FedScope ZIP found under {SOURCE_DIR}"
        )

    return matches[-1]


def decode_sample(raw: bytes) -> tuple[str, str]:
    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    return raw.decode(
        "latin-1",
        errors="replace",
    ), "latin-1-replace"


def looks_textual(name: str) -> bool:
    suffix = Path(name).suffix.lower()

    return suffix in {
        ".txt",
        ".csv",
        ".dat",
        ".tsv",
        ".asc",
        ".lst",
    }


def main() -> None:
    source = find_latest_zip()

    print("=" * 78)
    print("OPM FEDSCOPE FY2016 ZIP STRUCTURAL INSPECTION")
    print("=" * 78)
    print(f"Source: {source}")
    print()

    with zipfile.ZipFile(source, "r") as zf:
        members = [
            info
            for info in zf.infolist()
            if not info.is_dir()
        ]

        print(f"Archive members: {len(members)}")
        print()

        print("MEMBER INVENTORY")
        print("-" * 78)

        for i, info in enumerate(
            members,
            start=1,
        ):
            ratio = (
                info.compress_size / info.file_size
                if info.file_size
                else 0
            )

            print(
                f"{i:3d}. "
                f"{info.filename}"
            )

            print(
                f"     uncompressed: "
                f"{info.file_size:,} bytes"
            )

            print(
                f"     compressed:   "
                f"{info.compress_size:,} bytes"
            )

            print(
                f"     ratio:        "
                f"{ratio:.3f}"
            )

        print()
        print("=" * 78)
        print("TEXT FILE SAMPLES")
        print("=" * 78)

        text_members = [
            info
            for info in members
            if looks_textual(info.filename)
        ]

        if not text_members:
            print(
                "No obvious text-format members found."
            )
            return

        for info in text_members:
            print()
            print("-" * 78)
            print(info.filename)
            print("-" * 78)

            with zf.open(info, "r") as f:
                raw = f.read(
                    min(
                        info.file_size,
                        16_384,
                    )
                )

            text, encoding = decode_sample(raw)

            print(
                f"Detected sample encoding: {encoding}"
            )

            lines = text.splitlines()

            print(
                f"Sample lines available: {len(lines)}"
            )

            for line_number, line in enumerate(
                lines[:8],
                start=1,
            ):
                # Keep terminal output manageable.
                if len(line) > 500:
                    line = (
                        line[:500]
                        + " ... [truncated]"
                    )

                print(
                    f"{line_number:2d}: {line}"
                )


if __name__ == "__main__":
    main()