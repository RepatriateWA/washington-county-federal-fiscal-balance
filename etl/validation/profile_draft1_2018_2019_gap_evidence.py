from __future__ import annotations

import os
from pathlib import Path

import psycopg2


# ======================================================================================
# ETL-196 - DRAFT-1 2018-2019 GAP EVIDENCE AUDIT v0.1
#
# PURPOSE
# -------
# Determine whether existing WCFFBP evidence can support reconstruction of the
# remaining 2018/2019 DRAFT-1 expenditure components.
#
# READ ONLY.
#
# This script:
#   * does not write to PostgreSQL
#   * does not modify source files
#   * does not authorize ledger inclusion
#   * does not infer missing values
#   * does not convert calendar-year observations to FFY
#   * does not resolve overlap
#
# Target components:
#   1. USAspending assistance
#   2. USAspending procurement
#   3. SSI
#   4. ACA APTC
#   5. Military retired / survivor pay
#   6. OPM civilian retirement
# ======================================================================================


TARGET_YEARS = (2018, 2019)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------------------
# Files/directories that are useful evidence but should not themselves be treated as
# underlying source observations.
# --------------------------------------------------------------------------------------

IGNORE_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
}

IGNORE_FILE_NAMES = {
    "draft1_extension_years_profile.txt",
    "draft1_extension_years_profile_v0_2.txt",
    "draft1_extension_years_matrix.csv",
    "194_output.txt",
    "195_output.txt",
}

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".sql",
    ".py",
    ".ps1",
    ".yaml",
    ".yml",
}

SOURCE_SUFFIXES = {
    ".csv",
    ".xlsx",
    ".xls",
    ".zip",
    ".json",
    ".pdf",
    ".txt",
}


COMPONENTS = {
    "USASPENDING_ASSISTANCE": {
        "path_terms": (
            "usaspending",
            "assistance",
        ),
        "content_terms": (
            "assistance",
            "federal_action_obligation",
            "assistance_transaction",
        ),
    },

    "USASPENDING_PROCUREMENT": {
        "path_terms": (
            "usaspending",
            "procurement",
            "contract",
        ),
        "content_terms": (
            "procurement",
            "contract",
            "federal_action_obligation",
        ),
    },

    "SSI": {
        "path_terms": (
            "ssi",
            "supplemental_security_income",
            "supplemental security income",
        ),
        "content_terms": (
            "ssi",
            "supplemental security income",
        ),
    },

    "ACA_APTC": {
        "path_terms": (
            "aptc",
            "aca",
            "advance_premium_tax_credit",
            "advance premium tax credit",
        ),
        "content_terms": (
            "aptc",
            "advance premium tax credit",
            "premium tax credit",
        ),
    },

    "MILITARY_RETIRED_SURVIVOR": {
        "path_terms": (
            "military_ret",
            "military-ret",
            "retired_pay",
            "retirement_pay",
            "dfas",
        ),
        "content_terms": (
            "military retired",
            "military retirement",
            "retired pay",
            "survivor benefit",
            "dfas",
        ),
    },

    "OPM_CIVILIAN_RETIREMENT": {
        "path_terms": (
            "opm",
            "civilian_ret",
            "retirement",
            "annuit",
        ),
        "content_terms": (
            "civilian retirement",
            "opm retirement",
            "annuitant",
            "annuity",
        ),
    },
}


def banner(text: str) -> None:
    print()
    print("=" * 100)
    print(text)
    print("=" * 100)


def safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def year_tokens(year: int) -> tuple[str, ...]:
    yy = str(year)[-2:]
    return (
        str(year),
        f"fy{year}",
        f"fy_{year}",
        f"fy-{year}",
        f"fy{yy}",
        f"fy_{yy}",
        f"fy-{yy}",
    )


def contains_year(text: str, year: int) -> bool:
    lower = text.lower()
    return any(token.lower() in lower for token in year_tokens(year))


def path_component_score(path_text: str, component: dict) -> int:
    lower = path_text.lower()
    return sum(1 for term in component["path_terms"] if term.lower() in lower)


def content_component_score(text: str, component: dict) -> int:
    lower = text.lower()
    return sum(1 for term in component["content_terms"] if term.lower() in lower)


def looks_like_generated_profile(path: Path) -> bool:
    lower = str(path).lower()

    generated_terms = (
        "validation",
        "profile",
        "inventory",
        "output",
        "matrix",
        "report",
    )

    return any(term in lower for term in generated_terms)


def classify_file_role(path: Path) -> str:
    suffix = path.suffix.lower()
    lower = str(path).lower()

    if looks_like_generated_profile(path):
        return "EVIDENCE_OR_VALIDATION"

    if suffix in SOURCE_SUFFIXES:
        source_terms = (
            "data/raw",
            "data\\raw",
            "archive",
            "source",
            "download",
            "acquisition",
        )
        if any(term in lower for term in source_terms):
            return "SOURCE_OR_ARCHIVE"

    if suffix in {".py", ".sql", ".ps1"}:
        return "CODE"

    if suffix in {".md", ".txt", ".csv", ".json"}:
        return "DOCUMENTATION_OR_EVIDENCE"

    return "OTHER"


def inventory_repo_files() -> list[Path]:
    results: list[Path] = []

    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORE_DIR_NAMES for part in path.parts):
            continue

        if path.name in IGNORE_FILE_NAMES:
            continue

        results.append(path)

    return results


def scan_repository(files: list[Path]) -> dict:
    results = {
        component_name: {
            year: []
            for year in TARGET_YEARS
        }
        for component_name in COMPONENTS
    }

    for path in files:
        relative = safe_relative(path)
        relative_lower = relative.lower()

        path_scores = {
            component_name: path_component_score(relative_lower, definition)
            for component_name, definition in COMPONENTS.items()
        }

        candidate_components = {
            name
            for name, score in path_scores.items()
            if score > 0
        }

        if not candidate_components:
            continue

        matching_years = [
            year
            for year in TARGET_YEARS
            if contains_year(relative_lower, year)
        ]

        # If the path itself does not identify 2018/2019, inspect small text-like
        # evidence/code files for explicit year references.
        content = None

        if (
            not matching_years
            and path.suffix.lower() in TEXT_SUFFIXES
        ):
            try:
                if path.stat().st_size <= 2_000_000:
                    content = path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    matching_years = [
                        year
                        for year in TARGET_YEARS
                        if contains_year(content, year)
                    ]
            except OSError:
                content = None

        if not matching_years:
            continue

        for component_name in candidate_components:
            definition = COMPONENTS[component_name]

            cscore = 0
            if content is not None:
                cscore = content_component_score(content, definition)

            record = {
                "path": relative,
                "role": classify_file_role(path),
                "path_score": path_scores[component_name],
                "content_score": cscore,
                "size_bytes": path.stat().st_size,
            }

            for year in matching_years:
                results[component_name][year].append(record)

    return results


def connect_db():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )


def fetchall(cur, sql: str, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def db_object_inventory(cur) -> list[tuple]:
    return fetchall(
        cur,
        """
        SELECT
            table_schema,
            table_name,
            table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN (
            'pg_catalog',
            'information_schema'
        )
        ORDER BY
            table_schema,
            table_name
        """
    )


def db_column_inventory(cur) -> list[tuple]:
    return fetchall(
        cur,
        """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN (
            'pg_catalog',
            'information_schema'
        )
        ORDER BY
            table_schema,
            table_name,
            ordinal_position
        """
    )


def identify_candidate_db_objects(
    objects: list[tuple],
    columns: list[tuple],
) -> dict:
    results = {
        component_name: []
        for component_name in COMPONENTS
    }

    column_map: dict[tuple[str, str], list[str]] = {}

    for schema, table, column, _dtype in columns:
        column_map.setdefault((schema, table), []).append(column)

    for schema, table, table_type in objects:
        object_text = f"{schema}.{table}".lower()
        cols = column_map.get((schema, table), [])
        combined_text = object_text + " " + " ".join(cols).lower()

        for component_name, definition in COMPONENTS.items():
            terms = tuple(
                term.lower()
                for term in (
                    definition["path_terms"]
                    + definition["content_terms"]
                )
            )

            matched_terms = sorted({
                term
                for term in terms
                if term in combined_text
            })

            if matched_terms:
                results[component_name].append({
                    "schema": schema,
                    "table": table,
                    "table_type": table_type,
                    "matched_terms": matched_terms,
                    "columns": cols,
                })

    return results


def query_year_presence(
    cur,
    schema: str,
    table: str,
    columns: list[str],
) -> list[dict]:
    candidate_year_columns = [
        "fiscal_year",
        "report_year",
        "calendar_year",
        "action_date_fiscal_year",
    ]

    year_column = next(
        (
            column
            for column in candidate_year_columns
            if column in columns
        ),
        None,
    )

    if year_column is None:
        return []

    quoted_schema = '"' + schema.replace('"', '""') + '"'
    quoted_table = '"' + table.replace('"', '""') + '"'
    quoted_year = '"' + year_column.replace('"', '""') + '"'

    sql = f"""
        SELECT
            {quoted_year},
            COUNT(*)::bigint
        FROM {quoted_schema}.{quoted_table}
        WHERE {quoted_year} IN (2018, 2019)
        GROUP BY {quoted_year}
        ORDER BY {quoted_year}
    """

    try:
        rows = fetchall(cur, sql)
    except Exception:
        cur.connection.rollback()
        cur.execute("SET TRANSACTION READ ONLY")
        return []

    return [
        {
            "year_column": year_column,
            "year": row[0],
            "row_count": row[1],
        }
        for row in rows
    ]


def print_repo_results(repo_results: dict) -> None:
    banner("A. REPOSITORY EVIDENCE")

    for component_name in COMPONENTS:
        print()
        print(component_name)
        print("-" * 100)

        for year in TARGET_YEARS:
            records = repo_results[component_name][year]

            print(f"{year}: {len(records)} candidate file(s)")

            ranked = sorted(
                records,
                key=lambda r: (
                    r["role"] != "SOURCE_OR_ARCHIVE",
                    -r["path_score"],
                    -r["content_score"],
                    r["path"].lower(),
                ),
            )

            for record in ranked[:20]:
                print(
                    f"  [{record['role']}] "
                    f"{record['path']}"
                )

            if len(ranked) > 20:
                print(
                    f"  ... {len(ranked) - 20} additional candidate file(s) omitted"
                )


def print_db_results(cur, db_candidates: dict) -> None:
    banner("B. POSTGRESQL CANDIDATE OBJECTS")

    for component_name in COMPONENTS:
        print()
        print(component_name)
        print("-" * 100)

        objects = db_candidates[component_name]

        if not objects:
            print("No candidate database objects identified.")
            continue

        for obj in objects:
            schema = obj["schema"]
            table = obj["table"]
            columns = obj["columns"]

            print(
                f"{schema}.{table} "
                f"[{obj['table_type']}]"
            )
            print(
                "  matched terms: "
                + ", ".join(obj["matched_terms"])
            )

            year_presence = query_year_presence(
                cur,
                schema,
                table,
                columns,
            )

            if year_presence:
                for item in year_presence:
                    print(
                        f"  {item['year_column']}={item['year']}: "
                        f"{item['row_count']} row(s)"
                    )
            else:
                print(
                    "  no affirmative 2018/2019 year-row evidence "
                    "from recognized year columns"
                )


def derive_status(
    repo_results: dict,
    db_candidates: dict,
    cur,
) -> None:
    banner("C. CONSERVATIVE GAP STATUS")

    print(
        "Status vocabulary:"
    )
    print(
        "  AVAILABLE                  = affirmative 2018/2019 DB rows plus repository evidence"
    )
    print(
        "  SOURCE_PRESENT_NOT_NORMALIZED = source/archive evidence exists but no affirmative DB rows"
    )
    print(
        "  DB_PRESENT_SOURCE_UNCLEAR  = affirmative DB rows but no identified source/archive evidence"
    )
    print(
        "  MISSING                    = neither affirmative DB rows nor identified source/archive evidence"
    )
    print()
    print(
        "These are evidence-availability statuses only. AVAILABLE does not authorize ledger inclusion."
    )
    print()

    for component_name in COMPONENTS:
        print(component_name)

        objects = db_candidates[component_name]

        db_years = set()

        for obj in objects:
            for item in query_year_presence(
                cur,
                obj["schema"],
                obj["table"],
                obj["columns"],
            ):
                db_years.add(item["year"])

        for year in TARGET_YEARS:
            source_records = [
                r
                for r in repo_results[component_name][year]
                if r["role"] == "SOURCE_OR_ARCHIVE"
            ]

            has_source = bool(source_records)
            has_db = year in db_years

            if has_source and has_db:
                status = "AVAILABLE"
            elif has_source and not has_db:
                status = "SOURCE_PRESENT_NOT_NORMALIZED"
            elif has_db and not has_source:
                status = "DB_PRESENT_SOURCE_UNCLEAR"
            else:
                status = "MISSING"

            print(
                f"  {year}: {status}"
                f" | source/archive files={len(source_records)}"
                f" | affirmative DB year={has_db}"
            )

        print()


def main() -> None:
    banner("ETL-196 - DRAFT-1 2018-2019 GAP EVIDENCE AUDIT v0.1")

    print(f"Repository root : {REPO_ROOT}")
    print(f"Target years    : {', '.join(map(str, TARGET_YEARS))}")
    print("Mode            : READ ONLY")
    print()
    print("No accounting values are calculated by this script.")
    print("No missing observations are interpreted as zero.")

    files = inventory_repo_files()

    print()
    print(f"Repository files inventoried: {len(files):,}")

    repo_results = scan_repository(files)

    conn = connect_db()

    try:
        conn.set_session(readonly=True, autocommit=False)

        cur = conn.cursor()

        objects = db_object_inventory(cur)
        columns = db_column_inventory(cur)

        db_candidates = identify_candidate_db_objects(
            objects,
            columns,
        )

        print_repo_results(repo_results)
        print_db_results(cur, db_candidates)
        derive_status(
            repo_results,
            db_candidates,
            cur,
        )

        conn.rollback()

    finally:
        conn.close()

    banner("ETL-196 COMPLETE")
    print("READ ONLY")
    print("No database writes performed.")
    print("No source files modified.")
    print("No accounting classifications changed.")
    print("No ledger inclusion decisions made.")
    print("No missing values inferred.")


if __name__ == "__main__":
    main()