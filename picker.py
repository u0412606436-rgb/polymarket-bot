import anthropic
import json
from config import ANTHROPIC_API_KEY


def pick_top_bets(candidates: list[dict], n: int = 10) -> list[dict]:
    """Use Claude to pick the N smartest low-chance bets, closest end dates first."""
    if not candidates:
        return []

    # Sort by end_date ascending (closest deadline first), then filter out no-date
    dated = [c for c in candidates if c.get("end_date") and str(c["end_date"])[:4].isdigit()]
    dated.sort(key=lambda c: c["end_date"])

    # Take top 80 closest-ending candidates to send to Claude
    pool = dated[:80]

    lines = []
    for i, c in enumerate(pool):
        lines.append(
            f"{i}: market={c['market']!r}, outcome={c['outcome']!r}, "
            f"prob={c['probability_%']}%, volume=${c['volume']:,.0f}, "
            f"liquidity=${c['liquidity']:,.0f}, end={c['end_date']}, "
            f"category={c['category'] or 'unknown'!r}"
        )

    prompt = (
        f"You are an expert prediction market analyst. "
        f"Below are {len(lines)} active Polymarket outcomes with 5–10% probability, sorted by closest end date first.\n\n"
        f"Pick the {n} SMARTEST bets. 'Smart' means:\n"
        f"- The outcome is realistic and could actually happen\n"
        f"- Prefer closer end dates (resolves sooner = faster feedback)\n"
        f"- High volume/liquidity (well-priced, active market)\n"
        f"- Good payout vs true risk\n\n"
        f"Return ONLY a JSON array with exactly {n} objects:\n"
        f'[{{"index": <number>, "reason": "<1 sentence explanation>"}}, ...]\n\n'
        f"Candidates:\n" + "\n".join(lines) +
        "\n\nReturn only valid JSON. No markdown, no extra text."
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    picks = json.loads(text)

    result = []
    for pick in picks[:n]:
        idx = pick["index"]
        if 0 <= idx < len(pool):
            candidate = pool[idx].copy()
            candidate["claude_reason"] = pick.get("reason", "")
            result.append(candidate)

    return result
