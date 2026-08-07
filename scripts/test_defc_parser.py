"""Contract tests for the reusable DEFC parser."""

from __future__ import annotations

from etl.common.extraordinary_funding.defc_parser import (
    parse_defc_value,
)


def assert_codes(
    raw_value: str | None,
    expected_codes: list[str],
) -> None:
    """Assert the parsed DEFC-code sequence."""

    result = parse_defc_value(
        raw_value
    )

    actual_codes = [
        observation.code
        for observation in result.observations
    ]

    if actual_codes != expected_codes:
        raise AssertionError(
            f"Expected codes {expected_codes!r}; "
            f"found {actual_codes!r}."
        )

    if result.unparsed_segments:
        raise AssertionError(
            "Unexpected unparsed segments: "
            f"{result.unparsed_segments!r}"
        )


def main() -> None:
    assert_codes(
        None,
        [],
    )

    assert_codes(
        "",
        [],
    )

    assert_codes(
        "Q: Not Designated "
        "Nonemergency/Emergency/Disaster/"
        "Wildfire Suppression",
        ["Q"],
    )

    assert_codes(
        "N: Emergency P.L. 116-136;"
        "Q: Not Designated "
        "Nonemergency/Emergency/Disaster/"
        "Wildfire Suppression;"
        "V: Non-emergency P.L. 117-2",
        ["N", "Q", "V"],
    )

    result = parse_defc_value(
        "O: Non-emergency P.L. 116-136|"
        "Non-emergency P.L. 116-139|"
        "Non-emergency P.L. 116-260|"
        "Non-emergency P.L. 117-2"
    )

    if len(result.observations) != 1:
        raise AssertionError(
            "Expected one O-code observation."
        )

    observation = result.observations[0]

    if observation.code != "O":
        raise AssertionError(
            f"Expected O; found {observation.code!r}."
        )

    expected_description = (
        "Non-emergency P.L. 116-136|"
        "Non-emergency P.L. 116-139|"
        "Non-emergency P.L. 116-260|"
        "Non-emergency P.L. 117-2"
    )

    if observation.description != expected_description:
        raise AssertionError(
            "Pipe-connected O-code description was not preserved."
        )

    mixed = parse_defc_value(
        "N: Emergency P.L. 116-136|"
        "V: Non-emergency P.L. 117-2"
    )

    if [
        item.code
        for item in mixed.observations
    ] != ["N", "V"]:
        raise AssertionError(
            "Pipe-delimited code observations were not split."
        )

    duplicate = parse_defc_value(
        "N: Emergency P.L. 116-136;"
        "N: Emergency P.L. 116-136"
    )

    if len(duplicate.observations) != 1:
        raise AssertionError(
            "Duplicate code within one source value was not collapsed."
        )

    malformed = parse_defc_value(
        "N: Emergency P.L. 116-136;"
        "unparseable segment"
    )

    if malformed.unparsed_segments != (
        "unparseable segment",
    ):
        raise AssertionError(
            "Malformed segment was not preserved."
        )

    print("DEFC parser contract test passed.")
    print()
    print("Verified:")
    print("  null and blank handling")
    print("  semicolon-delimited codes")
    print("  pipe-delimited codes")
    print("  embedded pipes in descriptions")
    print("  duplicate-code suppression")
    print("  malformed-segment preservation")


if __name__ == "__main__":
    main()