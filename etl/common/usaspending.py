"""
Shared USAspending constants and helper functions.

This module centralizes knowledge of USAspending field names so that
individual ETL loaders never hard-code JSON keys.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any


# ----------------------------------------------------------------------
# Raw JSON field names
# ----------------------------------------------------------------------

FIELDS = {

    # Award identifiers
    "AWARD_KEY": "contract_award_unique_key",
    "TRANSACTION_KEY": "contract_transaction_unique_key",
    "PIID": "award_id_piid",
    "PARENT_PIID": "parent_award_id_piid",

    # Award classification
    "AWARD_TYPE_CODE": "award_type_code",
    "AWARD_TYPE": "award_type",

    # Dates
    "ACTION_DATE": "action_date",
    "POP_START": "period_of_performance_start_date",
    "POP_CURRENT_END": "period_of_performance_current_end_date",
    "POP_POTENTIAL_END": "period_of_performance_potential_end_date",
    "ORDERING_END": "ordering_period_end_date",

    # Money
    "OBLIGATION": "federal_action_obligation",
    "CURRENT_TOTAL_VALUE": "current_total_value_of_award",
    "POTENTIAL_TOTAL_VALUE": "potential_total_value_of_award",
    
    "FEDERAL_ACTION_OBLIGATION": "federal_action_obligation",    

    # Codes
    "NAICS": "naics_code",
    "PSC": "product_or_service_code",

    # Descriptions
    "AWARD_DESCRIPTION": "prime_award_base_transaction_description",
    "TRANSACTION_DESCRIPTION": "transaction_description",

    # Transaction attributes
    "MODIFICATION_NUMBER": "modification_number",
    "NAICS_DESCRIPTION": "naics_description",
    "PSC_DESCRIPTION": "product_or_service_code_description",

    




    
}

def get_required(record: dict, field: str) -> str:
    """
    Return a required field.

    Raises ValueError if missing or blank.
    """

    key = FIELDS[field]

    value = record.get(key)

    if value is None:
        raise ValueError(f"Missing required field: {key}")

    value = str(value).strip()

    if value == "":
        raise ValueError(f"Blank required field: {key}")

    return value

def get_optional(record: dict, field: str):
    """
    Return an optional field.

    Blank strings become None.
    """

    key = FIELDS[field]

    value = record.get(key)

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value

def parse_date(value):

    if value in (None, ""):
        return None

    value = str(value).replace("Z", "+00:00")

    if "T" in value:
        return datetime.fromisoformat(value).date()

    return date.fromisoformat(value[:10])

def parse_decimal(value):

    if value in (None, ""):
        return None

    return Decimal(str(value).replace(",", ""))

