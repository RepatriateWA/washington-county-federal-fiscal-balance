from pathlib import Path
from typing import Dict, List

import pandas as pd
import pdfplumber


TABLE5_FIRST_HALF_KEYS = [
    "state_name",
    "total_collections",
    "business_income_taxes",
    "individual_employment_estate_trust",
    "withheld_fica",
    "payments_seca",
]

TABLE5_SECOND_HALF_KEYS = [
    "state_name",
    "unemployment_insurance_tax",
    "railroad_retirement_tax",
    "estate_trust_income_tax",
    "estate_tax",
    "gift_tax",
    "excise_taxes",
]


def _to_int(value: str):
    value = value.replace(",", "").strip()

    try:
        return int(round(float(value)))
    except ValueError:
        return None


def _is_number(token: str) -> bool:
    token = token.replace(",", "").replace(".", "").replace("-", "")
    return token.isdigit()


def find_table_pages(pdf_file: Path, table_number: int) -> List[int]:
    matches = []
    table_label = f"Table {table_number}."

    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""

            if table_label in text and "List of Statistical Tables" not in text:
                matches.append(i)

    return matches


def extract_table_text(pdf_file: Path, table_number: int) -> str:
    pages = find_table_pages(pdf_file, table_number)
    chunks = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_number in pages:
            page = pdf.pages[page_number - 1]
            chunks.append(page.extract_text() or "")

    return "\n".join(chunks)


def _parse_rows(text: str, expected_numbers: int, keys: List[str]) -> List[Dict]:
    rows = []

    for line in text.splitlines():
        parts = line.split()

        if len(parts) < expected_numbers + 1:
            continue

        numeric_positions = [
            i for i, token in enumerate(parts)
            if _is_number(token)
        ]

        if len(numeric_positions) < expected_numbers:
            continue

        first_num = numeric_positions[0]
        state_name = " ".join(parts[:first_num]).strip()

        if not state_name:
            continue

        skip_prefixes = {
            "Download",
            "Table",
            "[Money",
            "Individual",
            "Total Internal",
            "Revenue",
            "State or",
            "and estate",
            "Footnotes",
            "NOTES:",
            "SOURCE:",
        }

        if any(state_name.startswith(prefix) for prefix in skip_prefixes):
            continue

        values = [_to_int(parts[i]) for i in numeric_positions[:expected_numbers]]

        if any(v is None for v in values):
            continue

        row = {"state_name": state_name}

        for key, value in zip(keys[1:], values):
            row[key] = value

        rows.append(row)

    return rows


def extract_table5_dataframe(pdf_file: Path) -> pd.DataFrame:
    text = extract_table_text(pdf_file, 5)

    if "Table 5. Gross Collections, by Type of Tax and State" not in text:
        raise ValueError("Could not locate Table 5 text.")

    first_marker = "Table 5. Gross Collections, by Type of Tax and State, Fiscal Year"
    continued_marker = "—Continued"
    footnotes_marker = "Footnotes"

    if continued_marker not in text:
        raise ValueError("Could not locate Table 5 continued section.")

    first_text = text.split(continued_marker)[0]
    second_text = text.split(continued_marker, 1)[1]

    if footnotes_marker in second_text:
        second_text = second_text.split(footnotes_marker)[0]

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

    second_by_state = {
        row["state_name"]: row
        for row in second_rows
    }

    merged = []

    for row in first_rows:
        state = row["state_name"]

        if state not in second_by_state:
            continue

        merged_row = {
            **row,
            **{
                key: value
                for key, value in second_by_state[state].items()
                if key != "state_name"
            },
        }

        merged.append(merged_row)

    return pd.DataFrame(merged)