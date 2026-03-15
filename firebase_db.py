import threading
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

_db = None
_lock = threading.Lock()


def _init():
    global _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        if not firebase_admin._apps:
            # Railway: set FIREBASE_CREDENTIALS env var to the full JSON string
            cred_json = os.environ.get("FIREBASE_CREDENTIALS", "").strip()
            if cred_json:
                cred = credentials.Certificate(json.loads(cred_json))
            else:
                # Local: put your downloaded key file here
                cred = credentials.Certificate(
                    os.path.join(os.path.dirname(__file__), "firebase_key.json")
                )
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


# ── Budget ────────────────────────────────────────────────
def load_budget(default: dict) -> dict:
    db  = _init()
    doc = db.collection("state").document("budget").get()
    return doc.to_dict() if doc.exists else default


def save_budget(data: dict):
    _init().collection("state").document("budget").set(data)


# ── Bets ──────────────────────────────────────────────────
def load_bets() -> list:
    db   = _init()
    docs = db.collection("bets").order_by("time").stream()
    return [d.to_dict() for d in docs]


def add_bet(bet: dict):
    """Add a new bet. Uses token_id as document ID to prevent duplicates."""
    _init().collection("bets").document(bet["token_id"]).set(bet)


def update_bet(token_id: str, fields: dict):
    _init().collection("bets").document(token_id).update(fields)


def reset_bets():
    db   = _init()
    docs = db.collection("bets").stream()
    for d in docs:
        d.reference.delete()
