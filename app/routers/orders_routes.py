from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import ETA_SECONDS_PER_DRINK

from app.core.auth import current_user
from app.core.storage import load_orders, save_orders, enqueue_esp_order, queue_position, load_esp_queue, load_drinks, load_machine_state, load_esp_done

router = APIRouter()


def _username_from_session(request: Request) -> Optional[str]:
    u = current_user(request)
    if not u:
        return None

    if isinstance(u, dict):
        u = u.get("username") or u.get("user") or u.get("name")

    sess = getattr(request, "session", {}) or {}
    u2 = sess.get("user") or sess.get("username") or u

    return str(u2) if u2 else None


def _drink_step_seconds(drink_id: str) -> int:
    try:
        did = str(drink_id or "").strip().lower()
        for d in load_drinks() or []:
            if isinstance(d, dict) and str(d.get("id") or "").strip().lower() == did:
                return int(round(float(d.get("prep_seconds", ETA_SECONDS_PER_DRINK) or ETA_SECONDS_PER_DRINK)))
    except Exception:
        pass
    return int(ETA_SECONDS_PER_DRINK)


def _latest_done_drink_name() -> str | None:
    done = load_esp_done() or []
    if not done:
        return None
    latest = done[-1]
    items = latest.get("items") or []
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0].get("drinkName") or latest.get("drinkName")
    return latest.get("drinkName")


@router.post("/checkout")
async def checkout(request: Request) -> JSONResponse:
    username = _username_from_session(request)
    if not username:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)

    mood = payload.get("mood") or (getattr(request, "session", {}) or {}).get("mood")
    mood = str(mood).strip().lower() if mood else None
    if mood and mood not in {"chill","energized","sweet","adventurous"}:
        mood = None

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return JSONResponse({"ok": False, "error": "No items"}, status_code=400)

    # Normalize + validate
    norm_items: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue

        drink_id = str(it.get("drinkId", "")).strip()
        drink_name = str(it.get("drinkName", "")).strip()

        try:
            qty = int(it.get("quantity", 1))
        except Exception:
            qty = 1

        try:
            cal = int(it.get("calories", 0))
        except Exception:
            cal = 0

        if not drink_id or not drink_name or qty <= 0:
            continue

        # Optional: ratios (for pump control + better ETA)
        ratios = it.get("ratios")
        norm_ratios = None
        if isinstance(ratios, dict):
            tmp = {}
            for k, v in ratios.items():
                try:
                    tmp[str(k)] = int(v)
                except Exception:
                    continue
            if tmp:
                norm_ratios = tmp

        row = {"drinkId": drink_id, "drinkName": drink_name, "quantity": qty, "calories": cal}
        if norm_ratios is not None:
            row["ratios"] = norm_ratios
        norm_items.append(row)

    if not norm_items:
        return JSONResponse({"ok": False, "error": "Items invalid"}, status_code=400)

    now = datetime.now(timezone.utc).isoformat()

    # ---- Save history rows (SAME file used by recommender) ----
    orders = load_orders()
    for it in norm_items:
        orders.append(
            {
                "username": username,
                "drinkId": it["drinkId"],
                "drinkName": it["drinkName"],
                "quantity": it["quantity"],
                "calories": it["calories"],
                "ts": now,
                "mood": mood,
            }
        )
    save_orders(orders)

    # ---- Enqueue ONE queue entry per DRINK UNIT (1-spot machine + per-drink ETA) ----
    order_ids: List[str] = []

    for it in norm_items:
        qty = int(it.get("quantity", 1))
        if qty < 1:
            qty = 1

        for _ in range(qty):
            oid = str(uuid4())
            order_ids.append(oid)

            item_one = {
                "drinkId": it["drinkId"],
                "drinkName": it["drinkName"],
                "quantity": 1,
                "calories": it.get("calories", 0),
            }
            if isinstance(it.get("ratios"), dict):
                item_one["ratios"] = it["ratios"]

            enqueue_esp_order(
                {
                    "id": oid,
                    "username": username,
                    "ts": now,
                    "mood": mood,
                    "status": "Pending",
                    "items": [item_one],
                }
            )

    # Provide queue info for the LAST enqueued unit (most recently added)
    order_id = order_ids[-1]
    pos = queue_position(order_id) or {}

    return JSONResponse(
        {"ok": True, "saved": True, "count": len(norm_items), "queued": True, "orderId": order_id, "orderIds": order_ids, "queue": pos},
        status_code=200,
    )




@router.get("/api/my/queue")
def api_my_queue(request: Request) -> JSONResponse:
    """Return ALL active queue entries for the logged-in user with position + ETA."""
    username = _username_from_session(request)
    if not username:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    q = load_esp_queue() or []
    active = [o for o in q if o.get("status") in ("Pending", "In Progress") and str(o.get("username")) == username]
    machine = load_machine_state()

    results: List[Dict[str, Any]] = []
    for o in active:
        oid = str(o.get("id"))
        info = queue_position(oid) or {}
        first_item = (o.get("items") or [{}])[0] if isinstance((o.get("items") or [{}])[0], dict) else {}
        did = first_item.get("drinkId")
        results.append(
            {
                "orderId": oid,
                "id": oid,
                "status": o.get("status"),
                "ts": o.get("ts"),
                "mood": o.get("mood"),
                "items": o.get("items") or [],
                "drinkName": first_item.get("drinkName"),
                "drinkId": did,
                "quantity": 1,
                "stepSeconds": _drink_step_seconds(did),
                **info,
            }
        )

    results.sort(key=lambda x: int(x.get("position") or 999999))

    return JSONResponse(
        {
            "ok": True,
            "username": username,
            "count": len(results),
            "orders": results,
            "flushRequired": bool(machine.get("flush_required")),
            "flushRequested": bool(machine.get("flush_requested")),
            "flushing": bool(machine.get("flushing")),
            "lastDoneDrinkName": _latest_done_drink_name(),
            "activeQueueCount": len([o for o in q if o.get("status") in ("Pending", "In Progress")]),
        },
        status_code=200,
    )


@router.get("/api/history")
def api_history(request: Request) -> JSONResponse:
    username = _username_from_session(request)
    if not username:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    orders = load_orders()
    mine = [o for o in orders if str(o.get("username")) == username]
    return JSONResponse({"ok": True, "username": username, "orders": mine})
