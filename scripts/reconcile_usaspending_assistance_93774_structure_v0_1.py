#!/usr/bin/env python3
"""
reconcile_usaspending_assistance_93774_structure_v0_1.py

WCFFBP — USAspending Assistance Listing 93.774
Transaction-Level Structural Reconciliation v0.1

Purpose:
  Determine what the normalized USAspending AL 93.774 transaction structure
  actually represents before any Medicare additivity or county-allocation
  decision.

Hard boundaries:
  * READ ONLY.
  * No database writes.
  * No ledger inclusion.
  * No assumption of additivity.
  * No assumption of overlap.
  * No county-beneficiary-incidence inference from place of performance.
  * federal_action_obligation is the transaction-flow measure.
  * total_obligated_amount and total_outlayed_amount_for_overall_award are
    profiled as award-state observations and are NOT summed as independent
    transaction flows.

Target:
  Assistance Listing 93.774 — Medicare Supplementary Medical Insurance.

This validator profiles:
  1. transaction and award identity structure;
  2. award-to-place and award-to-recipient relationships;
  3. repeated award observations across action dates and fiscal years;
  4. transaction obligation signs and modification behavior;
  5. whether overall-award totals repeat across transaction observations;
  6. county/place concentration and cross-county award reuse;
  7. recipient/place/award combinations that look administrative or aggregate.

PASS certifies structural accounting only. It does NOT itself classify 93.774
as ADDITIVE, OVERLAPPING, CONTROL_ONLY, or suitable for county allocation.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Make repo-root imports work when invoked as:
#   python scripts\\reconcile_usaspending_assistance_93774_structure_v0_1.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from etl.common.db import get_connection

TARGET_CFDA = "93.774"


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def clean(v) -> str:
    return "" if v is None else str(v).strip()


def norm_text(v) -> str:
    return re.sub(r"\s+", " ", clean(v)).strip()


def d(v) -> Decimal:
    if v is None or clean(v) == "":
        return Decimal("0")
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return Decimal("0")


def money(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.01')):,.2f}"


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
          WHERE table_schema=%s AND table_name=%s
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
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def choose(cols: list[str], candidates: list[str]) -> str | None:
    s = set(cols)
    return next((x for x in candidates if x in s), None)


def find_table_with_column(cur, col: str, preferred=()) -> tuple[str, str] | None:
    cur.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name=%s
          AND table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema, table_name
        """,
        (col,),
    )
    found = [(r[0], r[1]) for r in cur.fetchall()]
    for p in preferred:
        if p in found:
            return p
    return found[0] if found else None


def dimension(cur, fk: str, preferred, fields):
    found = find_table_with_column(cur, fk, preferred)
    if not found:
        return None
    schema, table = found
    cols = columns(cur, schema, table)
    out = {"schema": schema, "table": table, "pk": fk}
    for alias, candidates in fields.items():
        out[alias] = choose(cols, candidates)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/raw/usaspending/assistance/validation/"
            "medicare_93774_structural_reconciliation_v0_1"
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

        if not table_exists(cur, "assistance", "assistance_listing"):
            raise RuntimeError("Missing assistance.assistance_listing")
        if not table_exists(cur, "assistance", "award_transaction"):
            raise RuntimeError("Missing assistance.award_transaction")

        lc = columns(cur, "assistance", "assistance_listing")
        tc = columns(cur, "assistance", "award_transaction")

        req_l = {"assistance_listing_id", "cfda_number"}
        req_t = {
            "assistance_transaction_id",
            "assistance_listing_id",
            "load_batch_id",
            "source_row_number",
            "action_date_fiscal_year",
            "federal_action_obligation",
        }
        missing = sorted((req_l - set(lc)) | (req_t - set(tc)))
        if missing:
            raise RuntimeError("Missing required normalized columns: " + ", ".join(missing))

        tx = {
            "transaction_key": choose(tc, ["assistance_transaction_unique_key"]),
            "award_pk": choose(tc, ["assistance_award_id"]),
            "action_date": choose(tc, ["action_date"]),
            "total_obligated": choose(tc, ["total_obligated_amount"]),
            "total_outlay": choose(tc, ["total_outlayed_amount_for_overall_award"]),
            "recipient_id": choose(tc, ["recipient_id"]),
            "pop_id": choose(tc, ["place_of_performance_id"]),
            "awarding_agency_id": choose(tc, ["awarding_agency_id"]),
            "funding_agency_id": choose(tc, ["funding_agency_id"]),
            "assistance_type_id": choose(tc, ["assistance_type_id"]),
            "action_type": choose(tc, ["action_type_code"]),
            "record_type": choose(tc, ["record_type_code"]),
            "correction_delete": choose(tc, ["correction_delete_indicator_code"]),
            "description": choose(tc, ["transaction_description"]),
            "permalink": choose(tc, ["usaspending_permalink"]),
        }

        # Award dimension: preserve candidate USAspending award identity fields.
        award = None
        if tx["award_pk"]:
            award = dimension(
                cur,
                "assistance_award_id",
                [
                    ("assistance", "award"),
                    ("assistance", "assistance_award"),
                ],
                {
                    "unique_key": ["assistance_award_unique_key"],
                    "fain": ["award_id_fain"],
                    "uri": ["award_id_uri"],
                    "sai": ["sai_number"],
                },
            )

        recipient = None
        if tx["recipient_id"]:
            recipient = dimension(
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
                    "uei": ["recipient_uei", "recipient_uei_raw", "recipient_unique_entity_id"],
                    "duns": ["recipient_duns", "recipient_duns_raw"],
                },
            )

        place = None
        if tx["pop_id"]:
            place = dimension(
                cur,
                "place_id",
                [
                    ("procurement", "place"),
                    ("assistance", "place"),
                    ("public", "place"),
                ],
                {
                    "state": [
                        "state_code", "state_abbreviation", "state",
                        "place_of_performance_state_code",
                    ],
                    "county": [
                        "county_name", "county", "place_of_performance_county_name",
                    ],
                    "county_fips": [
                        "county_fips", "county_fips_code",
                        "place_of_performance_county_fips",
                    ],
                    "country": [
                        "country_code", "country", "place_of_performance_country_code",
                    ],
                },
            )

        agency = None
        if tx["awarding_agency_id"] or tx["funding_agency_id"]:
            agency = dimension(
                cur,
                "agency_id",
                [
                    ("procurement", "agency"),
                    ("assistance", "agency"),
                    ("public", "agency"),
                ],
                {
                    "name": ["agency_name", "agency_name_raw", "subtier_agency_name", "name"],
                    "toptier": ["toptier_agency_name", "toptier_name", "agency_toptier_name"],
                },
            )

        atype = None
        if tx["assistance_type_id"]:
            atype = dimension(
                cur,
                "assistance_type_id",
                [("assistance", "assistance_type")],
                {
                    "code": ["assistance_type_code", "code"],
                    "description": [
                        "assistance_type_description", "description",
                        "assistance_type_name",
                    ],
                },
            )

        # Build a single introspection-safe query.
        sel = [
            "t.assistance_transaction_id",
            "t.load_batch_id",
            "t.source_row_number",
            "t.action_date_fiscal_year",
            "t.federal_action_obligation",
            "l.cfda_number",
            "COALESCE(l.cfda_title,'')",
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
        joins = []

        def add_tx(alias, col):
            sel.append(f"t.{qident(col)}" if col else "NULL")
            names.append(alias)

        for alias in (
            "transaction_key", "award_pk", "action_date",
            "total_obligated", "total_outlay", "recipient_id", "pop_id",
            "awarding_agency_id", "funding_agency_id", "assistance_type_id",
            "action_type", "record_type", "correction_delete",
            "description", "permalink",
        ):
            add_tx(alias, tx[alias])

        def add_dim(alias, dim, fkcol, outputs):
            if dim and fkcol:
                joins.append(
                    f"LEFT JOIN {qident(dim['schema'])}.{qident(dim['table'])} {alias} "
                    f"ON {alias}.{qident(dim['pk'])}=t.{qident(fkcol)}"
                )
                for out, field in outputs:
                    sel.append(f"{alias}.{qident(dim[field])}" if dim.get(field) else "NULL")
                    names.append(out)
            else:
                for out, _ in outputs:
                    sel.append("NULL")
                    names.append(out)

        add_dim(
            "aw", award, tx["award_pk"],
            [
                ("award_unique_key", "unique_key"),
                ("award_id_fain", "fain"),
                ("award_id_uri", "uri"),
                ("sai_number", "sai"),
            ],
        )
        add_dim(
            "r", recipient, tx["recipient_id"],
            [
                ("recipient_name", "name"),
                ("recipient_uei", "uei"),
                ("recipient_duns", "duns"),
            ],
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
            [
                ("awarding_agency_name", "name"),
                ("awarding_toptier_name", "toptier"),
            ],
        )
        add_dim(
            "fa", agency, tx["funding_agency_id"],
            [
                ("funding_agency_name", "name"),
                ("funding_toptier_name", "toptier"),
            ],
        )
        add_dim(
            "aty", atype, tx["assistance_type_id"],
            [
                ("assistance_type_code", "code"),
                ("assistance_type_description", "description"),
            ],
        )

        sql = f"""
        SELECT {", ".join(sel)}
        FROM assistance.award_transaction t
        JOIN assistance.assistance_listing l
          ON l.assistance_listing_id=t.assistance_listing_id
        {" ".join(joins)}
        WHERE l.cfda_number=%s
        ORDER BY t.action_date_fiscal_year,
                 t.action_date NULLS LAST,
                 t.load_batch_id,
                 t.source_row_number,
                 t.assistance_transaction_id
        """
        cur.execute(sql, (TARGET_CFDA,))
        rows = [dict(zip(names, r)) for r in cur.fetchall()]

        if not rows:
            errors.append("No normalized 93.774 transactions found.")

        # Choose the best observed award identity without asserting an
        # authoritative hierarchy beyond the available fields.
        def award_identity(r):
            for label, key in (
                ("ASSISTANCE_AWARD_UNIQUE_KEY", "award_unique_key"),
                ("FAIN", "award_id_fain"),
                ("URI", "award_id_uri"),
                ("SAI", "sai_number"),
                ("NORMALIZED_AWARD_PK", "award_pk"),
            ):
                if clean(r.get(key)):
                    return label, clean(r.get(key))
            return "UNRESOLVED", f"TX:{r['assistance_transaction_id']}"

        for r in rows:
            kind, value = award_identity(r)
            r["award_identity_kind"] = kind
            r["award_identity"] = value
            r["place_key"] = "|".join(
                [
                    clean(r["pop_state"]) or "[NULL]",
                    clean(r["pop_county"]) or "[NULL]",
                    clean(r["pop_county_fips"]) or "[NULL]",
                    clean(r["pop_country"]) or "[NULL]",
                ]
            )
            r["recipient_key"] = "|".join(
                [
                    clean(r["recipient_name"]) or "[NULL]",
                    clean(r["recipient_uei"]) or "[NULL]",
                    clean(r["recipient_duns"]) or "[NULL]",
                ]
            )

        # Core transaction controls.
        total_rows = len(rows)
        total_obligation = sum((d(r["federal_action_obligation"]) for r in rows), Decimal("0"))
        tx_keys = Counter(clean(r["transaction_key"]) for r in rows if clean(r["transaction_key"]))
        duplicate_tx_key_excess = sum(n - 1 for n in tx_keys.values() if n > 1)

        # Award-level structural aggregation.
        awards = {}
        for r in rows:
            key = (r["award_identity_kind"], r["award_identity"])
            a = awards.setdefault(
                key,
                {
                    "rows": 0,
                    "obligation": Decimal("0"),
                    "fys": set(),
                    "dates": set(),
                    "places": set(),
                    "recipients": set(),
                    "action_types": set(),
                    "record_types": set(),
                    "descriptions": set(),
                    "total_obligated_values": set(),
                    "total_outlay_values": set(),
                    "positive_rows": 0,
                    "negative_rows": 0,
                    "zero_rows": 0,
                },
            )
            a["rows"] += 1
            ob = d(r["federal_action_obligation"])
            a["obligation"] += ob
            if ob > 0:
                a["positive_rows"] += 1
            elif ob < 0:
                a["negative_rows"] += 1
            else:
                a["zero_rows"] += 1
            if r["fiscal_year"] is not None:
                a["fys"].add(r["fiscal_year"])
            if clean(r["action_date"]):
                a["dates"].add(clean(r["action_date"]))
            a["places"].add(r["place_key"])
            a["recipients"].add(r["recipient_key"])
            a["action_types"].add(clean(r["action_type"]) or "[NULL]")
            a["record_types"].add(clean(r["record_type"]) or "[NULL]")
            a["descriptions"].add(norm_text(r["description"]) or "[NULL]")
            if r["total_obligated"] is not None:
                a["total_obligated_values"].add(clean(r["total_obligated"]))
            if r["total_outlay"] is not None:
                a["total_outlay_values"].add(clean(r["total_outlay"]))

        award_rows = []
        for (kind, ident), a in sorted(
            awards.items(),
            key=lambda kv: (-abs(kv[1]["obligation"]), kv[0][1]),
        ):
            award_rows.append(
                {
                    "award_identity_kind": kind,
                    "award_identity": ident,
                    "transaction_rows": a["rows"],
                    "fiscal_years": ";".join(str(x) for x in sorted(a["fys"])),
                    "action_dates": len(a["dates"]),
                    "net_federal_action_obligation": str(a["obligation"]),
                    "positive_rows": a["positive_rows"],
                    "negative_rows": a["negative_rows"],
                    "zero_rows": a["zero_rows"],
                    "distinct_places": len(a["places"]),
                    "places": " || ".join(sorted(a["places"])),
                    "distinct_recipients": len(a["recipients"]),
                    "recipients": " || ".join(sorted(a["recipients"])),
                    "distinct_action_types": len(a["action_types"]),
                    "action_types": ";".join(sorted(a["action_types"])),
                    "distinct_record_types": len(a["record_types"]),
                    "record_types": ";".join(sorted(a["record_types"])),
                    "distinct_descriptions": len(a["descriptions"]),
                    "descriptions": " || ".join(sorted(a["descriptions"])),
                    "distinct_total_obligated_values": len(a["total_obligated_values"]),
                    "total_obligated_values": " || ".join(sorted(a["total_obligated_values"])),
                    "distinct_total_outlay_values": len(a["total_outlay_values"]),
                    "total_outlay_values": " || ".join(sorted(a["total_outlay_values"])),
                }
            )

        # Place profiles and cross-award reuse.
        places = {}
        for r in rows:
            p = places.setdefault(
                r["place_key"],
                {
                    "rows": 0,
                    "obligation": Decimal("0"),
                    "awards": set(),
                    "fys": set(),
                    "recipients": set(),
                    "dates": set(),
                },
            )
            p["rows"] += 1
            p["obligation"] += d(r["federal_action_obligation"])
            p["awards"].add((r["award_identity_kind"], r["award_identity"]))
            if r["fiscal_year"] is not None:
                p["fys"].add(r["fiscal_year"])
            p["recipients"].add(r["recipient_key"])
            if clean(r["action_date"]):
                p["dates"].add(clean(r["action_date"]))

        place_rows = [
            {
                "place_key": k,
                "transaction_rows": v["rows"],
                "net_federal_action_obligation": str(v["obligation"]),
                "distinct_awards": len(v["awards"]),
                "distinct_recipients": len(v["recipients"]),
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"])),
                "action_dates": len(v["dates"]),
            }
            for k, v in sorted(places.items(), key=lambda kv: (-abs(kv[1]["obligation"]), kv[0]))
        ]

        # Award/place matrix makes cross-county reuse explicit.
        award_place = {}
        for r in rows:
            k = (r["award_identity_kind"], r["award_identity"], r["place_key"])
            x = award_place.setdefault(
                k, {"rows": 0, "obligation": Decimal("0"), "fys": set(), "dates": set()}
            )
            x["rows"] += 1
            x["obligation"] += d(r["federal_action_obligation"])
            if r["fiscal_year"] is not None:
                x["fys"].add(r["fiscal_year"])
            if clean(r["action_date"]):
                x["dates"].add(clean(r["action_date"]))

        award_place_rows = [
            {
                "award_identity_kind": k[0],
                "award_identity": k[1],
                "place_key": k[2],
                "transaction_rows": v["rows"],
                "net_federal_action_obligation": str(v["obligation"]),
                "fiscal_years": ";".join(str(x) for x in sorted(v["fys"])),
                "action_dates": len(v["dates"]),
            }
            for k, v in sorted(
                award_place.items(),
                key=lambda kv: (-abs(kv[1]["obligation"]), kv[0][1], kv[0][2]),
            )
        ]

        # Repeated award-state values: if the same total award obligation/outlay
        # appears on multiple transaction rows, count the repetitions but never
        # treat them as independent flows.
        state_obs = defaultdict(lambda: {"rows": 0, "obligation": Decimal("0")})
        for r in rows:
            for field in ("total_obligated", "total_outlay"):
                val = clean(r[field])
                if not val:
                    continue
                k = (
                    r["award_identity_kind"],
                    r["award_identity"],
                    field,
                    val,
                )
                state_obs[k]["rows"] += 1
                state_obs[k]["obligation"] += d(r["federal_action_obligation"])

        state_rows = [
            {
                "award_identity_kind": k[0],
                "award_identity": k[1],
                "award_state_field": k[2],
                "observed_value": k[3],
                "transaction_rows_carrying_value": v["rows"],
                "net_transaction_obligation_on_rows": str(v["obligation"]),
                "repeated_value_flag": "YES" if v["rows"] > 1 else "NO",
            }
            for k, v in sorted(
                state_obs.items(),
                key=lambda kv: (-kv[1]["rows"], kv[0][1], kv[0][2], kv[0][3]),
            )
        ]

        # Annual sign/modification profile.
        annual = {}
        for r in rows:
            fy = r["fiscal_year"]
            a = annual.setdefault(
                fy,
                {
                    "rows": 0,
                    "obligation": Decimal("0"),
                    "positive": Decimal("0"),
                    "negative": Decimal("0"),
                    "zero": 0,
                    "positive_rows": 0,
                    "negative_rows": 0,
                    "awards": set(),
                    "places": set(),
                    "recipients": set(),
                },
            )
            a["rows"] += 1
            ob = d(r["federal_action_obligation"])
            a["obligation"] += ob
            if ob > 0:
                a["positive"] += ob
                a["positive_rows"] += 1
            elif ob < 0:
                a["negative"] += ob
                a["negative_rows"] += 1
            else:
                a["zero"] += 1
            a["awards"].add((r["award_identity_kind"], r["award_identity"]))
            a["places"].add(r["place_key"])
            a["recipients"].add(r["recipient_key"])

        annual_rows = [
            {
                "fiscal_year": fy,
                "transaction_rows": a["rows"],
                "distinct_awards": len(a["awards"]),
                "distinct_places": len(a["places"]),
                "distinct_recipients": len(a["recipients"]),
                "positive_rows": a["positive_rows"],
                "negative_rows": a["negative_rows"],
                "zero_rows": a["zero"],
                "positive_obligation": str(a["positive"]),
                "negative_obligation": str(a["negative"]),
                "net_federal_action_obligation": str(a["obligation"]),
                "sign_identity_difference": str(a["obligation"] - a["positive"] - a["negative"]),
            }
            for fy, a in sorted(annual.items(), key=lambda kv: (kv[0] is None, kv[0]))
        ]

        annual_total = sum(
            (Decimal(r["net_federal_action_obligation"]) for r in annual_rows),
            Decimal("0"),
        )
        award_total = sum(
            (Decimal(r["net_federal_action_obligation"]) for r in award_rows),
            Decimal("0"),
        )
        place_total = sum(
            (Decimal(r["net_federal_action_obligation"]) for r in place_rows),
            Decimal("0"),
        )
        award_place_total = sum(
            (Decimal(r["net_federal_action_obligation"]) for r in award_place_rows),
            Decimal("0"),
        )

        cross_place_awards = [r for r in award_rows if r["distinct_places"] > 1]
        multi_fy_awards = [r for r in award_rows if ";" in r["fiscal_years"]]
        repeated_total_obligation_states = [
            r for r in state_rows
            if r["award_state_field"] == "total_obligated"
            and r["repeated_value_flag"] == "YES"
        ]
        repeated_total_outlay_states = [
            r for r in state_rows
            if r["award_state_field"] == "total_outlay"
            and r["repeated_value_flag"] == "YES"
        ]

        all_recipient_names = {clean(r["recipient_name"]) for r in rows}
        multiple_recipients_only = (
            len(all_recipient_names) == 1
            and next(iter(all_recipient_names), "").upper() == "MULTIPLE RECIPIENTS"
        )

        checks = [
            (
                "At least one normalized 93.774 transaction exists",
                total_rows > 0,
                f"rows={total_rows}",
            ),
            (
                "No duplicate normalized transaction unique keys",
                duplicate_tx_key_excess == 0,
                f"duplicate_key_excess_rows={duplicate_tx_key_excess}",
            ),
            (
                "Annual transaction-flow identity",
                annual_total == total_obligation,
                f"detail={total_obligation}; annual={annual_total}; diff={total_obligation-annual_total}",
            ),
            (
                "Award transaction-flow identity",
                award_total == total_obligation,
                f"detail={total_obligation}; award={award_total}; diff={total_obligation-award_total}",
            ),
            (
                "Place transaction-flow identity",
                place_total == total_obligation,
                f"detail={total_obligation}; place={place_total}; diff={total_obligation-place_total}",
            ),
            (
                "Award-place transaction-flow identity",
                award_place_total == total_obligation,
                f"detail={total_obligation}; award_place={award_place_total}; diff={total_obligation-award_place_total}",
            ),
            (
                "All annual sign identities balance",
                all(Decimal(r["sign_identity_difference"]) == 0 for r in annual_rows),
                "all annual net = positive + negative",
            ),
            (
                "Read-only structural reconciliation completed without processing errors",
                not errors,
                f"errors={len(errors)}",
            ),
        ]
        overall = all(ok for _, ok, _ in checks)

        # Detail export.
        detail_fields = names + [
            "award_identity_kind", "award_identity", "place_key", "recipient_key"
        ]
        detail_rows = []
        for r in rows:
            detail_rows.append(
                {
                    k: (str(v) if isinstance(v, Decimal) else v)
                    for k, v in r.items()
                    if k in detail_fields
                }
            )

        write_csv(
            args.output_dir / "usaspending_93774_structural_transaction_detail_v0_1.csv",
            detail_rows,
            detail_fields,
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_award_profile_v0_1.csv",
            award_rows,
            [
                "award_identity_kind", "award_identity", "transaction_rows",
                "fiscal_years", "action_dates", "net_federal_action_obligation",
                "positive_rows", "negative_rows", "zero_rows",
                "distinct_places", "places", "distinct_recipients", "recipients",
                "distinct_action_types", "action_types",
                "distinct_record_types", "record_types",
                "distinct_descriptions", "descriptions",
                "distinct_total_obligated_values", "total_obligated_values",
                "distinct_total_outlay_values", "total_outlay_values",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_award_place_matrix_v0_1.csv",
            award_place_rows,
            [
                "award_identity_kind", "award_identity", "place_key",
                "transaction_rows", "net_federal_action_obligation",
                "fiscal_years", "action_dates",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_place_profile_v0_1.csv",
            place_rows,
            [
                "place_key", "transaction_rows", "net_federal_action_obligation",
                "distinct_awards", "distinct_recipients", "fiscal_years",
                "action_dates",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_award_state_repetition_v0_1.csv",
            state_rows,
            [
                "award_identity_kind", "award_identity", "award_state_field",
                "observed_value", "transaction_rows_carrying_value",
                "net_transaction_obligation_on_rows", "repeated_value_flag",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_annual_profile_v0_1.csv",
            annual_rows,
            [
                "fiscal_year", "transaction_rows", "distinct_awards",
                "distinct_places", "distinct_recipients", "positive_rows",
                "negative_rows", "zero_rows", "positive_obligation",
                "negative_obligation", "net_federal_action_obligation",
                "sign_identity_difference",
            ],
        )
        write_csv(
            args.output_dir / "usaspending_93774_structural_checks_v0_1.csv",
            [
                {"check": n, "status": "PASS" if ok else "FAIL", "detail": detail}
                for n, ok, detail in checks
            ],
            ["check", "status", "detail"],
        )

        report = [
            "USASPENDING ASSISTANCE LISTING 93.774",
            "TRANSACTION-LEVEL STRUCTURAL RECONCILIATION v0.1",
            "=" * 78,
            f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
            "",
            "PURPOSE",
            "-" * 78,
            "Determine what the normalized 93.774 transaction structure represents",
            "before any Medicare additivity or county-allocation decision.",
            "",
            "BOUNDARY",
            "-" * 78,
            "READ ONLY. No database writes. No ledger inclusion.",
            "No assumption of additivity or overlap.",
            "No beneficiary-incidence inference from place of performance.",
            "Federal action obligation is the transaction-flow control measure.",
            "Overall-award obligation/outlay fields are award-state observations only;",
            "they are not summed as independent transaction flows.",
            "",
            "CORE TRANSACTION CONTROLS",
            "-" * 78,
            f"Transaction rows: {total_rows:,}",
            f"Net federal action obligation: ${money(total_obligation)}",
            f"Distinct transaction unique keys: {len(tx_keys):,}",
            f"Duplicate-key excess rows: {duplicate_tx_key_excess:,}",
            f"Distinct structural award identities: {len(awards):,}",
            f"Distinct places: {len(places):,}",
            f"Recipient names observed: {len(all_recipient_names):,}",
            f"Recipient is exclusively MULTIPLE RECIPIENTS: {multiple_recipients_only}",
            "",
            "STRUCTURAL SIGNALS",
            "-" * 78,
            f"Awards observed in >1 place: {len(cross_place_awards):,}",
            f"Awards observed in >1 fiscal year: {len(multi_fy_awards):,}",
            f"Repeated total-obligated award-state observations: "
            f"{len(repeated_total_obligation_states):,}",
            f"Repeated total-outlay award-state observations: "
            f"{len(repeated_total_outlay_states):,}",
            "",
            "ANNUAL TRANSACTION STRUCTURE",
            "-" * 78,
        ]

        for r in annual_rows:
            report.append(
                f"FY{r['fiscal_year']}: rows={r['transaction_rows']:,} | "
                f"awards={r['distinct_awards']:,} | places={r['distinct_places']:,} | "
                f"positive=${money(Decimal(r['positive_obligation']))} | "
                f"negative=${money(Decimal(r['negative_obligation']))} | "
                f"net=${money(Decimal(r['net_federal_action_obligation']))}"
            )

        report += ["", "TOP AWARD STRUCTURES", "-" * 78]
        for r in award_rows[:30]:
            report.append(
                f"{r['award_identity_kind']}={r['award_identity']} | "
                f"rows={r['transaction_rows']:,} | FY={r['fiscal_years']} | "
                f"places={r['distinct_places']} | recipients={r['distinct_recipients']} | "
                f"net=${money(Decimal(r['net_federal_action_obligation']))}"
            )

        report += ["", "PLACE STRUCTURE", "-" * 78]
        for r in place_rows:
            report.append(
                f"{r['place_key']} | rows={r['transaction_rows']:,} | "
                f"awards={r['distinct_awards']:,} | recipients={r['distinct_recipients']:,} | "
                f"FY={r['fiscal_years']} | "
                f"net=${money(Decimal(r['net_federal_action_obligation']))}"
            )

        report += ["", "CHECKS", "-" * 78]
        for n, ok, detail in checks:
            report.append(f"[{'PASS' if ok else 'FAIL'}] {n} — {detail}")

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
            "PASS certifies transaction/award/place structural accounting only.",
            "It does NOT establish ADDITIVE, OVERLAPPING, CONTROL_ONLY, or county",
            "allocation status. Those decisions require interpretation of the observed",
            "structure against the CMS-native Medicare accounting streams.",
        ]

        text = "\n".join(report) + "\n"
        (args.output_dir / "usaspending_93774_structural_report_v0_1.txt").write_text(
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
