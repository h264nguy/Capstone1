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
    load_machine_state,
    save_machine_state,
    load_drinks,
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


class FlushCompleteBody(BaseModel):
    ok: bool = True


@router.get("/api/esp/next")
def esp_next(key: str):
    """ESP polls this endpoint for the current job."""
    _check_key(key)
    state = load_machine_state()
    if state.get("flush_required"):
        return {"ok": True, "order": None, "waitingForFlush": True, "flushRequired": True, "flushRequested": bool(state.get("flush_requested")), "flushing": bool(state.get("flushing"))}
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

    drinks_map = {str(d.get('id') or '').strip().lower(): d for d in (load_drinks() or []) if isinstance(d, dict)}
    drink_meta = drinks_map.get(str(first.get('drinkId') or '').strip().lower(), {})
    per_drink_seconds = int(round(float(drink_meta.get('prep_seconds', ETA_SECONDS_PER_DRINK) or ETA_SECONDS_PER_DRINK)))

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
        "stepSeconds": int(per_drink_seconds),
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
            drinks_map = {str(d.get('id') or '').strip().lower(): d for d in (load_drinks() or []) if isinstance(d, dict)}
            first = ((target.get('items') or [{}])[0] if isinstance((target.get('items') or [{}])[0], dict) else {})
            drink_meta = drinks_map.get(str(first.get('drinkId') or '').strip().lower(), {})
            required = max(5, int(round(float(drink_meta.get('prep_seconds', ETA_SECONDS_PER_DRINK) or ETA_SECONDS_PER_DRINK))))  # minimum per unit
            if elapsed < required:
                return {"ok": False, "error": "Too early to complete", "waitSeconds": int(required - elapsed)}

    ok = complete_and_archive_order(body.id)
    if ok:
        save_machine_state({"flush_required": True, "flush_requested": False, "flushing": False, "last_completed_order_id": body.id})
        return {"ok": True, "flushRequired": True}
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


@router.post("/api/flush/request")
def flush_request():
    state = load_machine_state()
    if not state.get("flush_required"):
        return {"ok": False, "error": "No flush needed right now."}
    save_machine_state({"flush_requested": True, "flushing": True})
    return {"ok": True, "flush_requested": True}


@router.get("/api/esp/flush")
def esp_flush(key: str):
    _check_key(key)
    state = load_machine_state()
    return {
        "ok": True,
        "flush_required": bool(state.get("flush_required")),
        "flush_requested": bool(state.get("flush_requested")),
    }


@router.post("/api/esp/flush/complete")
def esp_flush_complete(body: FlushCompleteBody, key: str):
    _check_key(key)
    save_machine_state({"flush_required": False, "flush_requested": False, "flushing": False})
    return {"ok": True}
