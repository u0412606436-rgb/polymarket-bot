import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, render_template
from fetcher import fetch_all_active_markets
from filter import extract_matching_outcomes
import threading, time, random, requests as req

app = Flask(__name__)

_state = {
    "running":          False,
    "last_run":         None,
    "next_run":         None,
    "status":           "stopped",
    "markets_count":    0,
    "candidates_count": 0,
    "last_error":       None,
}

_loop_thread = None
_stop_event  = threading.Event()


# ── Budget helpers ─────────────────────────────────────────
def _default_budget():
    from config import VIRTUAL_BUDGET
    return {"total": VIRTUAL_BUDGET, "balance": VIRTUAL_BUDGET,
            "locked": 0.0, "won": 0.0, "lost": 0.0, "bets_placed": 0}

def get_budget():
    from firebase_db import load_budget
    return load_budget(_default_budget())

def save_budget(b):
    from firebase_db import save_budget
    save_budget(b)

def get_bets():
    from firebase_db import load_bets
    return load_bets()


# ── Place a virtual bet ────────────────────────────────────
def place_virtual_bet(bet: dict, budget: dict) -> bool:
    if budget["balance"] < bet["bet_size"]:
        return False
    budget["balance"]     = round(budget["balance"] - bet["bet_size"], 2)
    budget["locked"]      = round(budget["locked"]  + bet["bet_size"], 2)
    budget["bets_placed"] = budget.get("bets_placed", 0) + 1
    return True


# ── Resolve pending bets ───────────────────────────────────
def resolve_bets():
    from firebase_db import update_bet
    bets   = get_bets()
    budget = get_budget()
    changed = False

    for bet in bets:
        if bet.get("status") != "pending":
            continue
        try:
            r = req.get(
                "https://clob.polymarket.com/midpoints",
                params={"token_id": bet["token_id"]},
                timeout=10
            )
            if r.status_code != 200:
                continue
            data  = r.json()
            price = float(data.get("mid", bet["probability"] / 100))
            now   = time.strftime("%Y-%m-%d %H:%M:%S")

            if price >= 0.95:
                payout = round(bet["bet_size"] * bet["payout_x"], 2)
                fields = {"status": "win", "resolved_at": now,
                          "current_prob": round(price * 100, 2),
                          "checked_at": now, "payout_received": payout}
                update_bet(bet["token_id"], fields)
                budget["locked"]  = round(budget["locked"]  - bet["bet_size"], 2)
                budget["balance"] = round(budget["balance"] + payout, 2)
                budget["won"]     = round(budget["won"]     + payout, 2)
                changed = True
                print(f"[resolve] WIN  +${payout}  {bet['market'][:50]}")

            elif price <= 0.05:
                fields = {"status": "loss", "resolved_at": now,
                          "current_prob": round(price * 100, 2),
                          "checked_at": now, "payout_received": 0}
                update_bet(bet["token_id"], fields)
                budget["locked"] = round(budget["locked"] - bet["bet_size"], 2)
                budget["lost"]   = round(budget["lost"]   + bet["bet_size"], 2)
                changed = True
                print(f"[resolve] LOSS -${bet['bet_size']}  {bet['market'][:50]}")

            else:
                fields = {"current_prob": round(price * 100, 2), "checked_at": now}
                update_bet(bet["token_id"], fields)

        except Exception as e:
            print(f"[resolve error] {e}")

    if changed:
        save_budget(budget)


# ── One betting cycle ──────────────────────────────────────
def run_cycle():
    from config import BET_SIZE_MIN, BET_SIZE_MAX
    from firebase_db import add_bet
    _state["status"]     = "running"
    _state["last_error"] = None
    print("[bot] Cycle started")

    try:
        try:
            markets = fetch_all_active_markets()
        except Exception as net_err:
            print(f"[bot] Network unavailable, skipping cycle: {net_err}")
            _state["status"]     = "idle"
            _state["last_error"] = f"Network error (will retry next cycle): {net_err}"
            return
        _state["markets_count"] = len(markets)
        print(f"[bot] {len(markets)} markets fetched")

        candidates = extract_matching_outcomes(markets)
        _state["candidates_count"] = len(candidates)
        print(f"[bot] {len(candidates)} candidates (5-10%)")

        budget = get_budget()
        if budget["balance"] < BET_SIZE_MIN:
            print("[bot] Balance depleted")
            _state["status"] = "idle"
            return

        if not candidates:
            _state["status"] = "idle"
            return

        from picker import pick_top_bets
        picks = pick_top_bets(candidates, n=10)
        print(f"[bot] Claude picked {len(picks)} bets")

        existing_keys = {b["token_id"] for b in get_bets()}
        added = 0

        for pick in picks:
            if budget["balance"] < BET_SIZE_MIN:
                print("[bot] Balance reached 0")
                break

            token_id = pick.get("_token_id")
            if not token_id or token_id in existing_keys:
                continue

            bet_size = round(random.uniform(BET_SIZE_MIN, min(BET_SIZE_MAX, budget["balance"])), 2)
            prob     = pick["probability_%"] / 100.0
            payout_x = round(1.0 / prob, 2) if prob > 0 else 0

            bet = {
                "token_id":        token_id,
                "market":          pick["market"],
                "outcome":         pick["outcome"],
                "category":        pick.get("category", ""),
                "probability":     pick["probability_%"],
                "payout_x":        payout_x,
                "bet_size":        bet_size,
                "potential":       round(bet_size * payout_x, 2),
                "end_date":        (pick.get("end_date") or "")[:10],
                "time":            time.strftime("%Y-%m-%d %H:%M:%S"),
                "status":          "pending",
                "current_prob":    None,
                "checked_at":      None,
                "resolved_at":     None,
                "payout_received": None,
                "claude_reason":   pick.get("claude_reason", ""),
            }

            if place_virtual_bet(bet, budget):
                add_bet(bet)
                existing_keys.add(token_id)
                added += 1
                print(f"[bot] ${bet_size} on {pick['outcome']} "
                      f"({pick['probability_%']}%) ends {bet['end_date']}")

        save_budget(budget)
        print(f"[bot] {added} bets placed. Balance: ${budget['balance']}")
        _state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["status"]   = "idle"

    except Exception as e:
        _state["status"]     = "error"
        _state["last_error"] = str(e)
        print(f"[bot error] {e}")


# ── Main loop ──────────────────────────────────────────────
def auto_loop(interval_seconds):
    while not _stop_event.is_set():
        run_cycle()
        resolve_bets()
        next_ts = time.time() + interval_seconds
        _state["next_run"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(next_ts))
        _stop_event.wait(interval_seconds)
    _state["status"]   = "stopped"
    _state["next_run"] = None


# ── Routes ─────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    return jsonify({**_state, "loop_alive": _loop_thread is not None and _loop_thread.is_alive()})

@app.route("/api/start", methods=["POST"])
def api_start():
    global _loop_thread, _stop_event
    if _loop_thread and _loop_thread.is_alive():
        return jsonify({"status": "already_running"})
    _stop_event  = threading.Event()
    interval     = int(os.environ.get("REFRESH_INTERVAL", 3600))
    _loop_thread = threading.Thread(target=auto_loop, args=(interval,), daemon=True)
    _loop_thread.start()
    return jsonify({"status": "started"})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    _stop_event.set()
    _state["status"]   = "stopped"
    _state["next_run"] = None
    return jsonify({"status": "stopped"})

@app.route("/api/bets")
def api_bets():
    return jsonify(get_bets())

@app.route("/api/budget")
def api_budget():
    return jsonify(get_budget())

@app.route("/api/resolve", methods=["POST"])
def api_resolve():
    threading.Thread(target=resolve_bets, daemon=True).start()
    return jsonify({"status": "checking"})

@app.route("/api/ping")
def api_ping():
    import socket
    try:
        socket.getaddrinfo("gamma-api.polymarket.com", 443)
        return jsonify({"dns": "ok"})
    except Exception as e:
        return jsonify({"dns": "fail", "error": str(e)})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    from firebase_db import reset_bets
    save_budget(_default_budget())
    reset_bets()
    _state["last_run"] = None
    _state["next_run"] = None
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Polymarket AI Bot — http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
