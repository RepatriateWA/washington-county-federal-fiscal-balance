"""Contract tests for the shared recipient identity engine."""

from __future__ import annotations

from etl.common.identity.exceptions import (
    UnsupportedRecipientIdentityError,
)
from etl.common.identity.placeholders import (
    RecipientSourceCondition,
)
from etl.common.identity.recipient_identity import (
    RecipientIdentityInput,
    RecipientIdentityType,
    classify_recipient_identity,
)


def main() -> None:
    uei = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="University of Washington",
            recipient_uei="wa39fk22jpq2",
        )
    )

    if uei.identity_key != "UEI:WA39FK22JPQ2":
        raise AssertionError(
            f"Unexpected UEI key: {uei.identity_key!r}"
        )

    if uei.identity_type != RecipientIdentityType.UEI:
        raise AssertionError("UEI identity type was not assigned.")

    first_fingerprint = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="  Example   Farm LLC ",
            recipient_country_code="US",
            recipient_state_code="WA",
            recipient_city_name="Prosser",
            recipient_zip_code="99350",
            recipient_address_line_1="100 Main Street",
            business_types_code="Q",
        )
    )

    second_fingerprint = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="EXAMPLE FARM LLC",
            recipient_country_code="us",
            recipient_state_code="wa",
            recipient_city_name="PROSSER",
            recipient_zip_code="99350",
            recipient_address_line_1="100   MAIN STREET",
            business_types_code="q",
        )
    )

    if (
        first_fingerprint.identity_key
        != second_fingerprint.identity_key
    ):
        raise AssertionError(
            "Equivalent normalized observations produced "
            "different fingerprints."
        )

    if (
        first_fingerprint.identity_type
        != RecipientIdentityType.NAME_FINGERPRINT
    ):
        raise AssertionError(
            "Named no-UEI identity type was not assigned."
        )

    changed_address = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="Example Farm LLC",
            recipient_country_code="US",
            recipient_state_code="WA",
            recipient_city_name="Prosser",
            recipient_zip_code="99350",
            recipient_address_line_1="200 Main Street",
            business_types_code="Q",
        )
    )

    if (
        changed_address.identity_key
        == first_fingerprint.identity_key
    ):
        raise AssertionError(
            "Materially different identity attributes produced "
            "the same fingerprint."
        )

    pii = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="redacted due to pii",
            recipient_uei="SHOULDNOTBEUSED",
        )
    )

    if pii.identity_key != "SOURCE:PII_REDACTED":
        raise AssertionError(
            "PII source condition was not recognized."
        )

    if (
        pii.source_condition
        != RecipientSourceCondition.PII_REDACTED
    ):
        raise AssertionError(
            "PII source-condition enum was not assigned."
        )

    multiple = classify_recipient_identity(
        RecipientIdentityInput(
            recipient_name="MULTIPLE RECIPIENTS",
        )
    )

    if (
        multiple.identity_key
        != "SOURCE:MULTIPLE_RECIPIENTS"
    ):
        raise AssertionError(
            "Multiple-recipient condition was not recognized."
        )

    try:
        classify_recipient_identity(
            RecipientIdentityInput(
                recipient_name="   ",
            )
        )
    except UnsupportedRecipientIdentityError:
        pass
    else:
        raise AssertionError(
            "Blank recipient names should be rejected."
        )

    print("Shared recipient identity contract test passed.")
    print()
    print("Verified:")
    print("  UEI normalization and precedence")
    print("  deterministic name fingerprints")
    print("  comparison-text normalization")
    print("  material attribute sensitivity")
    print("  PII-redacted source conditions")
    print("  multiple-recipient source conditions")
    print("  blank-name rejection")


if __name__ == "__main__":
    main()