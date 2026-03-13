import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import (
    USERS_FILE,
    ORDERS_FILE,
    DRINKS_FILE,
    ESP_QUEUE_FILE,
    ESP_DONE_FILE,
    ETA_ORDER_OVERHEAD_SEC,
    ETA_SECONDS_PER_DRINK,
    ESP_PREP_SECONDS,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def estimate_order_seconds(order: dict) -> int:
    """Explainable ETA model used for queue + ESP display."""
    total_qty = 0
    items = order.get("items") or []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                try:
                    total_qty += int(it.get("quantity", 1))
                except Exception:
                    total_qty += 1
    if total_qty <= 0:
        total_qty = 1
    return int(ETA_ORDER_OVERHEAD_SEC + (total_qty * ETA_SECONDS_PER_DRINK))


def _remaining_seconds_for_order(order: dict) -> int:
    """Remaining seconds for an active order.

    If In Progress and has startedAt, subtract elapsed time.
    Otherwise return full estimated seconds.
    """
    est = int(order.get("estSeconds") or estimate_order_seconds(order))
    status = order.get("status")
    if status == "In Progress":
        started_at = order.get("startedAt")
        if started_at:
            try:
                started_dt = datetime.fromisoformat(str(started_at))
                # Ensure tz-aware
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
                elapsed = int((_utc_now() - started_dt).total_seconds())
                return max(1, est - elapsed)
            except Exception:
                pass
    return max(0, est)


def _read_json(path, default=None) -> Any:
    """
    Read JSON safely.
    Returns `default` if file missing/empty/bad.
    """
    try:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return default
        return json.loads(raw)
    except Exception:
        return default


def _write_json(path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


# -------------------------
# Users
# -------------------------

def load_users() -> Dict[str, str]:
    data = _read_json(USERS_FILE, default={})
    return data if isinstance(data, dict) else {}


def save_users(users: Dict[str, str]):
    _write_json(USERS_FILE, users)


# -------------------------
# Orders
# -------------------------

def load_orders() -> List[dict]:
    data = _read_json(ORDERS_FILE, default=[])
    return data if isinstance(data, list) else []


def save_orders(orders: List[dict]):
    _write_json(ORDERS_FILE, orders)


# -------------------------
# Drinks
# -------------------------

def load_drinks() -> List[dict]:
    data = _read_json(DRINKS_FILE, default=[])
    return data if isinstance(data, list) else []


def ensure_drinks_file():
    """Create drinks.json if missing/empty (starter list)."""
    if DRINKS_FILE.exists():
        raw = DRINKS_FILE.read_text(encoding="utf-8").strip()
        if raw:
            return

    starter = [
        {"id": "amber_storm", "name": "Amber Storm", "calories": 104, "ingredients": ["Coca-Cola", "Ginger Ale"]},
        {"id": "classic_fusion", "name": "Classic Fusion", "calories": 76, "ingredients": ["Water", "Lemonade"]},
        {"id": "chaos_punch", "name": "Chaos Punch", "calories": 204, "ingredients": ["Coca-Cola", "Red Bull"]},
        {"id": "crystal_chill", "name": "Crystal Chill", "calories": 56, "ingredients": ["Water", "Sprite"]},
        {"id": "cola_spark", "name": "Cola Spark", "calories": 81, "ingredients": ["Coca-Cola", "Sprite"]},
        {"id": "dark_amber", "name": "Dark Amber", "calories": 65, "ingredients": ["Coca-Cola", "Ginger Ale"]},
        {"id": "voltage_fizz", "name": "Voltage Fizz", "calories": 117, "ingredients": ["Red Bull", "Sprite"]},
        {"id": "golden_breeze", "name": "Golden Breeze", "calories": 87, "ingredients": ["Lemonade", "Ginger Ale", "Water"]},
        {"id": "energy_sunrise", "name": "Energy Sunrise", "calories": 180, "ingredients": ["Red Bull", "Lemonade"]},
        {"id": "citrus_cloud", "name": "Citrus Cloud", "calories": 95, "ingredients": ["Sprite", "Lemonade"]},
        {"id": "citrus_shine", "name": "Citrus Shine", "calories": 90, "ingredients": ["Lemonade", "Sprite", "Water"]},
        {"id": "sparking_citrus", "name": "Sparking Citrus", "calories": 102, "ingredients": ["Sprite", "Lemonade", "Ginger Ale"]},
        {"id": "sunset_fizz", "name": "Sunset Fizz", "calories": 120, "ingredients": ["Ginger Ale", "Lemonade"]},
        {"id": "tropical_charge", "name": "Tropical Charge", "calories": 160, "ingredients": ["Red Bull", "Sprite", "Lemonade"]},

        # Bases
        {"id": "base_water", "name": "Water", "calories": 0},
        {"id": "base_lemonade", "name": "Lemonade", "calories": 150},
        {"id": "base_coca_cola", "name": "Coca-Cola", "calories": 140},
        {"id": "base_sprite", "name": "Sprite", "calories": 140},
        {"id": "base_ginger_ale", "name": "Ginger Ale", "calories": 120},
        {"id": "base_red_bull", "name": "Red Bull", "calories": 110},
    ]

    _write_json(DRINKS_FILE, starter)


# -------------------------
# ESP queue (polling)
# -------------------------

def load_esp_queue() -> List[dict]:
    data = _read_json(ESP_QUEUE_FILE, default=[])
    return data if isinstance(data, list) else []


def save_esp_queue(queue: List[dict]):
    _write_json(ESP_QUEUE_FILE, queue)


def enqueue_esp_order(order: dict):
    # Store estimation fields once at enqueue-time (used for UI + queue ETA)
    if "estSeconds" not in order:
        order["estSeconds"] = estimate_order_seconds(order)
    queue = load_esp_queue()
    queue.append(order)
    save_esp_queue(queue)


def claim_next_Pending_order() -> dict | None:
    """Return the oldest Pending order and mark it In Progress."""
    queue = load_esp_queue()
    for o in queue:
        if o.get("status") == "Pending":
            o["status"] = "In Progress"
            save_esp_queue(queue)
            return o
    return None


def mark_order_complete(order_id: str) -> bool:
    queue = load_esp_queue()
    for o in queue:
        if o.get("id") == order_id:
            o["status"] = "complete"
            save_esp_queue(queue)
            return True
    return False


def load_esp_done() -> List[dict]:
    data = _read_json(ESP_DONE_FILE, default=[])
    return data if isinstance(data, list) else []


def save_esp_done(done: List[dict]):
    _write_json(ESP_DONE_FILE, done)


def get_active_order_for_esp() -> dict | None:
    """
    Returns the current In Progress order if one exists.
    Otherwise, claims the oldest Pending order by marking it In Progress.
    """
    queue = load_esp_queue()
    for o in queue:
        if o.get("status") == "In Progress":
            return o
    for o in queue:
        if o.get("status") == "Pending":
            o["status"] = "In Progress"
            # Add startedAt for remaining-time estimation
            o.setdefault("startedAt", _utc_now_iso())
            o.setdefault("estSeconds", estimate_order_seconds(o))
            save_esp_queue(queue)
            return o
    return None


def complete_and_archive_order(order_id: str) -> bool:
    """Advance a multi-item order OR complete it.

    ESP calls /api/esp/complete after finishing ONE drink unit.

    Behavior:
      - If the active order still has remaining items/quantity, we decrement the first item's quantity
        (or pop it) and KEEP the order in the queue as In Progress.
      - If nothing remains, we mark the order complete, remove it from the queue,
        and archive into esp_done.json.

    Returns True if the order id was found (advanced or completed).
    """
    queue = load_esp_queue()
    for idx, o in enumerate(queue):
        if str(o.get("id")) != str(order_id):
            continue

        # Normalize items list
        items = o.get("items") or []
        if not isinstance(items, list):
            items = []

        # If there are remaining items, consume ONE drink unit
        if items:
            first = items[0] if isinstance(items[0], dict) else {}
            try:
                qty = int(first.get("quantity", 1))
            except Exception:
                qty = 1

            if qty > 1:
                first["quantity"] = qty - 1
                items[0] = first
            else:
                # qty <= 1 => remove this item
                items.pop(0)

            # If items still remain, keep order active and reset timing estimation
            if items:
                o["items"] = items
                o["status"] = "In Progress"
                o["startedAt"] = _utc_now_iso()
                o["estSeconds"] = estimate_order_seconds(o)
                save_esp_queue(queue)
                return True

        # Otherwise (no items left) => fully complete + archive
        o["status"] = "complete"
        done = load_esp_done()
        done.append(o)
        save_esp_done(done)
        queue.pop(idx)
        save_esp_queue(queue)
        return True

    return False



def queue_position(order_id: str) -> dict | None:
    """
    Return position info for an order currently in queue.
    Position counts only active (Pending/In Progress) orders.
    position is 1-based.
    """
    q = load_esp_queue()
    active = [o for o in q if o.get("status") in ("Pending", "In Progress")]

    for i, o in enumerate(active):
        if str(o.get("id")) == str(order_id):
            # Seconds remaining for all orders ahead
            ahead_orders = active[:i]
            ahead_remaining = sum((_remaining_seconds_for_order(x) + int(ESP_PREP_SECONDS)) for x in ahead_orders)
            this_remaining = _remaining_seconds_for_order(o)
            this_est = int(o.get('estSeconds') or estimate_order_seconds(o))

            # ETA until *completion* of this order
            eta_to_complete = int(ahead_remaining + this_remaining)

            return {
                "position": i + 1,
                "ahead": i,
                "status": o.get("status"),
                "etaSeconds": eta_to_complete,
                "etaAheadSeconds": int(ahead_remaining),
                "etaThisSeconds": int(this_remaining),
                "estSeconds": int(this_est),
            }
    return None