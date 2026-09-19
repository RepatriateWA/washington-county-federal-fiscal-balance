from pathlib import Path
import pandas as pd


DISCOVERY_MANIFEST = Path(
    "data/raw/cms/medicare_advantage/validation/"
    "source_discovery/cms_ma_partc_source_discovery_manifest.csv"
)

OUTPUT_DIR = Path(
    "data/raw/cms/medicare_advantage/validation/"
    "source_acquisition"
)

SELECTION_MANIFEST = (
    OUTPUT_DIR
    / "cms_ma_partc_artifact_selection_manifest.csv"
)


def split_pipe(value) -> list[str]:
    if pd.isna(value):
        return []

    return [
        item.strip()
        for item in str(value).split("|")
        if item.strip()
    ]


def select_artifact(row: pd.Series) -> dict:
    source_type = str(row["source_type"])

    urls = split_pipe(row["artifact_urls"])
    types = split_pipe(row["artifact_types"])
    texts = split_pipe(row["artifact_link_texts"])

    if not (
        len(urls)
        == len(types)
        == len(texts)
    ):
        return {
            "selection_status": "FAIL",
            "selected_url": "",
            "selected_type": "",
            "selected_link_text": "",
            "selection_reason": (
                "Artifact URL/type/text cardinalities differ"
            ),
            "candidate_count": 0,
        }

    artifacts = [
        {
            "url": url,
            "type": artifact_type.upper(),
            "text": text,
        }
        for url, artifact_type, text
        in zip(urls, types, texts)
    ]

    candidates = []

    for artifact in artifacts:
        url_lower = artifact["url"].lower()
        text_lower = artifact["text"].lower()

        if artifact["type"] != "ZIP":
            continue

        if source_type == "CPSC":
            cpsc_identified = (
                "cpsc" in text_lower
                or "cpsc" in url_lower
                or "monthly enrollment by contract" in text_lower
                or "monthly-enrollment-contract" in url_lower
            )

            if cpsc_identified:
                candidates.append(artifact)

        elif source_type == "SCC_SCP":
            # CMS naming varies across vintages.  The required
            # acquisition artifact is the complete/full SCC file,
            # never the explicitly abridged/alternate version.
            scc_identified = (
                "state/county/contract" in text_lower
                or "statecountycontract" in text_lower
                or "scc" in text_lower
                or "scc" in url_lower
            )

            abridged_identified = (
                "abridged" in text_lower
                or "abridged" in url_lower
                or "_alt_" in text_lower
                or "_alt_" in url_lower
                or "-alt-" in text_lower
                or "-alt-" in url_lower
                or "maalt" in url_lower
            )

            if (
                scc_identified
                and not abridged_identified
            ):
                candidates.append(artifact)

        elif source_type == "SNP":
            if (
                "snp" in text_lower
                or "snp" in url_lower
            ):
                candidates.append(artifact)

        elif source_type == "PLAN_PAYMENT":
            semantic_text = (
                f"{text_lower} {url_lower}"
            )

            year = int(float(row["payment_year"]))
            year_text = str(year)

            payment_identified = any(
                token in semantic_text
                for token in (
                    "plan payment",
                    "plan-payment",
                    "plan_payment",
                    "payment data",
                    "payment-data",
                    "payment_data",
                    "paymentdata",
                )
            )

            if (
                year_text in semantic_text
                and payment_identified
            ):
                candidates.append(artifact)

        else:
            return {
                "selection_status": "FAIL",
                "selected_url": "",
                "selected_type": "",
                "selected_link_text": "",
                "selection_reason": (
                    f"Unsupported source_type: {source_type}"
                ),
                "candidate_count": 0,
            }

    if len(candidates) != 1:
        return {
            "selection_status": "FAIL",
            "selected_url": "",
            "selected_type": "",
            "selected_link_text": "",
            "selection_reason": (
                "Expected exactly one qualifying artifact; "
                f"found {len(candidates)}"
            ),
            "candidate_count": len(candidates),
        }

    selected = candidates[0]

    if source_type == "SCC_SCP":
        reason = (
            "Selected CMS Full-version state/county/contract "
            "enrollment ZIP; abridged artifact excluded"
        )
    elif source_type == "CPSC":
        reason = (
            "Selected CMS CPSC monthly enrollment ZIP"
        )
    elif source_type == "SNP":
        reason = (
            "Selected CMS SNP comprehensive-report ZIP"
        )
    else:
        reason = (
            "Selected year-specific CMS Plan Payment ZIP"
        )

    return {
        "selection_status": "PASS",
        "selected_url": selected["url"],
        "selected_type": selected["type"],
        "selected_link_text": selected["text"],
        "selection_reason": reason,
        "candidate_count": 1,
    }


def main() -> int:
    df = pd.read_csv(DISCOVERY_MANIFEST)

    required_columns = {
        "source_type",
        "period",
        "payment_year",
        "discovery_status",
        "artifact_urls",
        "artifact_types",
        "artifact_link_texts",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise RuntimeError(
            "Discovery manifest missing columns: "
            + ", ".join(sorted(missing))
        )

    if len(df) != 371:
        raise RuntimeError(
            f"Expected 371 discovery rows; found {len(df)}"
        )

    results = []

    for _, row in df.iterrows():
        selection = select_artifact(row)

        results.append(
            {
                "source_type": row["source_type"],
                "period": row["period"],
                "payment_year": row["payment_year"],
                "discovery_status": row["discovery_status"],
                **selection,
            }
        )

    output = pd.DataFrame(results)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        SELECTION_MANIFEST,
        index=False,
    )

    passed = int(
        (output["selection_status"] == "PASS").sum()
    )

    failed = int(
        (output["selection_status"] == "FAIL").sum()
    )

    print("=" * 80)
    print(
        "CMS MEDICARE ADVANTAGE PART C — "
        "ACQUISITION ARTIFACT SELECTION"
    )
    print("=" * 80)
    print()
    print(f"Required source slots: {len(output)}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    print()

    family_summary = (
        output.groupby("source_type")
        ["selection_status"]
        .value_counts()
        .unstack(fill_value=0)
    )

    print("BY SOURCE FAMILY")
    print(family_summary.to_string())
    print()

    failures = output[
        output["selection_status"] != "PASS"
    ]

    if not failures.empty:
        print("FAILURES")
        print(
            failures[
                [
                    "source_type",
                    "period",
                    "payment_year",
                    "candidate_count",
                    "selection_reason",
                ]
            ].to_string(index=False)
        )
        print()

    if passed == 371 and failed == 0:
        print(
            "RESULT: ALL 371 REQUIRED SOURCE SLOTS "
            "RESOLVE TO EXACTLY ONE ACQUISITION ARTIFACT"
        )
        return 0

    print(
        "RESULT: ARTIFACT SELECTION REQUIRES REVIEW"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())