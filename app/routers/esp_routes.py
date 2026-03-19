from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import ESP_POLL_KEY, ETA_SECONDS_PER_DRINK, ESP_PREP_SECONDS
from app.core.storage import (
    get_active_order_for_esp,
    complete_and_archive_order,
    load_esp_queue,
    queue_position,
    _remaining_seconds_for_order,
)


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


router = APIRouter()


def _check_key(key: str):
    if key != ESP_POLL_KEY:
        raise HTTPException(status_code=401, detail="Invalid key")


class CompleteBody(BaseModel):
    id: str


@router.get("/api/esp/next")
def esp_next(key: str):
    """ESP polls this endpoint for the current job."""
    _check_key(key)
    order = get_active_order_for_esp()
    if not order:
        return {"ok": True, "order": None}

    # Queue meta (position + ETA)
    qinfo = queue_position(order.get("id")) or {}

    # IMPORTANT: keep payload small for ESP8266 memory.
    # Only send the *current* item (first remaining item), not the full items list.
    items = order.get("items") or []
    first = (items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {})
    qty = first.get("quantity", 1)
    try:
        qty = int(qty)
    except Exception:
        qty = 1

    compact = {
        "id": order.get("id"),
        "drinkId": first.get("drinkId", ""),
        "drinkName": first.get("drinkName", ""),
        "quantity": max(1, qty),
        "remainingItems": int(len(items) if isinstance(items, list) else 0),
        # Remaining time for the active order (seconds)
        "etaSeconds": int(qinfo.get("etaThisSeconds") or _remaining_seconds_for_order(order)),
        "queuePosition": qinfo.get("position"),
        "queueAhead": qinfo.get("ahead"),
        "queueEtaSeconds": qinfo.get("etaSeconds"),
        "stepSeconds": int(ETA_SECONDS_PER_DRINK),
        "prepSeconds": int(ESP_PREP_SECONDS),
    }

    return {"ok": True, "order": compact}


@router.post("/api/esp/complete")
def esp_complete(body: CompleteBody, key: str):
    """ESP calls this after finishing ONE drink unit.

    Guard: prevent instant completion (e.g., old firmware calling complete too early).
    We require that the current unit has been 'In Progress' for at least ETA_SECONDS_PER_DRINK seconds.
    """
    _check_key(key)

    # Find the order in queue to check timing
    q = load_esp_queue() or []
    target = None
    for o in q:
        if str(o.get("id")) == str(body.id) and o.get("status") in ("Pending", "In Progress"):
            target = o
            break

    # If we found it, enforce minimum elapsed time per unit
    if target is not None:
        started = _parse_iso(target.get("startedAt") or "")
        if started is not None:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            required = max(5, int(ETA_SECONDS_PER_DRINK))  # minimum per unit
            if elapsed < required:
                return {"ok": False, "error": "Too early to complete", "waitSeconds": int(required - elapsed)}

    ok = complete_and_archive_order(body.id)
    if ok:
        return {"ok": True}
    return {"ok": False, "error": "Order not found"}



@router.get("/api/queue/status")
def queue_status(orderId: str):
    """Frontend can poll this to show queue position for a given order."""
    info = queue_position(orderId)
    if not info:
        return {"ok": False, "error": "Not in queue (maybe already completed)"}
    return {"ok": True, "orderId": orderId, **info}


@router.get("/api/queue/active")
def queue_active(limit: int = 20):
    """(Optional) Show active queue for debugging."""
    q = [o for o in load_esp_queue() if o.get("status") in ("Pending", "In Progress")]
    return {"ok": True, "count": len(q), "queue": q[: max(1, min(int(limit), 100))]}
