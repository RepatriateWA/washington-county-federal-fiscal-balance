from __future__ import annotations

import json
import urllib.error
import urllib.request


URL = (
    "https://api.usaspending.gov/"
    "api/v2/search/spending_by_transaction/"
)

payload = {
    "filters": {
        "time_period": [
            {
                "start_date": "2019-10-01",
                "end_date": "2020-09-30",
            }
        ],
        "award_type_codes": ["A", "B", "C", "D"],
        "place_of_performance_locations": [
            {
                "country": "USA",
                "state": "WA",
            }
        ],
    },
    "fields": [
    "internal_id",
    "generated_internal_id",
    "Award ID",
    "Action Date",
    "Mod",
    "Transaction Amount",
    "Transaction Description",
    "Recipient Name",
    "Recipient UEI",
    "recipient_id",
    "pop_state_code",
    "naics_code",
    "product_or_service_code",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Funding Agency",
    "Funding Sub Agency",
    "def_codes",
    ],
    "page": 1,
    "limit": 5,
    "sort": "internal_id",
    "order": "asc",
    "subawards": False,
}


data = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    URL,
    data=data,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "WCFFBP-USAspending-Acquisition/1.0",
    },
    method="POST",
)


try:
    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

except urllib.error.HTTPError as exc:
    print(f"HTTP ERROR: {exc.code}")
    print(
        exc.read().decode(
            "utf-8",
            errors="replace",
        )
    )
    raise


print("=" * 88)
print("USASPENDING PAGED TRANSACTION TEST")
print("=" * 88)
print()

print(json.dumps(result, indent=2))