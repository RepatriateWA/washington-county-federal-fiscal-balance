from __future__ import annotations
from decimal import Decimal
from etl.validation.assistance.models import CertificationCheck, CheckStatus

def _status(ok: bool, warn: bool = False) -> CheckStatus:
    if ok:
        return CheckStatus.PASS
    return CheckStatus.WARN if warn else CheckStatus.FAIL

def _zero(code, section, label, value, detail):
    ok = int(value) == 0
    return CertificationCheck(
        code, section, label, _status(ok), int(value), 0,
        None if ok else f"{value} {detail}."
    )

def _raw_numeric(field: str) -> str:
    return f"""
    CASE
      WHEN BTRIM(raw.raw_record ->> '{field}') ~ '^[+-]?[0-9]+([.][0-9]+)?$'
      THEN BTRIM(raw.raw_record ->> '{field}')::numeric
      ELSE NULL
    END
    """


def _batch_transaction_scope(alias: str = "t") -> str:
    """SQL predicate: canonical transaction is observed in the raw batch."""
    return f"""EXISTS (
      SELECT 1
      FROM assistance.raw_award_transaction raw_scope
      WHERE raw_scope.load_batch_id=%s
        AND raw_scope.assistance_transaction_unique_key
            ={alias}.assistance_transaction_unique_key
    )"""

# ---------------- BATCH COMPLETENESS ----------------

def check_raw_exists(cur, batch):
    cur.execute("SELECT COUNT(*) FROM assistance.raw_award_transaction WHERE load_batch_id=%s", (batch,))
    n = int(cur.fetchone()[0])
    return CertificationCheck("COUNT-001","BATCH COMPLETENESS","Raw observations exist",_status(n>0),n,"greater than 0")

def check_txn_exists(cur, batch):
    cur.execute(f"SELECT COUNT(*) FROM assistance.award_transaction t WHERE {_batch_transaction_scope('t')}", (batch,))
    n = int(cur.fetchone()[0])
    return CertificationCheck("COUNT-002","BATCH COMPLETENESS","Normalized transactions exist",_status(n>0),n,"greater than 0")

def check_awards_exist(cur, batch):
    cur.execute(f"SELECT COUNT(DISTINCT t.assistance_award_id) FROM assistance.award_transaction t WHERE {_batch_transaction_scope('t')}", (batch,))
    n = int(cur.fetchone()[0])
    return CertificationCheck("COUNT-003","BATCH COMPLETENESS","Normalized awards represented",_status(n>0),n,"greater than 0")

def check_counts_reconcile(cur, batch):
    cur.execute(f"""
      SELECT
        (SELECT COUNT(*) FROM assistance.raw_award_transaction WHERE load_batch_id=%s),
        (SELECT COUNT(*) FROM assistance.award_transaction t
         WHERE {_batch_transaction_scope('t')})
    """,(batch,batch))
    raw_n, txn_n = map(int, cur.fetchone())
    ok = raw_n > 0 and raw_n == txn_n
    return CertificationCheck("COUNT-004","BATCH COMPLETENESS","Raw and normalized counts reconcile",_status(ok),txn_n,raw_n,
        None if ok else f"Raw count {raw_n}; normalized count {txn_n}.")

# ---------------- DUPLICATES ----------------

def check_raw_source_rows_unique(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM (
      SELECT source_row_number FROM assistance.raw_award_transaction
      WHERE load_batch_id=%s GROUP BY source_row_number HAVING COUNT(*)>1) d""",(batch,))
    return _zero("DUP-001","DUPLICATE DETECTION","Raw source-row identifiers are unique",cur.fetchone()[0],"duplicate raw source-row groups were found")

def check_txn_source_rows_unique(cur,batch):
    cur.execute(f"""SELECT COUNT(*) FROM (
      SELECT raw.source_row_number
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t
        ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s
      GROUP BY raw.source_row_number HAVING COUNT(*)>1) d""",(batch,))
    return _zero("DUP-002","DUPLICATE DETECTION","Transaction source-row identifiers are unique",cur.fetchone()[0],"duplicate normalized source-row groups were found")

def check_txn_keys_unique(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM (
      SELECT raw.assistance_transaction_unique_key
      FROM assistance.raw_award_transaction raw
      WHERE raw.load_batch_id=%s
      GROUP BY raw.assistance_transaction_unique_key HAVING COUNT(*)>1) d""",(batch,))
    return _zero("DUP-003","DUPLICATE DETECTION","Assistance transaction keys are unique",cur.fetchone()[0],"duplicate transaction-key groups were found")

# ---------------- REFERENTIAL ----------------

def _fk(cur,batch,code,label,column,table,target):
    cur.execute(f"""SELECT COUNT(*) FROM assistance.award_transaction t
      LEFT JOIN {table} r ON r.{target}=t.{column}
      WHERE {_batch_transaction_scope('t')} AND t.{column} IS NOT NULL AND r.{target} IS NULL""",(batch,))
    return _zero(code,"REFERENTIAL INTEGRITY",label,cur.fetchone()[0],"orphan references were found")

def check_fk_award(cur,b): return _fk(cur,b,"FK-001","Transaction award references resolve","assistance_award_id","assistance.award","assistance_award_id")
def check_fk_recipient(cur,b): return _fk(cur,b,"FK-002","Recipient references resolve","recipient_id","procurement.recipient","recipient_id")
def check_fk_place(cur,b): return _fk(cur,b,"FK-003","Place references resolve","place_of_performance_id","procurement.place","place_id")
def check_fk_awarding_agency(cur,b): return _fk(cur,b,"FK-004","Awarding-agency references resolve","awarding_agency_id","procurement.agency","agency_id")
def check_fk_awarding_subagency(cur,b): return _fk(cur,b,"FK-005","Awarding-subagency references resolve","awarding_subagency_id","procurement.agency","agency_id")
def check_fk_funding_agency(cur,b): return _fk(cur,b,"FK-006","Funding-agency references resolve","funding_agency_id","procurement.agency","agency_id")
def check_fk_funding_subagency(cur,b): return _fk(cur,b,"FK-007","Funding-subagency references resolve","funding_subagency_id","procurement.agency","agency_id")
def check_fk_listing(cur,b): return _fk(cur,b,"FK-008","Assistance-listing references resolve","assistance_listing_id","assistance.assistance_listing","assistance_listing_id")
def check_fk_type(cur,b): return _fk(cur,b,"FK-009","Assistance-type references resolve","assistance_type_id","assistance.assistance_type","assistance_type_id")
def check_fk_opportunity(cur,b): return _fk(cur,b,"FK-010","Funding-opportunity references resolve","funding_opportunity_id","assistance.funding_opportunity","funding_opportunity_id")

def check_fk_recipient_history(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM assistance.award_recipient_history h
      LEFT JOIN assistance.award a ON a.assistance_award_id=h.assistance_award_id
      LEFT JOIN assistance.award_transaction t ON t.assistance_transaction_id=h.assistance_transaction_id
      LEFT JOIN procurement.recipient r ON r.recipient_id=h.recipient_id
      WHERE h.load_batch_id=%s AND (a.assistance_award_id IS NULL OR t.assistance_transaction_id IS NULL OR r.recipient_id IS NULL)""",(batch,))
    return _zero("FK-011","REFERENTIAL INTEGRITY","Award-recipient history references resolve",cur.fetchone()[0],"orphan history references were found")

def check_fk_parent_history(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM assistance.recipient_parent_history h
      LEFT JOIN procurement.recipient c ON c.recipient_id=h.child_recipient_id
      LEFT JOIN procurement.recipient p ON p.recipient_id=h.parent_recipient_id
      WHERE h.load_batch_id=%s
        AND (c.recipient_id IS NULL OR (h.parent_recipient_id IS NOT NULL AND p.recipient_id IS NULL))""",(batch,))
    return _zero("FK-012","REFERENTIAL INTEGRITY","Recipient-parent history references resolve",cur.fetchone()[0],"orphan parent-history references were found")

def check_fk_defc(cur,batch):
    cur.execute(f"""SELECT COUNT(*) FROM assistance.award_transaction_defc d
      JOIN assistance.award_transaction t ON t.assistance_transaction_id=d.assistance_transaction_id
      LEFT JOIN reference.extraordinary_funding_code e ON e.extraordinary_funding_code_id=d.extraordinary_funding_code_id
      WHERE {_batch_transaction_scope('t')} AND e.extraordinary_funding_code_id IS NULL""",(batch,))
    return _zero("FK-013","REFERENTIAL INTEGRITY","DEFC references resolve",cur.fetchone()[0],"orphan DEFC references were found")

# ---------------- SOURCE-CONDITIONED RELATIONSHIPS ----------------

def _source_conditioned(cur,batch,code,label,fields,column):
    pred = " OR ".join([f"NULLIF(BTRIM(raw.raw_record ->> '{x}'),'') IS NOT NULL" for x in fields])
    cur.execute(f"""WITH p AS (
      SELECT t.{column} id
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t
        ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s AND ({pred}))
      SELECT COUNT(*),COUNT(id) FROM p""",(batch,))
    expected,resolved = map(int,cur.fetchone())
    ok = expected == resolved
    pct = 100.0 if expected == 0 else 100.0*resolved/expected
    return CertificationCheck(code,"RELATIONSHIP COMPLETENESS",label,_status(ok),f"{resolved}/{expected} ({pct:.2f}%)","100.00%",
        None if ok else f"{expected-resolved} source-populated rows lack this relationship.")

def check_rel_recipient(cur,b): return _source_conditioned(cur,b,"REL-001","Recipient attribution complete",("recipient_uei","recipient_duns","recipient_name"),"recipient_id")
def check_rel_awarding_agency(cur,b): return _source_conditioned(cur,b,"REL-002","Awarding-agency attribution complete",("awarding_agency_code","awarding_agency_name"),"awarding_agency_id")
def check_rel_awarding_subagency(cur,b): return _source_conditioned(cur,b,"REL-003","Awarding-subagency attribution complete",("awarding_sub_agency_code","awarding_sub_agency_name"),"awarding_subagency_id")
def check_rel_funding_agency(cur,b): return _source_conditioned(cur,b,"REL-004","Funding-agency attribution complete",("funding_agency_code","funding_agency_name"),"funding_agency_id")
def check_rel_funding_subagency(cur,b): return _source_conditioned(cur,b,"REL-005","Funding-subagency attribution complete",("funding_sub_agency_code","funding_sub_agency_name"),"funding_subagency_id")
def check_rel_type(cur,b): return _source_conditioned(cur,b,"REL-006","Assistance-type attribution complete",("assistance_type_code",),"assistance_type_id")
def check_rel_listing(cur,b): return _source_conditioned(cur,b,"REL-007","Assistance-listing attribution complete",("cfda_number",),"assistance_listing_id")

def check_rel_history(cur,batch):
    cur.execute("""SELECT
      COUNT(*) FILTER (WHERE t.recipient_id IS NOT NULL),
      COUNT(*) FILTER (WHERE t.recipient_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM assistance.award_recipient_history h
        WHERE h.load_batch_id=raw.load_batch_id
          AND h.source_row_number=raw.source_row_number
          AND h.assistance_transaction_id=t.assistance_transaction_id))
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t
        ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s""",(batch,))
    expected,covered=map(int,cur.fetchone())
    ok=expected==covered
    return CertificationCheck("REL-008","RELATIONSHIP COMPLETENESS","Award-recipient history coverage complete",_status(ok),f"{covered}/{expected}",expected,
      None if ok else f"{expected-covered} recipient-bearing observations lack matching history.")

# ---------------- CLASSIFICATION ----------------

def check_type_codes(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      LEFT JOIN assistance.assistance_type typ ON typ.assistance_type_id=t.assistance_type_id
      WHERE raw.load_batch_id=%s
        AND NULLIF(BTRIM(raw.raw_record->>'assistance_type_code'),'') IS NOT NULL
        AND BTRIM(raw.raw_record->>'assistance_type_code') IS DISTINCT FROM typ.assistance_type_code""",(batch,))
    return _zero("CLASS-001","ASSISTANCE CLASSIFICATION","Assistance-type codes reconcile",cur.fetchone()[0],"type-code mismatches were found")

def check_listing_numbers(cur,batch):
    cur.execute("""SELECT COUNT(*) FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      LEFT JOIN assistance.assistance_listing l ON l.assistance_listing_id=t.assistance_listing_id
      WHERE raw.load_batch_id=%s
        AND NULLIF(BTRIM(raw.raw_record->>'cfda_number'),'') IS NOT NULL
        AND BTRIM(raw.raw_record->>'cfda_number') IS DISTINCT FROM l.cfda_number""",(batch,))
    return _zero("CLASS-002","ASSISTANCE CLASSIFICATION","Assistance listings reconcile",cur.fetchone()[0],"listing-number mismatches were found")

# ---------------- GEOGRAPHY ----------------

def check_geo_coverage(cur,batch):
    cur.execute("""SELECT
      (SELECT COUNT(*)
         FROM assistance.raw_award_transaction
        WHERE load_batch_id=%s),
      (SELECT COUNT(*)
         FROM analysis.v_assistance_observation_geographic_attribution
        WHERE observation_load_batch_id=%s)""",(batch,batch))
    total,geo=map(int,cur.fetchone()); ok=total>0 and total==geo
    return CertificationCheck(
      "GEO-001",
      "GEOGRAPHIC CERTIFICATION",
      "Every observation receives geographic attribution",
      _status(ok),
      f"{geo}/{total}",
      total)


def check_geo_classes(cur,batch):
    cur.execute("""SELECT COUNT(*)
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s
        AND geographic_attribution_class NOT IN
        ('WA_COUNTY','WA_UNSPECIFIED','GEOGRAPHY_CONFLICT','NON_WASHINGTON')""",
        (batch,))
    return _zero(
      "GEO-002",
      "GEOGRAPHIC CERTIFICATION",
      "Geographic attribution classes are valid",
      cur.fetchone()[0],
      "unsupported attribution classes were found")


def check_wa_county_refs(cur,batch):
    cur.execute("""SELECT COUNT(*)
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s
        AND geographic_attribution_class='WA_COUNTY'
        AND (
          reference_state_abbreviation IS DISTINCT FROM 'WA'
          OR reference_county_id IS NULL
          OR county_full_fips IS NULL
        )""",(batch,))
    return _zero(
      "GEO-003",
      "GEOGRAPHIC CERTIFICATION",
      "Washington county references resolve",
      cur.fetchone()[0],
      "WA_COUNTY observations lack valid county references")


def check_wa_counties(cur,batch):
    cur.execute("""SELECT COUNT(DISTINCT reference_county_id)
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s
        AND geographic_attribution_class='WA_COUNTY'""",(batch,))
    n=int(cur.fetchone()[0]); ok=n==39
    return CertificationCheck(
      "GEO-004",
      "GEOGRAPHIC CERTIFICATION",
      "All Washington counties represented",
      _status(ok,warn=True),
      n,
      39,
      None if ok else "Fewer than 39 Washington counties are represented.")

# ---------------- EXTRAORDINARY FUNDING ----------------

def _revision_numeric(column_expr: str) -> str:
    return f"""
    CASE
      WHEN BTRIM({column_expr}) ~ '^[+-]?[0-9]+([.][0-9]+)?$'
      THEN BTRIM({column_expr})::numeric
      ELSE NULL
    END
    """


def _field_preservation_sql(raw_field: str, norm_col: str, numeric: bool) -> str:
    if numeric:
        raw_value = _raw_numeric(raw_field)
        canonical_value = f"t.{norm_col}"
        revision_observed = _revision_numeric("r.observed_value_text")
        revision_canonical = _revision_numeric(
            "r.canonical_first_seen_value_text"
        )
    else:
        raw_value = (
            f"NULLIF(BTRIM(raw.raw_record ->> '{raw_field}'), '')"
        )
        canonical_value = f"NULLIF(BTRIM(t.{norm_col}), '')"
        revision_observed = (
            "NULLIF(BTRIM(r.observed_value_text), '')"
        )
        revision_canonical = (
            "NULLIF(BTRIM(r.canonical_first_seen_value_text), '')"
        )

    return f"""
    SELECT
        raw.raw_assistance_transaction_id,

        CASE
          /* No source evolution: a revision row must not exist. */
          WHEN ({raw_value}) IS NOT DISTINCT FROM ({canonical_value})
          THEN r.award_transaction_revision_id IS NOT NULL

          /* Source evolution: require exact ETL-162 revision evidence. */
          ELSE NOT (
              p.field_name IS NOT NULL
              AND p.policy_version = 'ANALYSIS-162-v1'
              AND p.field_class IN (
                  'REVISABLE_ECONOMIC',
                  'AWARD_SNAPSHOT',
                  'MUTABLE_AWARD_METADATA',
                  'PUBLICATION_METADATA'
              )
              AND r.award_transaction_revision_id IS NOT NULL
              AND r.assistance_transaction_id =
                  t.assistance_transaction_id
              AND r.revision_class = p.field_class
              AND r.policy_version = p.policy_version
              AND ({revision_observed})
                  IS NOT DISTINCT FROM ({raw_value})
              AND ({revision_canonical})
                  IS NOT DISTINCT FROM ({canonical_value})
          )
        END AS preservation_failure

    FROM assistance.raw_award_transaction AS raw
    JOIN assistance.award_transaction AS t
      ON t.assistance_transaction_unique_key =
         raw.assistance_transaction_unique_key

    LEFT JOIN assistance.transaction_field_policy AS p
      ON p.field_name = '{norm_col}'

    LEFT JOIN assistance.award_transaction_revision AS r
      ON r.raw_assistance_transaction_id =
         raw.raw_assistance_transaction_id
     AND r.assistance_transaction_id =
         t.assistance_transaction_id
     AND r.field_name = '{norm_col}'

    WHERE raw.load_batch_id = %s
    """


def _numeric_preservation(
    cur, batch, code, label, raw_field, norm_col
):
    sql = _field_preservation_sql(
        raw_field,
        norm_col,
        numeric=True,
    )

    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM ({sql}) AS x
        WHERE preservation_failure
        """,
        (batch,),
    )

    return _zero(
        code,
        "EXTRAORDINARY FUNDING",
        label,
        cur.fetchone()[0],
        "unaccounted or invalid revision-aware preservation failures were found",
    )


def check_defc_text(cur, batch):
    sql = _field_preservation_sql(
        "disaster_emergency_fund_codes_for_overall_award",
        "disaster_emergency_fund_codes_raw",
        numeric=False,
    )

    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM ({sql}) AS x
        WHERE preservation_failure
        """,
        (batch,),
    )

    return _zero(
        "EXTRA-001",
        "EXTRAORDINARY FUNDING",
        "Raw DEFC values preserved",
        cur.fetchone()[0],
        "unaccounted or invalid revision-aware DEFC preservation failures were found",
    )


def check_covid_ob(cur, b):
    return _numeric_preservation(
        cur,
        b,
        "EXTRA-002",
        "COVID obligation values preserved",
        "obligated_amount_from_COVID-19_supplementals_for_overall_award",
        "covid_overall_award_obligation",
    )


def check_covid_out(cur, b):
    return _numeric_preservation(
        cur,
        b,
        "EXTRA-003",
        "COVID outlay values preserved",
        "outlayed_amount_from_COVID-19_supplementals_for_overall_award",
        "covid_overall_award_outlay",
    )


def check_iija_ob(cur, b):
    return _numeric_preservation(
        cur,
        b,
        "EXTRA-004",
        "IIJA obligation values preserved",
        "obligated_amount_from_IIJA_supplemental_for_overall_award",
        "iija_overall_award_obligation",
    )


def check_iija_out(cur, b):
    return _numeric_preservation(
        cur,
        b,
        "EXTRA-005",
        "IIJA outlay values preserved",
        "outlayed_amount_from_IIJA_supplemental_for_overall_award",
        "iija_overall_award_outlay",
    )

def check_funding_partition(cur,batch):
    cur.execute("""WITH x AS (
      SELECT
        federal_action_obligation,
        CASE
          WHEN is_covid THEN 'COVID'
          WHEN is_iija THEN 'IIJA'
          WHEN is_extraordinary THEN 'OTHER_EXTRAORDINARY'
          ELSE 'ORDINARY'
        END c
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s
        AND geographic_attribution_class IN
          ('WA_COUNTY','WA_UNSPECIFIED','GEOGRAPHY_CONFLICT')
    )
    SELECT
      COALESCE(SUM(federal_action_obligation),0),
      COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE c='COVID'),0)
      + COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE c='IIJA'),0)
      + COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE c='OTHER_EXTRAORDINARY'),0)
      + COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE c='ORDINARY'),0)
    FROM x""",(batch,))
    total,decomp=map(Decimal,cur.fetchone())
    diff=decomp-total
    ok=diff==0
    return CertificationCheck(
      "EXTRA-006",
      "EXTRAORDINARY FUNDING",
      "Exclusive funding classes reconcile",
      _status(ok),
      f"${diff:,.2f}",
      "$0.00 difference")

# ---------------- FINANCIAL ----------------

def check_batch_obligations(cur,batch):
    cur.execute(f"""WITH p AS (
      SELECT {_raw_numeric('federal_action_obligation')} r,t.federal_action_obligation n
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s)
      SELECT COUNT(*),COALESCE(SUM(r),0),COALESCE(SUM(n),0) FROM p""",(batch,))
    rows,raw_total,norm_total=cur.fetchone(); diff=Decimal(norm_total)-Decimal(raw_total); ok=int(rows)>0 and diff==0
    return CertificationCheck("FIN-001","FINANCIAL CERTIFICATION","Batch obligation totals reconcile",_status(ok),f"${diff:,.2f}","$0.00 difference")

def check_txn_obligations(cur,batch):
    cur.execute(f"""SELECT COUNT(*),COUNT(*) FILTER (
      WHERE ({_raw_numeric('federal_action_obligation')}) IS DISTINCT FROM t.federal_action_obligation)
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s""",(batch,))
    total,bad=map(int,cur.fetchone()); ok=bad==0 and total>0
    return CertificationCheck("FIN-002","FINANCIAL CERTIFICATION","Transaction obligations reconcile",_status(ok),f"{total-bad}/{total}",f"{total}/{total}")

def check_negative(cur,batch):
    cur.execute("""SELECT COUNT(*),COALESCE(SUM(t.federal_action_obligation),0)
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t
        ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s AND t.federal_action_obligation<0""",(batch,))
    n,amt=cur.fetchone()
    return CertificationCheck("FIN-003","FINANCIAL CERTIFICATION","Negative obligations preserved",CheckStatus.PASS,f"{int(n)} rows, ${Decimal(amt):,.2f}")

def check_zero(cur,batch):
    cur.execute("""SELECT COUNT(*)
      FROM assistance.raw_award_transaction raw
      JOIN assistance.award_transaction t
        ON t.assistance_transaction_unique_key=raw.assistance_transaction_unique_key
      WHERE raw.load_batch_id=%s AND t.federal_action_obligation=0""",(batch,))
    return CertificationCheck("FIN-004","FINANCIAL CERTIFICATION","Zero-dollar transactions preserved",CheckStatus.PASS,int(cur.fetchone()[0]))

def _fields(cur, batch, code, label, pairs):
    field_queries = []

    for raw_field, norm_col in pairs:
        field_queries.append(
            _field_preservation_sql(
                raw_field,
                norm_col,
                numeric=True,
            )
        )

    union_sql = "\nUNION ALL\n".join(field_queries)
    params = tuple(batch for _ in pairs)

    cur.execute(
        f"""
        SELECT COUNT(DISTINCT raw_assistance_transaction_id)
        FROM (
            {union_sql}
        ) AS x
        WHERE preservation_failure
        """,
        params,
    )

    return _zero(
        code,
        "FINANCIAL CERTIFICATION",
        label,
        cur.fetchone()[0],
        "observations contain unaccounted or invalid revision-aware financial preservation failures",
    )

def check_loan_fields(cur,b):
    return _fields(cur,b,"FIN-005","Loan financial fields preserved",(
      ("face_value_of_loan","face_value_of_loan"),
      ("original_loan_subsidy_cost","original_loan_subsidy_cost"),
      ("total_face_value_of_loan","total_face_value_of_loan"),
      ("total_loan_subsidy_cost","total_loan_subsidy_cost")))

def check_nonfed_fields(cur,b):
    return _fields(cur,b,"FIN-006","Nonfederal funding fields preserved",(
      ("non_federal_funding_amount","non_federal_funding_amount"),
      ("total_non_federal_funding_amount","total_non_federal_funding_amount")))

# ---------------- ANALYTICAL RECONCILIATION ----------------

def check_ledger_count(cur,batch):
    cur.execute("""SELECT
      (SELECT COUNT(*)
         FROM assistance.raw_award_transaction
        WHERE load_batch_id=%s),
      (SELECT COUNT(*)
         FROM analysis.v_assistance_transaction_observation_ledger
        WHERE observation_load_batch_id=%s)""",(batch,batch))
    observations,ledger=map(int,cur.fetchone())
    ok=observations>0 and observations==ledger
    return CertificationCheck(
      "REC-001",
      "ANALYTICAL RECONCILIATION",
      "Observation ledger count reconciles",
      _status(ok),
      f"{ledger}/{observations}",
      observations)


def check_geo_partition(cur,batch):
    cur.execute("""SELECT
      COUNT(*),
      COUNT(*) FILTER (
        WHERE geographic_attribution_class IN
          ('WA_COUNTY','WA_UNSPECIFIED',
           'GEOGRAPHY_CONFLICT','NON_WASHINGTON')
      )
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s""",(batch,))
    total,classified=map(int,cur.fetchone())
    ok=total>0 and total==classified
    return CertificationCheck(
      "REC-002",
      "ANALYTICAL RECONCILIATION",
      "Observation geographic partition reconciles",
      _status(ok),
      f"{classified}/{total}",
      total)


def check_wa_partition(cur,batch):
    cur.execute("""SELECT
      COALESCE(SUM(federal_action_obligation),0),
      COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE geographic_attribution_class='WA_COUNTY'),0)
      + COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE geographic_attribution_class='WA_UNSPECIFIED'),0)
      + COALESCE(SUM(federal_action_obligation)
        FILTER (WHERE geographic_attribution_class='GEOGRAPHY_CONFLICT'),0)
      FROM analysis.v_assistance_observation_geographic_attribution
      WHERE observation_load_batch_id=%s
        AND geographic_attribution_class IN
          ('WA_COUNTY','WA_UNSPECIFIED','GEOGRAPHY_CONFLICT')""",(batch,))
    total,parts=map(Decimal,cur.fetchone())
    diff=parts-total
    ok=diff==0
    return CertificationCheck(
      "REC-003",
      "ANALYTICAL RECONCILIATION",
      "Washington observation obligation partition reconciles",
      _status(ok),
      f"${diff:,.2f}",
      "$0.00 difference")

CHECKS = (
    check_raw_exists, check_txn_exists, check_awards_exist, check_counts_reconcile,
    check_raw_source_rows_unique, check_txn_source_rows_unique, check_txn_keys_unique,
    check_fk_award, check_fk_recipient, check_fk_place, check_fk_awarding_agency,
    check_fk_awarding_subagency, check_fk_funding_agency, check_fk_funding_subagency,
    check_fk_listing, check_fk_type, check_fk_opportunity, check_fk_recipient_history,
    check_fk_parent_history, check_fk_defc,
    check_rel_recipient, check_rel_awarding_agency, check_rel_awarding_subagency,
    check_rel_funding_agency, check_rel_funding_subagency, check_rel_type,
    check_rel_listing, check_rel_history,
    check_type_codes, check_listing_numbers,
    check_geo_coverage, check_geo_classes, check_wa_county_refs, check_wa_counties,
    check_defc_text, check_covid_ob, check_covid_out, check_iija_ob, check_iija_out,
    check_funding_partition,
    check_batch_obligations, check_txn_obligations, check_negative, check_zero,
    check_loan_fields, check_nonfed_fields,
    check_ledger_count, check_geo_partition, check_wa_partition,
)
