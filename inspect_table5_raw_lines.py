from pathlib import Path

from etl.pdf.databook import extract_table_text


def inspect_lines(year: int, names: list[str]) -> None:
    pdf_file = Path(
        f"data/raw/irs_databook/{year}/irs_databook_{year}.pdf"
    )

    text = extract_table_text(pdf_file, 5)
    continued_marker = "—Continued"

    _, second_text = text.split(continued_marker, 1)

    if "Footnotes" in second_text:
        second_text = second_text.split("Footnotes", 1)[0]

    print(f"\nFY{year} SECOND HALF")

    for line_number, line in enumerate(second_text.splitlines(), start=1):
        if any(name.lower() in line.lower() for name in names):
            print(f"{line_number}: {line}")


inspect_lines(
    2015,
    ["Arkansas", "California", "Colorado"],
)

inspect_lines(
    2017,
    [
        "Georgia",
        "Hawaii",
        "Idaho",
        "New Jersey",
        "New Mexico",
        "New York",
    ],
)
