"""
Database-query helpers for procurement certification.
"""

from __future__ import annotations

from typing import Any


def scalar_query(
    cur,
    sql: str,
    parameters: tuple[Any, ...],
) -> Any:
    """
    Execute a query expected to return one scalar value.
    """
    cur.execute(sql, parameters)
    row = cur.fetchone()

    if row is None:
        raise ValueError(
            "Certification query returned no result row."
        )

    return row[0]