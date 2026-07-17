from pathlib import Path

from etl.pdf.databook import (
    TABLE5_FIRST_HALF_KEYS,
    TABLE5_SECOND_HALF_KEYS,
    _parse_rows,
    extract_table_text,
)


def inspect_year(year: int, target_states: list[str]) -> None:
    pdf_file = Path(
        f"data/raw/irs_databook/{year}/irs_databook_{year}.pdf"
    )

    text = extract_table_text(pdf_file, 5)

    continued_marker = "—Continued"

    if continued_marker not in text:
        raise ValueError(
            f"Continued marker not found in {pdf_file}"
        )

    first_text, second_text = text.split(continued_marker, 1)

    if "Footnotes" in second_text:
        second_text = second_text.split("Footnotes", 1)[0]

    first_rows = _parse_rows(
        first_text,
        expected_numbers=5,
        keys=TABLE5_FIRST_HALF_KEYS,
    )

    second_rows = _parse_rows(
        second_text,
        expected_numbers=6,
        keys=TABLE5_SECOND_HALF_KEYS,
    )

    print(f"\nFY{year}")

    for target_state in target_states:
        first_matches = [
            row
            for row in first_rows
            if target_state.lower() in row["state_name"].lower()
        ]

        second_matches = [
            row
            for row in second_rows
            if target_state.lower() in row["state_name"].lower()
        ]

        print(f"\n{target_state}")
        print("FIRST HALF:")
        print(first_matches or "Not found")

        print("SECOND HALF:")
        print(second_matches or "Not found")


inspect_year(2015, ["California"])
inspect_year(2017, ["Hawaii", "New Mexico"])
