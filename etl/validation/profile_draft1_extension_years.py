"""
WCFFBP DRAFT-1 Extension-Year Completeness Profiler
====================================================

Purpose
-------
Inventory existing WCFFBP work product relevant to candidate extension years:

    FFY 2018
    FFY 2019
    FFY 2025

This is a DISCOVERY / PROFILING script only.

It does NOT:
    * write to PostgreSQL
    * alter repository files
    * download source data
    * classify accounting treatment
    * infer missing values
    * annualize partial observations
    * certify a component for ledger inclusion
    * calculate a federal fiscal balance

The profiler examines:

    1. Local repository/source/evidence filenames
    2. Small text-like files for explicit year/component references
    3. PostgreSQL schemas/tables/views
    4. Candidate year columns in PostgreSQL objects
    5. Observed year coverage where it can be queried safely

The resulting classifications are intentionally conservative:

    EVIDENCE_FOUND
    DB_YEAR_FOUND
    FILE_AND_DB_EVIDENCE
    PRESENT_NEEDS_REVIEW
    NOT_FOUND_BY_PROFILER

"NOT_FOUND_BY_PROFILER" does NOT mean the source does not exist.
It means this profiler did not locate affirmative evidence under its
current discovery rules.

Run from repository root.

Example:

    python etl/validation/profile_draft1_extension_years.py `
        > draft1_extension_years_profile.txt 2>&1

Optional database connection environment variables:

    PGHOST
    PGPORT
    PGDATABASE
    PGUSER
    PGPASSWORD

Defaults:
    host     localhost
    port     5432
    database wcffbp
    user     postgres

Security
--------
The script never prints PGPASSWORD.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    psycopg2 = None
    sql = None


# =============================================================================
# Configuration
# =============================================================================

TARGET_YEARS = (2018, 2019, 2025)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that can be enormous, irrelevant, generated, or unsafe/noisy
# for recursive evidence inspection.
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}

# Files larger than this are inventoried by NAME/PATH only and are not opened.
MAX_TEXT_SCAN_BYTES = 5 * 1024 * 1024  # 5 MiB

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".sql",
    ".py",
    ".ps1",
    ".log",
}

# Candidate PostgreSQL year columns.
# We do not assume all are equivalent concepts.
YEAR_COLUMN_NAMES = {
    "year",
    "fiscal_year",
    "fiscalyear",
    "fy",
    "ffy",
    "tax_year",
    "calendar_year",
    "report_year",
    "payment_year",
    "award_year",
    "budget_year",
    "data_year",
}

# Some tables may store dates rather than explicit year columns.
DATE_COLUMN_HINTS = {
    "date",
    "action_date",
    "transaction_date",
    "payment_date",
    "period_start",
    "period_end",
    "fiscal_date",
    "report_date",
}

# Do not profile system schemas.
SYSTEM_SCHEMAS = {
    "pg_catalog",
    "information_schema",
}

# Limit displayed evidence so output remains useful.
MAX_PATHS_PER_COMPONENT_YEAR = 20
MAX_DB_OBJECTS_PER_COMPONENT_YEAR = 30


# =============================================================================
# Component definitions
# =============================================================================

@dataclass(frozen=True)
class ComponentDefinition:
    key: str
    label: str
    path_terms: tuple[str, ...]
    text_terms: tuple[str, ...]
    db_terms: tuple[str, ...]


COMPONENTS = (
    ComponentDefinition(
        key="irs_gross",
        label="IRS gross collections",
        path_terms=("irs", "databook", "collections"),
        text_terms=(
            "gross collections",
            "irs data book",
            "internal revenue collections",
            "collections by state",
        ),
        db_terms=("irs", "collection", "receipt"),
    ),
    ComponentDefinition(
        key="irs_refunds",
        label="IRS refunds",
        path_terms=("irs", "refund"),
        text_terms=("refund", "refunds"),
        db_terms=("irs", "refund"),
    ),
    ComponentDefinition(
        key="oasdi",
        label="SSA OASDI",
        path_terms=("ssa", "oasdi", "social_security"),
        text_terms=(
            "oasdi",
            "old-age",
            "old age",
            "survivors",
            "disability insurance",
            "social security",
        ),
        db_terms=("ssa", "oasdi", "social_security", "benefit"),
    ),
    ComponentDefinition(
        key="ssi",
        label="SSA SSI",
        path_terms=("ssa", "ssi"),
        text_terms=("supplemental security income", "ssi"),
        db_terms=("ssi", "supplemental_security"),
    ),
    ComponentDefinition(
        key="va_gdx",
        label="VA GDX",
        path_terms=("va", "gdx", "veteran"),
        text_terms=(
            "geographic distribution of expenditures",
            "va gdx",
            "veterans affairs",
        ),
        db_terms=("va", "gdx", "veteran"),
    ),
    ComponentDefinition(
        key="assistance",
        label="USAspending assistance",
        path_terms=("usaspending", "assistance"),
        text_terms=("usaspending", "assistance"),
        db_terms=("assistance", "usaspending"),
    ),
    ComponentDefinition(
        key="procurement",
        label="USAspending procurement",
        path_terms=("usaspending", "procurement", "contract"),
        text_terms=("procurement", "contract", "usaspending"),
        db_terms=("procurement", "contract", "award_transaction"),
    ),
    ComponentDefinition(
        key="federal_civilian_wages",
        label="Federal civilian wages / compensation",
        path_terms=("opm", "fedscope", "bea", "omb", "civilian"),
        text_terms=(
            "federal civilian",
            "civilian wages",
            "civilian compensation",
            "fedscope",
        ),
        db_terms=("opm", "fedscope", "bea", "civilian", "compensation", "wage"),
    ),
    ComponentDefinition(
        key="military_wages",
        label="Military wages / compensation",
        path_terms=("bea", "omb", "military"),
        text_terms=(
            "military wages",
            "military compensation",
            "military personnel",
        ),
        db_terms=("bea", "omb", "military", "compensation", "wage"),
    ),
    ComponentDefinition(
        key="original_medicare",
        label="Original Medicare",
        path_terms=("cms", "medicare", "ffs"),
        text_terms=(
            "original medicare",
            "fee-for-service",
            "fee for service",
            "medicare ffs",
        ),
        db_terms=("cms", "medicare", "ffs"),
    ),
    ComponentDefinition(
        key="medicare_advantage",
        label="Medicare Advantage / Part C",
        path_terms=("cms", "medicare", "part_c", "partc", "advantage"),
        text_terms=(
            "medicare advantage",
            "part c",
            "part_c",
        ),
        db_terms=("medicare", "part_c", "partc", "advantage"),
    ),
    ComponentDefinition(
        key="medicare_part_d",
        label="Medicare Part D",
        path_terms=("cms", "medicare", "part_d", "partd"),
        text_terms=("medicare part d", "part d", "part_d"),
        db_terms=("medicare", "part_d", "partd"),
    ),
    ComponentDefinition(
        key="medicaid",
        label="Medicaid federal expenditures",
        path_terms=("cms", "medicaid"),
        text_terms=("medicaid",),
        db_terms=("medicaid",),
    ),
    ComponentDefinition(
        key="chip",
        label="CHIP federal expenditures",
        path_terms=("cms", "chip"),
        text_terms=(
            "children's health insurance",
            "childrens health insurance",
            "chip",
            "cms-21",
        ),
        db_terms=("chip",),
    ),
    ComponentDefinition(
        key="aca_aptc",
        label="ACA APTC",
        path_terms=("aca", "aptc", "marketplace"),
        text_terms=(
            "advance premium tax credit",
            "advanced premium tax credit",
            "aptc",
        ),
        db_terms=("aptc", "aca", "marketplace"),
    ),
    ComponentDefinition(
        key="military_retirement",
        label="Military retired / survivor pay",
        path_terms=("military", "retire", "survivor", "dfas"),
        text_terms=(
            "military retired",
            "military retirement",
            "survivor pay",
            "retired pay",
        ),
        db_terms=("military", "retire", "survivor", "dfas"),
    ),
    ComponentDefinition(
        key="opm_retirement",
        label="OPM civilian retirement",
        path_terms=("opm", "retire", "annuit"),
        text_terms=(
            "civilian retirement",
            "opm retirement",
            "annuitant",
            "annuity",
        ),
        db_terms=("opm", "retire", "annuit"),
    ),
)


# =============================================================================
# Results
# =============================================================================

@dataclass
class YearEvidence:
    file_paths: set[str] = field(default_factory=set)
    text_paths: set[str] = field(default_factory=set)
    db_objects: set[str] = field(default_factory=set)
    db_year_details: list[str] = field(default_factory=list)


@dataclass
class ComponentEvidence:
    component: ComponentDefinition
    years: dict[int, YearEvidence] = field(
        default_factory=lambda: {year: YearEvidence() for year in TARGET_YEARS}
    )
    general_file_paths: set[str] = field(default_factory=set)
    general_db_objects: set[str] = field(default_factory=set)


# =============================================================================
# Utility
# =============================================================================

def normalize(value: str) -> str:
    return value.lower().replace("\\", "/")


def contains_term(value: str, terms: Iterable[str]) -> bool:
    value_n = normalize(value)
    return any(normalize(term) in value_n for term in terms)


def year_tokens(year: int) -> tuple[str, ...]:
    yy = str(year)[-2:]
    return (
        str(year),
        f"fy{year}",
        f"fy_{year}",
        f"fy-{year}",
        f"ffy{year}",
        f"ffy_{year}",
        f"ffy-{year}",
        f"fy{yy}",
        f"fy_{yy}",
        f"fy-{yy}",
    )


def path_mentions_year(path_text: str, year: int) -> bool:
    value = normalize(path_text)

    if any(token in value for token in year_tokens(year)):
        return True

    # Prevent 2018 from matching a larger digit string.
    return bool(re.search(rf"(?<!\d){year}(?!\d)", value))


def safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def should_skip(path: Path) -> bool:
    return any(part.lower() in SKIP_DIR_NAMES for part in path.parts)


def iter_repository_files() -> Iterable[Path]:
    """
    Walk the repository without following skipped environment/cache trees.
    """
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in SKIP_DIR_NAMES
        ]

        base = Path(dirpath)

        for filename in filenames:
            path = base / filename

            if should_skip(path):
                continue

            yield path


def read_small_text(path: Path) -> str | None:
    try:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            return None

        size = path.stat().st_size

        if size > MAX_TEXT_SCAN_BYTES:
            return None

        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, UnicodeError):
        return None


# =============================================================================
# Filesystem profiling
# =============================================================================

def profile_filesystem(
    evidence: dict[str, ComponentEvidence],
) -> dict[str, int]:
    stats = {
        "files_seen": 0,
        "text_files_scanned": 0,
        "large_or_binary_not_opened": 0,
    }

    print("Profiling repository filesystem...", flush=True)

    for path in iter_repository_files():
        stats["files_seen"] += 1

        rel = safe_relative(path)
        rel_n = normalize(rel)

        path_component_matches: list[ComponentDefinition] = []

        for component in COMPONENTS:
            if contains_term(rel_n, component.path_terms):
                path_component_matches.append(component)
                evidence[component.key].general_file_paths.add(rel)

                for year in TARGET_YEARS:
                    if path_mentions_year(rel_n, year):
                        evidence[component.key].years[year].file_paths.add(rel)

        text = read_small_text(path)

        if text is None:
            try:
                if (
                    path.suffix.lower() not in TEXT_SUFFIXES
                    or path.stat().st_size > MAX_TEXT_SCAN_BYTES
                ):
                    stats["large_or_binary_not_opened"] += 1
            except OSError:
                pass
            continue

        stats["text_files_scanned"] += 1

        text_n = normalize(text)

        # Only record text evidence where BOTH:
        #   * component terminology occurs
        #   * target year occurs
        #
        # This reduces false positives from generic year mentions.
        for component in COMPONENTS:
            component_hit = contains_term(
                text_n,
                component.text_terms + component.path_terms,
            )

            if not component_hit:
                continue

            evidence[component.key].general_file_paths.add(rel)

            for year in TARGET_YEARS:
                if re.search(rf"(?<!\d){year}(?!\d)", text_n):
                    evidence[component.key].years[year].text_paths.add(rel)

    return stats


# =============================================================================
# PostgreSQL profiling
# =============================================================================

def connect_read_only():
    if psycopg2 is None:
        return None, "psycopg2 is not installed."

    params = {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "dbname": os.environ.get("PGDATABASE", "wcffbp"),
        "user": os.environ.get("PGUSER", "postgres"),
    }

    password = os.environ.get("PGPASSWORD")
    if password:
        params["password"] = password

    try:
        conn = psycopg2.connect(**params)

        # Explicit read-only transaction.
        conn.set_session(readonly=True, autocommit=False)

        return conn, None

    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def get_database_objects(conn) -> list[dict]:
    """
    Return ordinary tables and views visible to the current user,
    along with their columns.
    """
    query = """
        SELECT
            t.table_schema,
            t.table_name,
            t.table_type,
            c.column_name,
            c.data_type,
            c.ordinal_position
        FROM information_schema.tables AS t
        JOIN information_schema.columns AS c
          ON c.table_schema = t.table_schema
         AND c.table_name = t.table_name
        WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY
            t.table_schema,
            t.table_name,
            c.ordinal_position
    """

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    objects: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)

    for schema_name, table_name, table_type, column_name, data_type, _ in rows:
        objects[(schema_name, table_name, table_type)].append(
            (column_name, data_type)
        )

    result = []

    for (schema_name, table_name, table_type), columns in objects.items():
        result.append(
            {
                "schema": schema_name,
                "name": table_name,
                "type": table_type,
                "columns": columns,
            }
        )

    return result


def candidate_year_columns(columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result = []

    for column_name, data_type in columns:
        column_n = column_name.lower()

        if column_n in YEAR_COLUMN_NAMES:
            result.append((column_name, data_type))
            continue

        if column_n.endswith("_year"):
            result.append((column_name, data_type))

    return result


def candidate_date_columns(columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result = []

    for column_name, data_type in columns:
        column_n = column_name.lower()

        if data_type not in {
            "date",
            "timestamp without time zone",
            "timestamp with time zone",
        }:
            continue

        if (
            column_n in DATE_COLUMN_HINTS
            or column_n.endswith("_date")
            or "date" in column_n
        ):
            result.append((column_name, data_type))

    return result


def query_explicit_years(
    conn,
    schema_name: str,
    object_name: str,
    column_name: str,
) -> tuple[set[int], str | None]:
    """
    Query only the target years from an explicit year-like column.

    We cast to text rather than assuming an integer storage type.
    """
    statement = sql.SQL("""
        SELECT DISTINCT {column}::text
        FROM {schema}.{table}
        WHERE {column} IS NOT NULL
          AND {column}::text IN (%s, %s, %s)
        ORDER BY 1
    """).format(
        column=sql.Identifier(column_name),
        schema=sql.Identifier(schema_name),
        table=sql.Identifier(object_name),
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                statement,
                tuple(str(year) for year in TARGET_YEARS),
            )
            values = {int(row[0]) for row in cur.fetchall()}

        return values, None

    except Exception as exc:
        # A failed SELECT aborts the transaction; restore read-only
        # transaction usability with rollback.
        conn.rollback()
        conn.set_session(readonly=True, autocommit=False)

        return set(), f"{type(exc).__name__}: {exc}"


def query_date_years(
    conn,
    schema_name: str,
    object_name: str,
    column_name: str,
) -> tuple[set[int], str | None]:
    """
    Query target years from a date/timestamp column.

    This is secondary evidence only. A transaction/action/report date
    is not automatically the accounting fiscal year.
    """
    statement = sql.SQL("""
        SELECT DISTINCT EXTRACT(YEAR FROM {column})::integer
        FROM {schema}.{table}
        WHERE {column} >= DATE %s
          AND {column} <  DATE %s
        ORDER BY 1
    """).format(
        column=sql.Identifier(column_name),
        schema=sql.Identifier(schema_name),
        table=sql.Identifier(object_name),
    )

    start_year = min(TARGET_YEARS)
    end_year = max(TARGET_YEARS) + 1

    try:
        with conn.cursor() as cur:
            cur.execute(
                statement,
                (f"{start_year}-01-01", f"{end_year}-01-01"),
            )

            observed = {
                int(row[0])
                for row in cur.fetchall()
                if row[0] is not None
                and int(row[0]) in TARGET_YEARS
            }

        return observed, None

    except Exception as exc:
        conn.rollback()
        conn.set_session(readonly=True, autocommit=False)

        return set(), f"{type(exc).__name__}: {exc}"


def profile_database(
    evidence: dict[str, ComponentEvidence],
) -> dict:
    stats = {
        "connected": False,
        "connection_error": None,
        "objects_seen": 0,
        "candidate_objects": 0,
        "year_queries": 0,
        "date_queries": 0,
        "query_errors": [],
    }

    print("Profiling PostgreSQL in READ ONLY mode...", flush=True)

    conn, error = connect_read_only()

    if conn is None:
        stats["connection_error"] = error
        return stats

    stats["connected"] = True

    try:
        objects = get_database_objects(conn)
        stats["objects_seen"] = len(objects)

        for obj in objects:
            schema_name = obj["schema"]
            object_name = obj["name"]
            object_id = f"{schema_name}.{object_name}"
            object_n = normalize(object_id)

            matching_components = [
                component
                for component in COMPONENTS
                if contains_term(object_n, component.db_terms)
            ]

            if not matching_components:
                continue

            stats["candidate_objects"] += 1

            for component in matching_components:
                evidence[component.key].general_db_objects.add(object_id)

            explicit_year_columns = candidate_year_columns(obj["columns"])
            date_columns = candidate_date_columns(obj["columns"])

            # Prefer explicit year fields.
            for column_name, data_type in explicit_year_columns:
                stats["year_queries"] += 1

                years, query_error = query_explicit_years(
                    conn,
                    schema_name,
                    object_name,
                    column_name,
                )

                if query_error:
                    stats["query_errors"].append(
                        f"{object_id}.{column_name}: {query_error}"
                    )
                    continue

                for year in years:
                    detail = (
                        f"{object_id}.{column_name} "
                        f"[{data_type}] contains {year}"
                    )

                    for component in matching_components:
                        evidence[component.key].years[year].db_objects.add(
                            object_id
                        )
                        evidence[component.key].years[year].db_year_details.append(
                            detail
                        )

            # Date columns are secondary evidence and can be useful where
            # no explicit fiscal-year field exists.
            #
            # Limit to the first three likely date columns per object so a
            # huge transaction table is not repeatedly scanned.
            if not explicit_year_columns:
                for column_name, data_type in date_columns[:3]:
                    stats["date_queries"] += 1

                    years, query_error = query_date_years(
                        conn,
                        schema_name,
                        object_name,
                        column_name,
                    )

                    if query_error:
                        stats["query_errors"].append(
                            f"{object_id}.{column_name}: {query_error}"
                        )
                        continue

                    for year in years:
                        detail = (
                            f"{object_id}.{column_name} "
                            f"[{data_type}] has calendar-date observations "
                            f"in {year}; accounting-year meaning NOT inferred"
                        )

                        for component in matching_components:
                            evidence[component.key].years[year].db_objects.add(
                                object_id
                            )
                            evidence[component.key].years[year].db_year_details.append(
                                detail
                            )

        # No commit. End the read-only transaction explicitly.
        conn.rollback()

    finally:
        conn.close()

    return stats


# =============================================================================
# Classification
# =============================================================================

def classify(
    component_evidence: ComponentEvidence,
    year: int,
) -> str:
    y = component_evidence.years[year]

    file_evidence = bool(y.file_paths or y.text_paths)
    db_evidence = bool(y.db_objects or y.db_year_details)

    if file_evidence and db_evidence:
        return "FILE_AND_DB_EVIDENCE"

    if db_evidence:
        return "DB_YEAR_FOUND"

    if file_evidence:
        return "EVIDENCE_FOUND"

    if (
        component_evidence.general_file_paths
        or component_evidence.general_db_objects
    ):
        return "PRESENT_NEEDS_REVIEW"

    return "NOT_FOUND_BY_PROFILER"


# =============================================================================
# Reporting
# =============================================================================

def print_header() -> None:
    print("=" * 108)
    print("WCFFBP DRAFT-1 EXTENSION-YEAR COMPLETENESS PROFILE")
    print("=" * 108)
    print()
    print(f"Repository root : {REPO_ROOT}")
    print(f"Target years    : {', '.join(str(y) for y in TARGET_YEARS)}")
    print("Mode            : READ ONLY / DISCOVERY ONLY")
    print()
    print("IMPORTANT:")
    print("  Evidence presence does NOT authorize ledger inclusion.")
    print("  Missing/suppressed/partial/unresolved are NOT zero.")
    print("  Calendar year is NOT silently treated as federal fiscal year.")
    print("  NOT_FOUND_BY_PROFILER does NOT prove that a source is absent.")
    print()


def print_matrix(
    evidence: dict[str, ComponentEvidence],
) -> None:
    print()
    print("=" * 108)
    print("COMPONENT COMPLETENESS MATRIX")
    print("=" * 108)
    print()

    label_width = max(len(component.label) for component in COMPONENTS) + 2

    header = (
        f"{'COMPONENT':<{label_width}}"
        + "".join(f"{year:^28}" for year in TARGET_YEARS)
    )
    print(header)
    print("-" * len(header))

    for component in COMPONENTS:
        ce = evidence[component.key]

        row = f"{component.label:<{label_width}}"

        for year in TARGET_YEARS:
            row += f"{classify(ce, year):^28}"

        print(row)


def print_component_detail(
    evidence: dict[str, ComponentEvidence],
) -> None:
    print()
    print("=" * 108)
    print("COMPONENT EVIDENCE DETAIL")
    print("=" * 108)

    for component in COMPONENTS:
        ce = evidence[component.key]

        print()
        print("-" * 108)
        print(component.label)
        print("-" * 108)

        if ce.general_file_paths:
            print(
                f"General filesystem evidence : "
                f"{len(ce.general_file_paths):,} path(s)"
            )
        else:
            print("General filesystem evidence : none located")

        if ce.general_db_objects:
            print(
                f"General database evidence   : "
                f"{len(ce.general_db_objects):,} object(s)"
            )
        else:
            print("General database evidence   : none located")

        for year in TARGET_YEARS:
            y = ce.years[year]
            status = classify(ce, year)

            print()
            print(f"  {year} — {status}")

            combined_paths = sorted(y.file_paths | y.text_paths)

            if combined_paths:
                print("    File/text evidence:")

                for path in combined_paths[:MAX_PATHS_PER_COMPONENT_YEAR]:
                    flags = []

                    if path in y.file_paths:
                        flags.append("PATH")

                    if path in y.text_paths:
                        flags.append("TEXT")

                    print(
                        f"      [{'+'.join(flags)}] {path}"
                    )

                omitted = (
                    len(combined_paths)
                    - MAX_PATHS_PER_COMPONENT_YEAR
                )

                if omitted > 0:
                    print(f"      ... {omitted:,} additional path(s) omitted")
            else:
                print("    File/text evidence: none located")

            if y.db_year_details:
                print("    Database year evidence:")

                for detail in sorted(set(y.db_year_details))[
                    :MAX_DB_OBJECTS_PER_COMPONENT_YEAR
                ]:
                    print(f"      {detail}")

                omitted = (
                    len(set(y.db_year_details))
                    - MAX_DB_OBJECTS_PER_COMPONENT_YEAR
                )

                if omitted > 0:
                    print(
                        f"      ... {omitted:,} additional database "
                        f"detail(s) omitted"
                    )
            elif y.db_objects:
                print("    Database objects:")
                for object_id in sorted(y.db_objects)[
                    :MAX_DB_OBJECTS_PER_COMPONENT_YEAR
                ]:
                    print(f"      {object_id}")
            else:
                print("    Database year evidence: none located")


def print_stats(fs_stats: dict, db_stats: dict) -> None:
    print()
    print("=" * 108)
    print("PROFILER EXECUTION SUMMARY")
    print("=" * 108)
    print()

    print("Filesystem")
    print("-" * 60)
    print(f"Files inventoried                 : {fs_stats['files_seen']:,}")
    print(
        f"Small text-like files scanned     : "
        f"{fs_stats['text_files_scanned']:,}"
    )
    print(
        f"Binary/large files not opened     : "
        f"{fs_stats['large_or_binary_not_opened']:,}"
    )

    print()
    print("PostgreSQL")
    print("-" * 60)

    if not db_stats["connected"]:
        print("Connection                         : NOT AVAILABLE")
        print(
            f"Reason                             : "
            f"{db_stats['connection_error']}"
        )
    else:
        print("Connection                         : PASS")
        print("Transaction mode                   : READ ONLY")
        print(
            f"Tables/views inventoried           : "
            f"{db_stats['objects_seen']:,}"
        )
        print(
            f"Component-candidate objects        : "
            f"{db_stats['candidate_objects']:,}"
        )
        print(
            f"Explicit year-column queries       : "
            f"{db_stats['year_queries']:,}"
        )
        print(
            f"Date-column fallback queries       : "
            f"{db_stats['date_queries']:,}"
        )
        print(
            f"Query errors                       : "
            f"{len(db_stats['query_errors']):,}"
        )

        if db_stats["query_errors"]:
            print()
            print("Database query errors:")
            for error in db_stats["query_errors"][:30]:
                print(f"  {error}")

            if len(db_stats["query_errors"]) > 30:
                print(
                    f"  ... "
                    f"{len(db_stats['query_errors']) - 30:,} "
                    f"additional error(s) omitted"
                )


def print_interpretation() -> None:
    print()
    print("=" * 108)
    print("INTERPRETATION RULES")
    print("=" * 108)
    print()
    print("FILE_AND_DB_EVIDENCE")
    print("  Affirmative target-year evidence was located both in local files")
    print("  and in candidate PostgreSQL objects.")
    print()
    print("DB_YEAR_FOUND")
    print("  PostgreSQL contains affirmative target-year evidence in a")
    print("  component-related object, but corresponding file evidence was")
    print("  not located by this profiler.")
    print()
    print("EVIDENCE_FOUND")
    print("  Local file/path/text evidence for the component and year exists,")
    print("  but affirmative database year evidence was not located.")
    print()
    print("PRESENT_NEEDS_REVIEW")
    print("  The component exists somewhere in the repository/database, but")
    print("  this profiler did not establish affirmative evidence for the")
    print("  target year.")
    print()
    print("NOT_FOUND_BY_PROFILER")
    print("  No affirmative evidence was located under these discovery rules.")
    print("  This is NOT proof that the source or observation does not exist.")
    print()
    print("NONE OF THESE STATUSES MEANS:")
    print("  * ledger-ready")
    print("  * additive")
    print("  * authoritative accounting control")
    print("  * correct geographic incidence")
    print("  * complete annual observation")
    print()
    print("Those determinations require the existing WCFFBP validation,")
    print("reconciliation, and accounting-policy process.")


def write_csv_summary(
    evidence: dict[str, ComponentEvidence],
) -> Path:
    """
    Also create a compact CSV beside the text output workflow.

    This is the ONLY file written by the profiler itself.
    It contains profiler results only and does not alter source data,
    evidence, or PostgreSQL.

    If strict no-file-write behavior is desired, comment out the call
    in main().
    """
    output_path = REPO_ROOT / "draft1_extension_years_matrix.csv"

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow(
            [
                "component_key",
                "component",
                "year",
                "status",
                "file_path_hits",
                "text_hits",
                "db_object_hits",
                "db_year_detail_hits",
            ]
        )

        for component in COMPONENTS:
            ce = evidence[component.key]

            for year in TARGET_YEARS:
                y = ce.years[year]

                writer.writerow(
                    [
                        component.key,
                        component.label,
                        year,
                        classify(ce, year),
                        len(y.file_paths),
                        len(y.text_paths),
                        len(y.db_objects),
                        len(y.db_year_details),
                    ]
                )

    return output_path


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    print_header()

    evidence = {
        component.key: ComponentEvidence(component=component)
        for component in COMPONENTS
    }

    fs_stats = profile_filesystem(evidence)
    db_stats = profile_database(evidence)

    print_matrix(evidence)
    print_component_detail(evidence)
    print_stats(fs_stats, db_stats)
    print_interpretation()

    csv_path = write_csv_summary(evidence)

    print()
    print("=" * 108)
    print("OUTPUT ARTIFACT")
    print("=" * 108)
    print()
    print(f"Compact CSV matrix written to:")
    print(f"  {csv_path}")
    print()
    print("Profiler completed.")
    print("No database writes were performed.")
    print("No source data were modified.")
    print("No accounting classifications were changed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())