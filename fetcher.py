import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import GAMMA_API, PAGE_LIMIT


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_all_active_markets() -> list[dict]:
    url = f"{GAMMA_API}/markets"
    all_markets = []
    offset = 0
    session = _make_session()

    for attempt in range(1, 4):
        try:
            while True:
                params = {
                    "active": "true",
                    "closed": "false",
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                }
                resp = session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                batch = resp.json()

                if not batch:
                    break

                all_markets.extend(batch)

                if len(batch) < PAGE_LIMIT:
                    break

                offset += PAGE_LIMIT

            return all_markets

        except requests.exceptions.ConnectionError as e:
            print(f"[fetcher] Connection error (attempt {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(5 * attempt)
                offset = 0
                all_markets = []
            else:
                raise
