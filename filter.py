import json
from datetime import date
from config import PROB_MIN, PROB_MAX

TODAY = date.today().isoformat()  # e.g. "2026-03-14"


def _parse_field(val):
    """Fields from Gamma API may be JSON strings or already lists."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            return []
    return val or []


def extract_matching_outcomes(markets: list[dict]) -> list[dict]:
    rows = []

    for market in markets:
        outcomes   = _parse_field(market.get("outcomes", []))
        prices_raw = _parse_field(market.get("outcomePrices", []))

        if not outcomes or not prices_raw or len(outcomes) != len(prices_raw):
            continue

        # Parse token IDs properly (may be a JSON string)
        token_ids = _parse_field(market.get("clobTokenIds", []))

        # Get and validate end date — skip markets already expired
        end_date = (market.get("endDateIso") or market.get("endDate", "") or "")[:10]
        if end_date and end_date < TODAY:
            continue

        for i, outcome_label in enumerate(outcomes):
            try:
                prob = float(prices_raw[i])
            except (ValueError, IndexError):
                continue

            if PROB_MIN <= prob <= PROB_MAX:
                events = market.get("events", [])
                if events and events[0].get("category"):
                    category = events[0]["category"]
                else:
                    category = market.get("category", "")

                token_id = token_ids[i] if i < len(token_ids) else ""

                rows.append({
                    "market":        market.get("question", ""),
                    "category":      category,
                    "end_date":      end_date,
                    "outcome":       outcome_label,
                    "probability_%": round(prob * 100, 2),
                    "volume":        round(float(market.get("volume") or 0), 2),
                    "liquidity":     round(float(market.get("liquidity") or 0), 2),
                    "_token_id":     token_id,
                })

    rows.sort(key=lambda r: r["probability_%"])
    return rows
