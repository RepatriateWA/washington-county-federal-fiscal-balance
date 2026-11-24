"""
WCFFBP DRAFT-1 Extension-Year Completeness Profiler v0.2

Purpose
-------
Read-only discovery for FFY 2018, FFY 2019, and FFY 2025.

This profiler is intentionally conservative. It asks:

    1. Is there component-specific source/evidence in the repository?
    2. Is there a component-related PostgreSQL object?
    3. Does that object contain an affirmative target-year observation?
    4. Can an actual dollar value be extracted without guessing?
    5. Is there evidence of validation/accounting-policy work?

It DOES NOT:
    * authorize ledger inclusion
    * classify observations as additive
    * equate calendar year with federal fiscal year
    * treat missing/suppressed/partial observations as zero
    * download data
    * modify the database
    * modify source evidence

The generated report and CSV are discovery artifacts only.
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

import psycopg2
from psycopg2 import sql


# ============================================================================
# CONFIGURATION
# ============================================================================

REPO_ROOT = Path.cwd()

TARGET_YEARS = (2018, 2019, 2025)

REPORT_PATH = REPO_ROOT / "draft1_extension_years_profile_v0_2.txt"
CSV_PATH = REPO_ROOT / "draft1_extension_years_matrix_v0_2.csv"

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}

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
}

MAX_TEXT_BYTES = 8 * 1024 * 1024

YEAR_COLUMN_NAMES = {
    "year",
    "report_year",
    "fiscal_year",
    "fiscalyear",
    "fy",
    "ffy",
    "calendar_year",
    "cy",
    "tax_year",
    "taxyear",
    "benefit_year",
    "payment_year",
}

VALUE_HINTS = (
    "amount",
    "dollar",
    "payment",
    "expenditure",
    "obligation",
    "collection",
    "receipt",
    "refund",
    "benefit",
    "outlay",
    "spending",
    "total",
    "value",
    "wage",
    "compensation",
    "cost",
)

NUMERIC_TYPES = {
    "smallint",
    "integer",
    "bigint",
    "decimal",
    "numeric",
    "real",
    "double precision",
    "money",
}


# ============================================================================
# COMPONENT DEFINITIONS
# ============================================================================

@dataclass(frozen=True)
class ComponentSpec:
    name: str
    object_terms: tuple[str, ...]
    preferred_object_terms: tuple[str, ...]
    path_terms: tuple[str, ...]
    evidence_terms: tuple[str, ...]
    policy_terms: tuple[str, ...] = ()


COMPONENTS = (
    ComponentSpec(
        name="IRS gross collections",
        object_terms=("irs", "collection", "receipt", "databook"),
        preferred_object_terms=("gross", "collection"),
        path_terms=("irs",),
        evidence_terms=("gross collections", "gross_collections"),
    ),
    ComponentSpec(
        name="IRS refunds",
        object_terms=("irs", "refund"),
        preferred_object_terms=("refund",),
        path_terms=("irs", "refund"),
        evidence_terms=("refund",),
    ),
    ComponentSpec(
        name="SSA OASDI",
        object_terms=("ssa", "oasdi", "social_security"),
        preferred_object_terms=("oasdi", "benefit"),
        path_terms=("ssa",),
        evidence_terms=("oasdi",),
        policy_terms=("etl-135", "96.001", "96.002", "96.004"),
    ),
    ComponentSpec(
        name="SSA SSI",
        object_terms=("ssa", "ssi", "supplemental_security"),
        preferred_object_terms=("ssi",),
        path_terms=("ssa", "ssi"),
        evidence_terms=("ssi", "supplemental security income"),
        policy_terms=("etl-176",),
    ),
    ComponentSpec(
        name="VA GDX",
        object_terms=("va", "gdx", "veteran"),
        preferred_object_terms=("gdx",),
        path_terms=("va", "gdx"),
        evidence_terms=("gdx", "geographic distribution"),
        policy_terms=("etl-149", "etl-179"),
    ),
    ComponentSpec(
        name="USAspending assistance",
        object_terms=("assistance", "usaspending"),
        preferred_object_terms=("assistance",),
        path_terms=("usaspending", "assistance"),
        evidence_terms=("assistance",),
    ),
    ComponentSpec(
        name="USAspending procurement",
        object_terms=("procurement", "contract", "usaspending"),
        preferred_object_terms=("procurement", "contract"),
        path_terms=("usaspending",),
        evidence_terms=("procurement", "contract"),
    ),
    ComponentSpec(
        name="Federal civilian wages / compensation",
        object_terms=("bea", "civilian", "wage", "compensation"),
        preferred_object_terms=("federal", "civilian"),
        path_terms=("bea",),
        evidence_terms=("federal civilian",),
    ),
    ComponentSpec(
        name="Military wages / compensation",
        object_terms=("bea", "military", "wage", "compensation"),
        preferred_object_terms=("military",),
        path_terms=("bea",),
        evidence_terms=("military",),
    ),
    ComponentSpec(
        name="Original Medicare",
        object_terms=("medicare", "cms", "original"),
        preferred_object_terms=("original", "medicare"),
        path_terms=("cms", "medicare"),
        evidence_terms=("original medicare",),
    ),
    ComponentSpec(
        name="Medicare Advantage / Part C",
        object_terms=("medicare", "advantage", "partc", "part_c"),
        preferred_object_terms=("advantage", "partc", "part_c"),
        path_terms=("cms", "medicare_advantage"),
        evidence_terms=("medicare advantage", "part c", "partc"),
    ),
    ComponentSpec(
        name="Medicare Part D",
        object_terms=("medicare", "partd", "part_d"),
        preferred_object_terms=("partd", "part_d"),
        path_terms=("cms", "medicare_partd"),
        evidence_terms=("part d", "partd"),
    ),
    ComponentSpec(
        name="Medicaid federal expenditures",
        object_terms=("medicaid", "mbes", "cms"),
        preferred_object_terms=("medicaid", "mbes"),
        path_terms=("cms", "medicaid"),
        evidence_terms=("medicaid", "total net expenditures"),
    ),
    ComponentSpec(
        name="CHIP federal expenditures",
        object_terms=("chip", "mchip", "cms"),
        preferred_object_terms=("chip", "mchip"),
        path_terms=("chip",),
        evidence_terms=("chip", "mchip"),
        policy_terms=("etl-175",),
    ),
    ComponentSpec(
        name="ACA APTC",
        object_terms=("aptc", "aca", "premium_tax"),
        preferred_object_terms=("aptc",),
        path_terms=("aptc", "aca"),
        evidence_terms=("aptc", "advance premium tax credit"),
    ),
    ComponentSpec(
        name="Military retired / survivor pay",
        object_terms=("military", "retired", "retirement", "survivor"),
        preferred_object_terms=("retired", "survivor"),
        path_terms=("military", "retir"),
        evidence_terms=("retired", "survivor"),
    ),
    ComponentSpec(
        name="OPM civilian retirement",
        object_terms=("opm", "civilian", "retirement"),
        preferred_object_terms=("opm", "retirement"),
        path_terms=("opm",),
        evidence_terms=("retirement",),
    ),
)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class DBObject:
    schema: str
    name: str
    kind: str
    columns: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def searchable(self) -> str:
        return f"{self.schema} {self.name}".lower()


@dataclass
class YearFinding:
    component: str
    year: int
    db_objects: list[str] = field(default_factory=list)
    db_rows: list[str] = field(default_factory=list)
    evidence_files: list[str] = field(default_factory=list)
    policy_files: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def status(self) -> str:
        if self.db_rows and self.evidence_files:
            return "DB_YEAR_AND_SOURCE_EVIDENCE"
        if self.db_rows:
            return "DB_YEAR_FOUND"
        if self.evidence_files:
            return "SOURCE_EVIDENCE_FOUND"
        if self.db_objects:
            return "OBJECT_PRESENT_NO_YEAR_PROOF"
        return "NOT_ESTABLISHED"


# ============================================================================
# HELPERS
# ============================================================================

def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def path_is_skipped(path: Path) -> bool:
    return any(part.lower() in SKIP_DIRS for part in path.parts)


def iter_repo_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path_is_skipped(path):
            continue
        if path in {REPORT_PATH, CSV_PATH}:
            continue
        yield path


def safe_read_text(path: Path) -> Optional[str]:
    try:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            return None
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def term_in_path(path: Path, term: str) -> bool:
    return norm(term) in norm(relative(path))


def any_term(text: str, terms: Iterable[str]) -> bool:
    text_n = norm(text)
    return any(norm(term) in text_n for term in terms)


def format_number(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


# ============================================================================
# FILESYSTEM EVIDENCE
# ============================================================================

def build_file_inventory() -> tuple[list[Path], dict[Path, Optional[str]]]:
    files = list(iter_repo_files())
    text_cache: dict[Path, Optional[str]] = {}

    for path in files:
        text_cache[path] = safe_read_text(path)

    return files, text_cache


def component_file_candidates(
    spec: ComponentSpec,
    files: list[Path],
    text_cache: dict[Path, Optional[str]],
    year: int,
) -> tuple[list[str], list[str]]:
    """
    Strict evidence search.

    A source/evidence file must satisfy BOTH:
      * component-specific path or component-specific text
      * affirmative target-year evidence

    Generic files mentioning only the year are not accepted.
    """
    source_hits: list[str] = []
    policy_hits: list[str] = []

    year_patterns = (
        str(year),
        f"fy{year}",
        f"ffy{year}",
        f"fy {year}",
        f"ffy {year}",
    )

    for path in files:
        rel = relative(path)
        rel_l = rel.lower()
        text = text_cache.get(path)
        text_l = text.lower() if text else ""

        path_component = any(term_in_path(path, t) for t in spec.path_terms)
        text_component = bool(text) and any_term(text_l, spec.evidence_terms)

        year_in_path = any(p.lower() in rel_l for p in year_patterns)
        year_in_text = bool(text) and any(p.lower() in text_l for p in year_patterns)

        if (path_component or text_component) and (year_in_path or year_in_text):
            source_hits.append(rel)

        if spec.policy_terms and text:
            if any(term.lower() in text_l for term in spec.policy_terms):
                policy_hits.append(rel)

    # Prefer shorter, component-specific paths and suppress duplicate names.
    source_hits = sorted(
        set(source_hits),
        key=lambda p: (
            0 if any(norm(t) in norm(p) for t in spec.path_terms) else 1,
            len(p),
            p.lower(),
        ),
    )

    policy_hits = sorted(set(policy_hits), key=lambda p: (len(p), p.lower()))

    return source_hits[:25], policy_hits[:15]


# ============================================================================
# POSTGRESQL DISCOVERY
# ============================================================================

def connect_db():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "wcffbp"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD"),
        connect_timeout=10,
    )


def load_db_objects(conn) -> list[DBObject]:
    objects: dict[tuple[str, str], DBObject] = {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                n.nspname AS schema_name,
                c.relname AS object_name,
                CASE c.relkind
                    WHEN 'r' THEN 'TABLE'
                    WHEN 'v' THEN 'VIEW'
                    WHEN 'm' THEN 'MATERIALIZED VIEW'
                    WHEN 'p' THEN 'PARTITIONED TABLE'
                    ELSE c.relkind::text
                END AS object_kind
            FROM pg_class c
            JOIN pg_namespace n
              ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'v', 'm', 'p')
              AND n.nspname NOT IN (
                    'pg_catalog',
                    'information_schema',
                    'pg_toast'
              )
              AND n.nspname NOT LIKE 'pg_temp_%'
              AND n.nspname NOT LIKE 'pg_toast_temp_%'
            ORDER BY n.nspname, c.relname
            """
        )

        for schema_name, object_name, object_kind in cur.fetchall():
            objects[(schema_name, object_name)] = DBObject(
                schema=schema_name,
                name=object_name,
                kind=object_kind,
            )

        cur.execute(
            """
            SELECT
                table_schema,
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name, ordinal_position
            """
        )

        for schema_name, table_name, column_name, data_type in cur.fetchall():
            obj = objects.get((schema_name, table_name))
            if obj is not None:
                obj.columns[column_name] = (column_name, data_type)

    return list(objects.values())


def object_score(spec: ComponentSpec, obj: DBObject) -> int:
    searchable = obj.searchable
    column_text = " ".join(obj.columns).lower()

    score = 0

    for term in spec.object_terms:
        t = norm(term)
        if t in norm(searchable):
            score += 3
        if t in norm(column_text):
            score += 1

    for term in spec.preferred_object_terms:
        t = norm(term)
        if t in norm(searchable):
            score += 6
        if t in norm(column_text):
            score += 2

    return score


def candidate_objects(spec: ComponentSpec, objects: list[DBObject]) -> list[DBObject]:
    scored = [
        (object_score(spec, obj), obj)
        for obj in objects
    ]

    scored = [
        (score, obj)
        for score, obj in scored
        if score >= 3
    ]

    scored.sort(key=lambda item: (-item[0], item[1].qualified.lower()))

    return [obj for _, obj in scored[:30]]


def identify_year_columns(obj: DBObject) -> list[str]:
    preferred = []

    for col_name, (_, data_type) in obj.columns.items():
        if norm(col_name) in YEAR_COLUMN_NAMES:
            preferred.append(col_name)

    return preferred


def identify_value_columns(obj: DBObject) -> list[str]:
    candidates = []

    for col_name, (_, data_type) in obj.columns.items():
        if data_type.lower() not in NUMERIC_TYPES:
            continue

        col_n = norm(col_name)

        if any(hint in col_n for hint in VALUE_HINTS):
            candidates.append(col_name)

    return candidates[:12]


def year_predicate(column_name: str):
    """
    Compare year-like columns robustly by converting to text.

    This avoids assuming whether a year column is integer, numeric,
    varchar, etc. It deliberately does not reinterpret dates as fiscal
    years.
    """
    return sql.SQL("CAST({col} AS text) = %s").format(
        col=sql.Identifier(column_name)
    )


def query_object_year(
    conn,
    obj: DBObject,
    year: int,
) -> tuple[list[str], list[str], list[str]]:
    """
    Returns:
        row evidence strings
        value evidence strings
        notes
    """
    row_evidence: list[str] = []
    value_evidence: list[str] = []
    notes: list[str] = []

    year_cols = identify_year_columns(obj)

    if not year_cols:
        notes.append(f"{obj.qualified}: no explicit year column")
        return row_evidence, value_evidence, notes

    value_cols = identify_value_columns(obj)

    for year_col in year_cols[:3]:
        try:
            with conn.cursor() as cur:
                q_count = sql.SQL(
                    """
                    SELECT COUNT(*)
                    FROM {schema}.{table}
                    WHERE {predicate}
                    """
                ).format(
                    schema=sql.Identifier(obj.schema),
                    table=sql.Identifier(obj.name),
                    predicate=year_predicate(year_col),
                )

                cur.execute(q_count, (str(year),))
                count = cur.fetchone()[0]

                if not count:
                    continue

                row_evidence.append(
                    f"{obj.qualified}.{year_col}: {count:,} row(s)"
                )

                # Extract conservative aggregates from plausible dollar columns.
                for value_col in value_cols:
                    q_value = sql.SQL(
                        """
                        SELECT
                            COUNT({value_col}),
                            SUM({value_col})
                        FROM {schema}.{table}
                        WHERE {predicate}
                        """
                    ).format(
                        value_col=sql.Identifier(value_col),
                        schema=sql.Identifier(obj.schema),
                        table=sql.Identifier(obj.name),
                        predicate=year_predicate(year_col),
                    )

                    try:
                        cur.execute(q_value, (str(year),))
                        nonnull_count, total = cur.fetchone()

                        if nonnull_count and total is not None:
                            value_evidence.append(
                                f"{obj.qualified}.{value_col}: "
                                f"SUM={format_number(total)} "
                                f"(nonnull rows={nonnull_count:,})"
                            )
                    except Exception as exc:
                        conn.rollback()
                        conn.set_session(readonly=True, autocommit=False)
                        notes.append(
                            f"{obj.qualified}.{value_col}: "
                            f"aggregate skipped ({type(exc).__name__})"
                        )

        except Exception as exc:
            conn.rollback()
            conn.set_session(readonly=True, autocommit=False)
            notes.append(
                f"{obj.qualified}.{year_col}: query failed "
                f"({type(exc).__name__}: {exc})"
            )

    return row_evidence, value_evidence, notes


# ============================================================================
# PROFILING
# ============================================================================

def profile():
    files, text_cache = build_file_inventory()

    conn = connect_db()
    conn.set_session(readonly=True, autocommit=False)

    try:
        objects = load_db_objects(conn)

        findings: list[YearFinding] = []

        component_object_map: dict[str, list[DBObject]] = {}

        for spec in COMPONENTS:
            component_object_map[spec.name] = candidate_objects(spec, objects)

        for spec in COMPONENTS:
            db_candidates = component_object_map[spec.name]

            for year in TARGET_YEARS:
                finding = YearFinding(
                    component=spec.name,
                    year=year,
                )

                source_hits, policy_hits = component_file_candidates(
                    spec,
                    files,
                    text_cache,
                    year,
                )

                finding.evidence_files.extend(source_hits)
                finding.policy_files.extend(policy_hits)

                for obj in db_candidates:
                    finding.db_objects.append(
                        f"{obj.qualified} [{obj.kind}]"
                    )

                    rows, values, notes = query_object_year(
                        conn,
                        obj,
                        year,
                    )

                    finding.db_rows.extend(rows)
                    finding.values.extend(values)
                    finding.notes.extend(notes)

                # Deduplicate while preserving deterministic order.
                finding.db_objects = list(dict.fromkeys(finding.db_objects))
                finding.db_rows = list(dict.fromkeys(finding.db_rows))
                finding.values = list(dict.fromkeys(finding.values))
                finding.evidence_files = list(
                    dict.fromkeys(finding.evidence_files)
                )
                finding.policy_files = list(
                    dict.fromkeys(finding.policy_files)
                )
                finding.notes = list(dict.fromkeys(finding.notes))

                findings.append(finding)

        write_report(
            findings=findings,
            files=files,
            text_cache=text_cache,
            objects=objects,
            component_object_map=component_object_map,
        )

        write_csv(findings)

    finally:
        conn.rollback()
        conn.close()


# ============================================================================
# OUTPUT
# ============================================================================

def write_report(
    *,
    findings: list[YearFinding],
    files: list[Path],
    text_cache: dict[Path, Optional[str]],
    objects: list[DBObject],
    component_object_map: dict[str, list[DBObject]],
):
    by_key = {
        (f.component, f.year): f
        for f in findings
    }

    lines: list[str] = []

    def out(text: str = ""):
        lines.append(text)

    rule = "=" * 118
    subrule = "-" * 118

    out(rule)
    out("WCFFBP DRAFT-1 EXTENSION-YEAR COMPLETENESS PROFILE v0.2")
    out(rule)
    out()
    out(f"Repository root : {REPO_ROOT}")
    out(f"Target years    : {', '.join(map(str, TARGET_YEARS))}")
    out("Mode            : READ ONLY / TARGETED DISCOVERY")
    out()
    out("IMPORTANT:")
    out("  Evidence presence does NOT authorize ledger inclusion.")
    out("  Database presence does NOT establish accounting authority.")
    out("  SUM values below are discovery diagnostics, NOT automatically ledger controls.")
    out("  Missing/suppressed/partial/unresolved are NOT zero.")
    out("  Calendar year is NOT silently treated as federal fiscal year.")
    out()

    # ------------------------------------------------------------------
    # Matrix
    # ------------------------------------------------------------------

    out(rule)
    out("TARGETED COMPONENT MATRIX")
    out(rule)
    out()

    header = (
        f"{'COMPONENT':45}"
        f"{'2018':26}"
        f"{'2019':26}"
        f"{'2025':26}"
    )
    out(header)
    out("-" * len(header))

    for spec in COMPONENTS:
        row = f"{spec.name[:44]:45}"

        for year in TARGET_YEARS:
            status = by_key[(spec.name, year)].status()
            row += f"{status[:25]:26}"

        out(row)

    out()

    # ------------------------------------------------------------------
    # DB inventory
    # ------------------------------------------------------------------

    out(rule)
    out("POSTGRESQL INVENTORY")
    out(rule)
    out()
    out(f"Database objects inventoried: {len(objects):,}")
    out()

    schema_counts = defaultdict(int)
    for obj in objects:
        schema_counts[obj.schema] += 1

    out("Objects by schema:")
    for schema_name in sorted(schema_counts):
        out(f"  {schema_name:35} {schema_counts[schema_name]:,}")
    out()

    # ------------------------------------------------------------------
    # Component detail
    # ------------------------------------------------------------------

    out(rule)
    out("COMPONENT DETAIL")
    out(rule)

    for spec in COMPONENTS:
        out()
        out(subrule)
        out(spec.name)
        out(subrule)

        candidates = component_object_map[spec.name]

        out()
        out("Candidate PostgreSQL objects:")
        if candidates:
            for obj in candidates:
                year_cols = identify_year_columns(obj)
                value_cols = identify_value_columns(obj)

                out(
                    f"  {obj.qualified} [{obj.kind}]"
                    f" | year={','.join(year_cols) if year_cols else '-'}"
                    f" | values={','.join(value_cols) if value_cols else '-'}"
                )
        else:
            out("  none identified")

        for year in TARGET_YEARS:
            finding = by_key[(spec.name, year)]

            out()
            out(f"  {year} -- {finding.status()}")

            out("    Affirmative database year evidence:")
            if finding.db_rows:
                for item in finding.db_rows[:30]:
                    out(f"      {item}")
            else:
                out("      none established")

            out("    Candidate numeric aggregates:")
            if finding.values:
                for item in finding.values[:30]:
                    out(f"      {item}")
            else:
                out("      none")

            out("    Component-specific source/evidence files:")
            if finding.evidence_files:
                for item in finding.evidence_files[:15]:
                    out(f"      {item}")
                if len(finding.evidence_files) > 15:
                    out(
                        f"      ... "
                        f"{len(finding.evidence_files) - 15} additional hit(s)"
                    )
            else:
                out("      none established")

            out("    Accounting-policy / reconciliation evidence:")
            if finding.policy_files:
                for item in finding.policy_files[:10]:
                    out(f"      {item}")
                if len(finding.policy_files) > 10:
                    out(
                        f"      ... "
                        f"{len(finding.policy_files) - 10} additional hit(s)"
                    )
            else:
                out("      none located by targeted policy search")

            if finding.notes:
                relevant_notes = [
                    n for n in finding.notes
                    if "query failed" in n
                    or "aggregate skipped" in n
                ]

                if relevant_notes:
                    out("    Query notes:")
                    for item in relevant_notes[:10]:
                        out(f"      {item}")

    # ------------------------------------------------------------------
    # Execution summary
    # ------------------------------------------------------------------

    out()
    out(rule)
    out("EXECUTION SUMMARY")
    out(rule)
    out()

    scanned = sum(1 for value in text_cache.values() if value is not None)
    unscanned = len(files) - scanned

    out(f"Repository files inventoried      : {len(files):,}")
    out(f"Text-like files examined          : {scanned:,}")
    out(f"Binary/large files not text-read  : {unscanned:,}")
    out(f"PostgreSQL objects inventoried    : {len(objects):,}")
    out("PostgreSQL connection             : SUCCESS")
    out("Database transaction mode         : READ ONLY")
    out()

    out("STATUS DEFINITIONS")
    out("-" * 60)
    out()
    out("DB_YEAR_AND_SOURCE_EVIDENCE")
    out("  Target-year rows exist in a component-related PostgreSQL object")
    out("  and component-specific source/evidence was also located.")
    out()
    out("DB_YEAR_FOUND")
    out("  Target-year rows exist in a component-related PostgreSQL object,")
    out("  but the targeted filesystem search did not establish source evidence.")
    out()
    out("SOURCE_EVIDENCE_FOUND")
    out("  Component-specific source/evidence exists for the target year,")
    out("  but no target-year PostgreSQL observation was established.")
    out()
    out("OBJECT_PRESENT_NO_YEAR_PROOF")
    out("  Component-related PostgreSQL objects exist, but no affirmative")
    out("  target-year observation was established.")
    out()
    out("NOT_ESTABLISHED")
    out("  This profiler established neither target-year database evidence")
    out("  nor component-specific target-year source evidence.")
    out()
    out("NONE OF THESE STATUSES MEANS:")
    out("  * ledger-ready")
    out("  * additive")
    out("  * authoritative accounting control")
    out("  * correct geographic incidence")
    out("  * complete annual observation")
    out()
    out("Those determinations remain subject to WCFFBP validation,")
    out("reconciliation, timing, and accounting-policy rules.")
    out()
    out(rule)
    out("Profiler completed.")
    out("No database writes were performed.")
    out("No source data were modified.")
    out("No accounting classifications were changed.")
    out(rule)

    REPORT_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def write_csv(findings: list[YearFinding]):
    with CSV_PATH.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.writer(handle)

        writer.writerow(
            [
                "component",
                "year",
                "status",
                "database_year_evidence_count",
                "numeric_aggregate_count",
                "source_evidence_count",
                "policy_evidence_count",
            ]
        )

        for finding in findings:
            writer.writerow(
                [
                    finding.component,
                    finding.year,
                    finding.status(),
                    len(finding.db_rows),
                    len(finding.values),
                    len(finding.evidence_files),
                    len(finding.policy_files),
                ]
            )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print(
        "WCFFBP DRAFT-1 extension-year profiler v0.2\n"
        "READ ONLY / TARGETED DISCOVERY\n"
    )

    try:
        profile()
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        raise

    print("Completed successfully.")
    print(f"Report: {REPORT_PATH}")
    print(f"Matrix: {CSV_PATH}")