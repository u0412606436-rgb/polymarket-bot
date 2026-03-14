import requests
from config import GAMMA_API, PAGE_LIMIT


def fetch_all_active_markets() -> list[dict]:
    url = f"{GAMMA_API}/markets"
    all_markets = []
    offset = 0

    while True:
        params = {
            "active": "true",
            "closed": "false",
            "limit": PAGE_LIMIT,
            "offset": offset,
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break

        all_markets.extend(batch)

        if len(batch) < PAGE_LIMIT:
            break

        offset += PAGE_LIMIT

    return all_markets
