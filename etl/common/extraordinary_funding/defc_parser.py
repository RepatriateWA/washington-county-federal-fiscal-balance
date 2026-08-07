"""Reusable parser for USAspending Disaster Emergency Fund Codes."""

from __future__ import annotations

import re
from dataclasses import dataclass


SEGMENT_SPLITTER = re.compile(
    r";+|[|](?=[A-Za-z0-9]+\s*:)"
)

CODE_DESCRIPTION_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9]+)\s*:\s*(.*?)\s*$"
)


@dataclass(frozen=True)
class DefcObservation:
    """One parsed DEFC code-description observation."""

    code: str
    description: str


@dataclass(frozen=True)
class DefcParseResult:
    """Complete parse result for one raw DEFC source value."""

    observations: tuple[DefcObservation, ...]
    unparsed_segments: tuple[str, ...]


def parse_defc_value(
    raw_value: str | None,
) -> DefcParseResult:
    """
    Parse one USAspending DEFC source value.

    Semicolons always separate code-description observations.

    Pipes separate observations only when followed by another
    DEFC code and colon. Pipes inside a single code's description
    are preserved.
    """

    if raw_value is None:
        return DefcParseResult(
            observations=(),
            unparsed_segments=(),
        )

    text = raw_value.strip()

    if not text:
        return DefcParseResult(
            observations=(),
            unparsed_segments=(),
        )

    observations: list[DefcObservation] = []
    unparsed_segments: list[str] = []
    observed_codes: set[str] = set()

    for segment in SEGMENT_SPLITTER.split(text):
        cleaned_segment = segment.strip()

        if not cleaned_segment:
            continue

        match = CODE_DESCRIPTION_PATTERN.match(
            cleaned_segment
        )

        if match is None:
            unparsed_segments.append(
                cleaned_segment
            )
            continue

        code = match.group(1).upper()
        description = match.group(2).strip()

        # A code is represented at most once within one source value.
        if code in observed_codes:
            continue

        observed_codes.add(code)

        observations.append(
            DefcObservation(
                code=code,
                description=description,
            )
        )

    return DefcParseResult(
        observations=tuple(observations),
        unparsed_segments=tuple(
            unparsed_segments
        ),
    )