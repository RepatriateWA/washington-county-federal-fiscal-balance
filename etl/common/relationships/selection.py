from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TypeVar


T = TypeVar("T")
K = TypeVar("K")


def group_by_key(
    observations: Iterable[T],
    *,
    key: Callable[[T], K],
) -> dict[K, list[T]]:
    """Group observations deterministically by a caller-supplied key."""

    grouped: dict[K, list[T]] = defaultdict(list)

    for observation in observations:
        grouped[key(observation)].append(observation)

    return dict(grouped)


def select_one_per_group(
    observations: Iterable[T],
    *,
    group_key: Callable[[T], K],
    selection_key: Callable[[T], object],
) -> dict[K, T]:
    """
    Select one deterministic observation per group.

    The caller defines all business precedence through selection_key.
    """

    grouped = group_by_key(
        observations,
        key=group_key,
    )

    selections: dict[K, T] = {}

    for group_value in sorted(grouped):
        selections[group_value] = sorted(
            grouped[group_value],
            key=selection_key,
        )[0]

    return selections


def count_distinct_configurations(
    observations: Iterable[T],
    *,
    configuration_key: Callable[[T], object],
) -> int:
    """Count distinct relationship configurations."""

    return len(
        {
            configuration_key(observation)
            for observation in observations
        }
    )