#!/usr/bin/env python3
"""
profile_usaspending_assistance_93774_v0_1.py

Read-only empirical profiler for USAspending Assistance Listing 93.774
(Medicare Supplementary Medical Insurance) in the WCFFBP PostgreSQL database.

Purpose:
  Measure first. Classify later.

This script:
  * reads the existing normalized assistance schema;
  * inventories every normalized AL 93.774 transaction;
  * profiles fiscal-year obligations/outlays;
  * profiles recipient, geography, agency, type, and description structure;
  * preserves NULL/unlinked dimensional records explicitly;
  * performs accounting/control checks;
  * makes NO additive/overlap accounting decision;
  * performs NO database writes and NO ledger inclusion.

Expected project architecture:
  assistance.assistance_listing
  assistance.award_transaction
  shared recipient / agency / place dimensions linked by IDs

The script introspects PostgreSQL metadata so it can use the project's actual
dimension table/column names rather than silently assuming them.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# When a script is launched as:
#   python scripts\\<script>.py
# Python places scripts\\ (not the repository root) first on sys.path.
# Add the repository root explicitly so the project's etl package resolves
# consistently from PowerShell without requiring PYTHONPATH manipulation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from etl.common.db import get_connection

TARGET_CFDA = "93.774"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = %s AND table_name = %s
        )
        """,
        (schema, table),
    )
    return bool(cur.fetchone()[0])


def columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def find_table_with_column(cur, column: str, preferred=()) -> tuple[str, str] | None:
    cur.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name = %s
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
        """,
        (column,),
    )
    found = [(r[0], r[1]) for r in cur.fetchall()]
    for item in preferred:
        if item in found:
            return item
    return found[0] if found else None


def choose_col(cols: list[str], candidates: list[str]) -> str | None:
    s = set(cols)
    return next((x for x in candidates if x in s), None)


def dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def clean(v) -> str:
    return "" if v is None else str(v).strip()


def normalize_text(v) -> str:
    return re.sub(r"\s+", " ", clean(v)).strip()


def build_dimension(cur, fk: str, candidates: list[tuple[str, str]], fields: dict[str, list[str]]):
    for schema, table in candidates:
        if not table_exists(cur, schema, table):
            continue
        cols = columns(cur, schema, table)
        pk = choose_col(cols, [fk, fk.replace("_id", "") + "_id"])
        if not pk:
            continue
        selected = {"schema": schema, "table": table, "pk": pk, "cols": cols}
        for alias, opts in fields.items():
            selected[alias] = choose_col(cols, opts)
        return selected
    auto = find_table_with_column(cur, fk)
    if auto:
        schema, table = auto
        cols = columns(cur, schema, table)
        selected = {"schema": schema, "table": table, "pk": fk, "cols": cols}
        for alias, opts in fields.items():
            selected[alias] = choose_col(cols, opts)
        return selected
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/raw/usaspending/assistance/validation/"
            "medicare_93774_overlap_profile_v0_1"
        ),
    )
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    warnings: list[str] = []

    conn = get_connection()
    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()

        # Core schema validation.
        for t in ("assistance_listing", "award_transaction"):
            if not table_exists(cur, "assistance", t):
                errors.append(f"Missing required table assistance.{t}")

        if errors:
            raise RuntimeError("; ".join(errors))

        listing_cols = columns(cur, "assistance", "assistance_listing")
        tx_cols = columns(cur, "assistance", "award_transaction")

        required_listing = {"assistance_listing_id", "cfda_number"}
        required_tx = {
            "assistance_transaction_id",
            "load_batch_id",
            "source_row_number",
            "assistance_listing_id",
            "action_date_fiscal_year",
            "federal_action_obligation",
        }
        for c in sorted(required_listing - set(listing_cols)):
            errors.append(f"Missing assistance.assistance_listing.{c}")
        for c in sorted(required_tx - set(tx_cols)):
            errors.append(f"Missing assistance.award_transaction.{c}")
        if errors:
            raise RuntimeError("; ".join(errors))

        # Actual optional columns from the established normalized transaction table.
        tx = {
            "transaction_key": choose_col(
                tx_cols, ["assistance_transaction_unique_key"]
            ),
            "award_id": choose_col(tx_cols, ["assistance_award_id"]),
            "action_date": choose_col(tx_cols, ["action_date"]),
            "total_obligated": choose_col(tx_cols, ["total_obligated_amount"]),
            "total_outlay": choose_col(
                tx_cols, ["total_outlayed_amount_for_overall_award"]
            ),
            "recipient_id": choose_col(tx_cols, ["recipient_id"]),
            "pop_id": choose_col(tx_cols, ["place_of_performance_id"]),
            "awarding_agency_id": choose_col(tx_cols, ["awarding_agency_id"]),
            "funding_agency_id": choose_col(tx_cols, ["funding_agency_id"]),
            "assistance_type_id": choose_col(tx_cols, ["assistance_type_id"]),
            "description": choose_col(tx_cols, ["transaction_description"]),
            "action_type": choose_col(tx_cols, ["action_type_code"]),
            "record_type": choose_col(tx_cols, ["record_type_code"]),
            "correction_delete": choose_col(
                tx_cols, ["correction_delete_indicator_code"]
            ),
            "permalink": choose_col(tx_cols, ["usaspending_permalink"]),
        }

        # Discover dimensions from the actual database. Preferred names reflect
        # WCFFBP architecture but are not assumed blindly.
        recipient = None
        if tx["recipient_id"]:
            recipient = build_dimension(
                cur,
                "recipient_id",
                [
                    ("procurement", "recipient"),
                    ("assistance", "recipient"),
                    ("public", "recipient"),
                ],
                {
                    "name": [
                        "recipient_name",
                        "recipient_name_raw",
                        "recipient_legal_entity_name",
                        "name",
                    ],
                    "uei": [
                        "recipient_uei",
                        "recipient_uei_raw",
                        "recipient_unique_entity_id",
                    ],
                    "duns": ["recipient_duns", "recipient_duns_raw"],
                },
            )

        agency = None
        if tx["awarding_agency_id"] or tx["funding_agency_id"]:
            agency = build_dimension(
                cur,
                "agency_id",
                [
                    ("procurement", "agency"),
                    ("assistance", "agency"),
                    ("public", "agency"),
                ],
                {
                    "name": [
                        "agency_name",
                        "agency_name_raw",
                        "subtier_agency_name",
                        "name",
                    ],
                    "toptier": [
                        "toptier_agency_name",
                        "toptier_name",
                        "agency_toptier_name",
                    ],
                },
            )

        place = None
        if tx["pop_id"]:
            place = build_dimension(
                cur,
                "place_id",
                [
                    ("procurement", "place"),
                    ("assistance", "place"),
                    ("public", "place"),
                ],
                {
                    "state": [
                        "state_code",
                        "state_abbreviation",
                        "state",
                        "place_of_performance_state_code",
                    ],
                    "county": [
                        "county_name",
                        "county",
                        "place_of_performance_county_name",
                    ],
                    "county_fips": [
                        "county_fips",
                        "county_fips_code",
                        "place_of_performance_county_fips",
                    ],
                    "country": [
                        "country_code",
                        "country",
                        "place_of_performance_country_code",
                    ],
                },
            )

        atype = None
        if tx["assistance_type_id"]:
            atype = build_dimension(
                cur,
                "assistance_type_id",
                [("assistance", "assistance_type")],
                {
                    "code": ["assistance_type_code", "code"],
                    "description": [
                        "assistance_type_description",
                        "description",
                        "assistance_type_name",
                    ],
                },
            )

        # Inventory listing rows first.
        cur.execute(
            """
            SELECT assistance_listing_id, cfda_number,
                   COALESCE(cfda_title, '')
            FROM assistance.assistance_listing
            WHERE cfda_number = %s
            ORDER BY assistance_listing_id
            """,
            (TARGET_CFDA,),
        )
        listing_rows = cur.fetchall()
        if not listing_rows:
            errors.append(f"No normalized assistance listing row found for {TARGET_CFDA}")

        # Construct one read-only query using only columns/dimensions that actually exist.
        select = [
            "t.assistance_transaction_id",
            "t.load_batch_id",
            "t.source_row_number",
            "t.action_date_fiscal_year",
            "t.federal_action_obligation",
            "l.cfda_number",
            "COALESCE(l.cfda_title, '')",
        ]
        names = [
            "assistance_transaction_id",
            "load_batch_id",
            "source_row_number",
            "fiscal_year",
            "federal_action_obligation",
            "cfda_number",
            "cfda_title",
        ]

        def add_tx(alias, col):
            if col:
                select.append(f"t.{qident(col)}")
                names.append(alias)
            else:
                select.append("NULL")
                names.append(alias)

        for alias in (
            "transaction_key", "award_id", "action_date", "total_obligated",
            "total_outlay", "recipient_id", "pop_id", "awarding_agency_id",
            "funding_agency_id", "assistance_type_id", "description",
            "action_type", "record_type", "correction_delete", "permalink",
        ):
            add_tx(alias, tx[alias])

        joins = []

        def add_dim(prefix, dim, fkcol, fields):
            if dim and fkcol:
                alias = prefix
                joins.append(
                    f"LEFT JOIN {qident(dim['schema'])}.{qident(dim['table'])} {alias} "
                    f"ON {alias}.{qident(dim['pk'])} = t.{qident(fkcol)}"
                )
                for outname, field in fields:
                    if dim.get(field):
                        select.append(f"{alias}.{qident(dim[field])}")
                    else:
                        select.append("NULL")
                    names.append(outname)
            else:
                for outname, _ in fields:
                    select.append("NULL")
                    names.append(outname)

        add_dim(
            "r", recipient, tx["recipient_id"],
            [("recipient_name", "name"), ("recipient_uei", "uei"), ("recipient_duns", "duns")],
        )
        add_dim(
            "p", place, tx["pop_id"],
            [
                ("pop_state", "state"),
                ("pop_county", "county"),
                ("pop_county_fips", "county_fips"),
                ("pop_country", "country"),
            ],
        )
        add_dim(
            "aa", agency, tx["awarding_agency_id"],
            [("awarding_agency_name", "name"), ("awarding_toptier_name", "toptier")],
        )
        add_dim(
            "fa", agency, tx["funding_agency_id"],
            [("funding_agency_name", "name"), ("funding_toptier_name", "toptier")],
        )
        add_dim(
            "aty", atype, tx["assistance_type_id"],
            [("assistance_type_code", "code"), ("assistance_type_description", "description")],
        )

        sql = f"""
            SELECT {", ".join(select)}
            FROM assistance.award_transaction t
            JOIN assistance.assistance_listing l
              ON l.assistance_listing_id = t.assistance_listing_id
            {" ".join(joins)}
            WHERE l.cfda_number = %s
            ORDER BY t.action_date_fiscal_year,
                     t.load_batch_id,
                     t.source_row_number,
                     t.assistance_transaction_id
        """
        cur.execute(sql, (TARGET_CFDA,))

        rows = []
        while True:
            batch = cur.fetchmany(5000)
            if not batch:
                break
            rows.extend(dict(zip(names, r)) for r in batch)

        # Empirical summaries.
        annual = {}
        recipients = {}
        pops = {}
        agencies = {}
        types = {}
        descriptions = {}
        batch_counts = Counter()
        transaction_keys = Counter()
        nulls = Counter()

        for r in rows:
            fy = r["fiscal_year"]
            if fy not in annual:
                annual[fy] = {
                    "fiscal_year": fy,
                    "transaction_rows": 0,
                    "federal_action_obligation": Decimal("0"),
                    "rows_with_total_outlay": 0,
                    "sum_total_outlayed_amount_for_overall_award": Decimal("0"),
                    "rows_with_total_obligated_amount": 0,
                    "sum_total_obligated_amount": Decimal("0"),
                    "distinct_recipients": set(),
                    "distinct_pop_places": set(),
                    "distinct_awarding_agencies": set(),
                    "distinct_funding_agencies": set(),
                    "distinct_assistance_types": set(),
                }
            a = annual[fy]
            a["transaction_rows"] += 1
            a["federal_action_obligation"] += dec(r["federal_action_obligation"])

            if r["total_outlay"] is not None:
                a["rows_with_total_outlay"] += 1
                a["sum_total_outlayed_amount_for_overall_award"] += dec(r["total_outlay"])
            if r["total_obligated"] is not None:
                a["rows_with_total_obligated_amount"] += 1
                a["sum_total_obligated_amount"] += dec(r["total_obligated"])

            if r["recipient_id"] is not None:
                a["distinct_recipients"].add(r["recipient_id"])
            if r["pop_id"] is not None:
                a["distinct_pop_places"].add(r["pop_id"])
            if r["awarding_agency_id"] is not None:
                a["distinct_awarding_agencies"].add(r["awarding_agency_id"])
            if r["funding_agency_id"] is not None:
                a["distinct_funding_agencies"].add(r["funding_agency_id"])
            if r["assistance_type_id"] is not None:
                a["distinct_assistance_types"].add(r["assistance_type_id"])

            batch_counts[r["load_batch_id"]] += 1
            if r["transaction_key"]:
                transaction_keys[r["transaction_key"]] += 1

            for k in (
                "recipient_id", "recipient_name", "pop_id", "pop_state",
                "pop_county", "awarding_agency_id", "funding_agency_id",
                "assistance_type_id", "description",
            ):
                if r[k] is None or clean(r[k]) == "":
                    nulls[k] += 1

            rk = (
                r["recipient_id"],
                clean(r["recipient_name"]) or "[NULL/UNRESOLVED RECIPIENT]",
                clean(r["recipient_uei"]),
                clean(r["recipient_duns"]),
            )
            x = recipients.setdefault(
                rk, {"transaction_rows": 0, "obligation": Decimal("0"), "fys": set()}
            )
            x["transaction_rows"] += 1
            x["obligation"] += dec(r["federal_action_obligation"])
            x["fys"].add(fy)

            pk = (
                r["pop_id"],
                clean(r["pop_state"]) or "[NULL]",
                clean(r["pop_county"]) or "[NULL]",
                clean(r["pop_county_fips"]) or "[NULL]",
                clean(r["pop_country"]) or "[NULL]",
            )
            x = pops.setdefault(pk, {"transaction_rows": 0, "obligation": Decimal("0"), "fys": set()})
            x["transaction_rows"] += 1
            x["obligation"] += dec(r["federal_action_obligation"])
            x["fys"].add(fy)

            ak = (
                clean(r["awarding_agency_name"]) or "[NULL]",
                clean(r["awarding_toptier_name"]) or "[NULL]",
                clean(r["funding_agency_name"]) or "[NULL]",
                clean(r["funding_toptier_name"]) or "[NULL]",
            )
            x = agencies.setdefault(ak, {"transaction_rows": 0, "obligation": Decimal("0"), "fys": set()})
            x["transaction_rows"] += 1
            x["obligation"] += dec(r["federal_action_obligation"])
            x["fys"].add(fy)

            tk = (
                clean(r["assistance_type_code"]) or "[NULL]",
                clean(r["assistance_type_description"]) or "[NULL]",
                clean(r["action_type"]) or "[NULL]",
                clean(r["record_type"]) or "[NULL]",
            )
            x = types.setdefault(tk, {"transaction_rows": 0, "obligation": Decimal("0"), "fys": set()})
            x["transaction_rows"] += 1
            x["obligation"] += dec(r["federal_action_obligation"])
            x["fys"].add(fy)

            desc = normalize_text(r["description"]) or "[NULL/BLANK DESCRIPTION]"
            x = descriptions.setdefault(
                desc, {"transaction_rows": 0, "obligation": Decimal("0"), "fys": set()}
            )
            x["transaction_rows"] += 1
            x["obligation"] += dec(r["federal_action_obligation"])
            x["fys"].add(fy)

        annual_rows = []
        for fy in sorted(annual, key=lambda x: (x is None, x)):
            a = annual[fy]
            annual_rows.append(
                {
                    "fiscal_year": fy,
                    "transaction_rows": a["transaction_rows"],
                    "federal_action_obligation": str(a["federal_action_obligation"]),
                    "rows_with_total_outlay": a["rows_with_total_outlay"],
                    "sum_total_outlayed_amount_for_overall_award": str(
                        a["sum_total_outlayed_amount_for_overall_award"]
                    ),
                    "rows_with_total_obligated_amount": a["rows_with_total_obligated_amount"],
                    "sum_total_obligated_amount": str(a["sum_total_obligated_amount"]),
                    "distinct_recipients": len(a["distinct_recipients"]),
                    "distinct_pop_places": len(a["distinct_pop_places"]),
                    "distinct_awarding_agencies": len(a["distinct_awarding_agencies"]),
                    "distinct_funding_agencies": len(a["distinct_funding_agencies"]),
                    "distinct_assistance_types": len(a["distinct_assistance_types"]),
                }
            )

        recipient_rows = [
            {
                "recipient_id": k[0],
                "recipient_name": k[1],
                "recipient_uei": k[2],
                "recipient_duns": k[3],
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"]) if x is not None),
                "transaction_rows": v["transaction_rows"],
                "federal_action_obligation": str(v["obligation"]),
            }
            for k, v in sorted(recipients.items(), key=lambda kv: (-abs(kv[1]["obligation"]), str(kv[0])))
        ]

        pop_rows = [
            {
                "place_of_performance_id": k[0],
                "state": k[1], "county": k[2], "county_fips": k[3], "country": k[4],
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"]) if x is not None),
                "transaction_rows": v["transaction_rows"],
                "federal_action_obligation": str(v["obligation"]),
            }
            for k, v in sorted(pops.items(), key=lambda kv: (-abs(kv[1]["obligation"]), str(kv[0])))
        ]

        agency_rows = [
            {
                "awarding_agency_name": k[0],
                "awarding_toptier_name": k[1],
                "funding_agency_name": k[2],
                "funding_toptier_name": k[3],
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"]) if x is not None),
                "transaction_rows": v["transaction_rows"],
                "federal_action_obligation": str(v["obligation"]),
            }
            for k, v in sorted(agencies.items(), key=lambda kv: (-abs(kv[1]["obligation"]), str(kv[0])))
        ]

        type_rows = [
            {
                "assistance_type_code": k[0],
                "assistance_type_description": k[1],
                "action_type_code": k[2],
                "record_type_code": k[3],
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"]) if x is not None),
                "transaction_rows": v["transaction_rows"],
                "federal_action_obligation": str(v["obligation"]),
            }
            for k, v in sorted(types.items(), key=lambda kv: (-abs(kv[1]["obligation"]), str(kv[0])))
        ]

        description_rows = [
            {
                "transaction_description": k,
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"]) if x is not None),
                "transaction_rows": v["transaction_rows"],
                "federal_action_obligation": str(v["obligation"]),
            }
            for k, v in sorted(descriptions.items(), key=lambda kv: (-abs(kv[1]["obligation"]), kv[0]))
        ]

        detail_rows = []
        for r in rows:
            detail_rows.append(
                {
                    k: (str(v) if isinstance(v, Decimal) else v)
                    for k, v in r.items()
                }
            )

        total_rows = len(rows)
        total_obligation = sum((dec(r["federal_action_obligation"]) for r in rows), Decimal("0"))
        annual_obligation = sum(
            (Decimal(r["federal_action_obligation"]) for r in annual_rows), Decimal("0")
        )
        duplicate_tx_keys = sum(n - 1 for n in transaction_keys.values() if n > 1)
        distinct_batches = sorted(batch_counts)

        checks = [
            (
                f"Normalized listing {TARGET_CFDA} exists",
                bool(listing_rows),
                f"listing_rows={len(listing_rows)}",
            ),
            (
                "At least one normalized 93.774 transaction exists",
                total_rows > 0,
                f"transaction_rows={total_rows}",
            ),
            (
                "Annual federal-action-obligation identity",
                total_obligation == annual_obligation,
                f"detail={total_obligation}; annual={annual_obligation}; diff={total_obligation-annual_obligation}",
            ),
            (
                "No duplicate normalized assistance transaction unique keys within 93.774",
                duplicate_tx_keys == 0,
                f"duplicate_key_excess_rows={duplicate_tx_keys}",
            ),
            (
                "Read-only profiler completed without processing errors",
                not errors,
                f"errors={len(errors)}",
            ),
        ]
        overall = all(ok for _, ok, _ in checks)

        # Outputs.
        write_csv(
            args.output_dir / "usaspending_93774_annual_profile_v0_1.csv",
            annual_rows,
            [
                "fiscal_year", "transaction_rows", "federal_action_obligation",
                "rows_with_total_outlay", "sum_total_outlayed_amount_for_overall_award",
                "rows_with_total_obligated_amount", "sum_total_obligated_amount",
                "distinct_recipients", "distinct_pop_places",
                "distinct_awarding_agencies", "distinct_funding_agencies",
                "distinct_assistance_types",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_recipient_profile_v0_1.csv",
            recipient_rows,
            [
                "recipient_id", "recipient_name", "recipient_uei", "recipient_duns",
                "fiscal_years", "transaction_rows", "federal_action_obligation",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_place_profile_v0_1.csv",
            pop_rows,
            [
                "place_of_performance_id", "state", "county", "county_fips", "country",
                "fiscal_years", "transaction_rows", "federal_action_obligation",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_agency_profile_v0_1.csv",
            agency_rows,
            [
                "awarding_agency_name", "awarding_toptier_name",
                "funding_agency_name", "funding_toptier_name",
                "fiscal_years", "transaction_rows", "federal_action_obligation",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_type_profile_v0_1.csv",
            type_rows,
            [
                "assistance_type_code", "assistance_type_description",
                "action_type_code", "record_type_code",
                "fiscal_years", "transaction_rows", "federal_action_obligation",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_description_profile_v0_1.csv",
            description_rows,
            [
                "transaction_description", "fiscal_years",
                "transaction_rows", "federal_action_obligation",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_transaction_detail_v0_1.csv",
            detail_rows,
            names,
        )
        write_csv(
            args.output_dir / "usaspending_93774_checks_v0_1.csv",
            [
                {"check": n, "status": "PASS" if ok else "FAIL", "detail": d}
                for n, ok, d in checks
            ],
            ["check", "status", "detail"],
        )
        write_csv(
            args.output_dir / "usaspending_93774_null_profile_v0_1.csv",
            [
                {"field": k, "null_or_blank_rows": nulls[k], "total_rows": total_rows}
                for k in sorted(nulls)
            ],
            ["field", "null_or_blank_rows", "total_rows"],
        )
        write_csv(
            args.output_dir / "usaspending_93774_batch_profile_v0_1.csv",
            [
                {"load_batch_id": k, "transaction_rows": batch_counts[k]}
                for k in distinct_batches
            ],
            ["load_batch_id", "transaction_rows"],
        )

        report = [
            "USASPENDING ASSISTANCE LISTING 93.774 RECONCILIATION PROFILE v0.1",
            "=" * 78,
            f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
            "",
            "PURPOSE",
            "-" * 78,
            "Measure the normalized USAspending representation of Medicare",
            "Supplementary Medical Insurance before any overlap/additivity decision.",
            "",
            "BOUNDARY",
            "-" * 78,
            "Read-only. No database writes. No ledger inclusion.",
            "No assumption that 93.774 is additive.",
            "No assumption that 93.774 is overlapping.",
            "Federal action obligation is the transaction-flow control measure.",
            "Overall-award outlay/obligated fields are profiled but NOT summed as",
            "independent transaction flows without first establishing their semantics.",
            "",
            "CORE RESULTS",
            "-" * 78,
            f"Listing rows: {len(listing_rows):,}",
            f"Normalized 93.774 transaction rows: {total_rows:,}",
            f"Load batches represented: {len(distinct_batches):,} ({', '.join(map(str, distinct_batches))})",
            f"Federal action obligation total: {total_obligation}",
            f"Distinct transaction unique keys: {len(transaction_keys):,}",
            f"Duplicate-key excess rows: {duplicate_tx_keys:,}",
            "",
            "ANNUAL FEDERAL ACTION OBLIGATION",
            "-" * 78,
        ]
        for r in annual_rows:
            report.append(
                f"FY{r['fiscal_year']}: rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']} | "
                f"recipients={r['distinct_recipients']} | "
                f"POP places={r['distinct_pop_places']}"
            )

        report += [
            "",
            "TOP RECIPIENT STRUCTURE",
            "-" * 78,
        ]
        for r in recipient_rows[:20]:
            report.append(
                f"{r['recipient_name']} | rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']} | FY={r['fiscal_years']}"
            )

        report += ["", "TOP PLACE-OF-PERFORMANCE STRUCTURE", "-" * 78]
        for r in pop_rows[:20]:
            report.append(
                f"{r['state']} / {r['county']} / {r['county_fips']} | "
                f"rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']} | FY={r['fiscal_years']}"
            )

        report += ["", "TOP AGENCY STRUCTURE", "-" * 78]
        for r in agency_rows[:20]:
            report.append(
                f"Awarding={r['awarding_agency_name']} | "
                f"Funding={r['funding_agency_name']} | "
                f"rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']}"
            )

        report += ["", "TOP TYPE STRUCTURE", "-" * 78]
        for r in type_rows[:20]:
            report.append(
                f"Type={r['assistance_type_code']} {r['assistance_type_description']} | "
                f"Action={r['action_type_code']} | Record={r['record_type_code']} | "
                f"rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']}"
            )

        report += ["", "TOP TRANSACTION DESCRIPTIONS", "-" * 78]
        for r in description_rows[:30]:
            report.append(
                f"{r['transaction_description']} | rows={r['transaction_rows']:,} | "
                f"obligation={r['federal_action_obligation']} | FY={r['fiscal_years']}"
            )

        report += ["", "CHECKS", "-" * 78]
        for n, ok, d in checks:
            report.append(f"[{'PASS' if ok else 'FAIL'}] {n} — {d}")

        report += ["", "WARNINGS", "-" * 78]
        report += warnings or ["None"]
        report += ["", "ERRORS", "-" * 78]
        report += errors or ["None"]
        report += [
            "",
            f"OVERALL: {'PASS' if overall else 'FAIL'}",
            "",
            "INTERPRETATION BOUNDARY",
            "-" * 78,
            "PASS certifies source/profile accounting only. It does NOT establish",
            "that Assistance Listing 93.774 is additive, overlapping, or suitable",
            "for county allocation. That decision requires comparison to the CMS-",
            "native Medicare accounting streams after this empirical profile.",
        ]

        text = "\n".join(report) + "\n"
        (args.output_dir / "usaspending_93774_profile_report_v0_1.txt").write_text(
            text, encoding="utf-8"
        )

        print(text)
        print(f"Outputs: {args.output_dir}")
        return 0 if overall else 1

    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
