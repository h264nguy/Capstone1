from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import ESP_POLL_KEY, ETA_SECONDS_PER_DRINK, ESP_PREP_SECONDS, DONE_HOLD_SECONDS
from app.core.storage import (
    get_active_order_for_esp,
    complete_and_archive_order,
    load_esp_queue,
    queue_position,
    _remaining_seconds_for_order,
    load_drinks,
)
from app.core.status import get_live_status, set_live_status


router = APIRouter()


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _status_age_seconds(status: dict) -> int:
    ts = _parse_iso((status or {}).get("updatedAt") or "")
    if ts is None:
        return 10**9
    return max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))


def _pretty_label(s: str) -> str:
    parts = str(s or "").replace("-", " ").replace("_", " ").split()
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _pretty_ingredient_name(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return s.replace("_", " ").replace("-", " ").title()


def _drink_lookup() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in load_drinks() or []:
        did = str(d.get("id") or "").strip()
        if did:
            out[did] = {
                "name": str(d.get("name") or did).strip(),
                "ingredients": list(d.get("ingredients") or []),
            }
    return out


def _enrich_status(raw: dict) -> dict:
    s = dict(raw or {})
    lookup = _drink_lookup()
    did = str(s.get("drinkId") or "").strip()
    meta = lookup.get(did) or {}
    machine = str(s.get("machine") or s.get("stage") or "").lower()

    ingredients = [_pretty_ingredient_name(x) for x in (meta.get("ingredients") or []) if str(x or "").strip()]
    if ingredients:
        s["ingredients"] = ingredients
        if not s.get("totalIngredients"):
            s["totalIngredients"] = len(ingredients)

    if not s.get("drink") and meta.get("name"):
        s["drink"] = meta.get("name")

    current_ing = _pretty_ingredient_name(s.get("currentIngredient") or "")
    if machine in {"queued", "idle", "waiting", "cooldown"}:
        current_ing = ""
    elif machine == "done":
        current_ing = current_ing
    elif not current_ing and ingredients:
        try:
            idx_raw = s.get("currentIngredientIndex")
            idx = int(idx_raw) if idx_raw not in (None, "") else 0
        except Exception:
            idx = 0
        idx = max(0, min(idx, len(ingredients) - 1))
        current_ing = ingredients[idx]
    s["currentIngredient"] = current_ing

    oid = str(s.get("orderId") or "").strip()
    if oid and machine == "queued":
        qinfo = queue_position(oid) or {}
        if int(s.get("remainingSeconds") or 0) <= 0 and qinfo:
            s["remainingSeconds"] = int(qinfo.get("etaSeconds") or 0)
        if not s.get("headline"):
            ahead = qinfo.get("ahead") if isinstance(qinfo, dict) else None
            note = f" • {ahead} ahead" if isinstance(ahead, int) and ahead > 0 else ""
            s["headline"] = f"Waiting in queue{note}"

    return s


def _queue_status_from_order(order: dict | None) -> dict | None:
    if not order:
        return None
    items = order.get("items") or []
    first = (items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {})
    drink_id = str(first.get("drinkId") or "")
    drink_name = str(first.get("drinkName") or "")
    info = _drink_lookup().get(drink_id, {})
    ingredients = [_pretty_ingredient_name(x) for x in (info.get("ingredients") or []) if str(x or "").strip()]
    qinfo = queue_position(order.get("id")) or {}
    ahead = qinfo.get("ahead") if isinstance(qinfo, dict) else None
    note = f" • {ahead} ahead" if isinstance(ahead, int) and ahead > 0 else ""
    return _enrich_status({
        "machine": "queued",
        "headline": f"Waiting in queue{note}",
        "drink": drink_name or info.get("name") or drink_id,
        "drinkId": drink_id,
        "stage": "queued",
        "currentIngredient": "",
        "currentIngredientIndex": 0,
        "totalIngredients": len(ingredients),
        "remainingSeconds": int(qinfo.get("etaSeconds") or _remaining_seconds_for_order(order)),
        "progress": 0,
        "orderId": order.get("id") or "",
        "ingredients": ingredients,
    })


def _check_key(key: str):
    if key != ESP_POLL_KEY:
        raise HTTPException(status_code=401, detail="Invalid key")


class CompleteBody(BaseModel):
    id: str


class StatusBody(BaseModel):
    orderId: str = ""
    drink: str = ""
    drinkId: str = ""
    machine: str = "pouring"
    headline: str = "Making drink"
    stage: str = "pouring"
    currentIngredient: str = ""
    currentIngredientIndex: int = 0
    totalIngredients: int = 0
    remainingSeconds: int = 0
    progress: int = 0
    ingredients: list[str] = []


@router.get("/api/esp/next")
def esp_next(key: str):
    _check_key(key)
    order = get_active_order_for_esp()
    if not order:
        return {"ok": True, "order": None}

    qinfo = queue_position(order.get("id")) or {}
    items = order.get("items") or []
    first = (items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {})
    qty = first.get("quantity", 1)
    try:
        qty = int(qty)
    except Exception:
        qty = 1

    drink_info = _drink_lookup().get(str(first.get("drinkId") or ""), {})
    ingredients = [_pretty_ingredient_name(x) for x in (drink_info.get("ingredients") or []) if str(x or "").strip()]

    compact = {
        "id": order.get("id"),
        "drinkId": first.get("drinkId", ""),
        "drinkName": first.get("drinkName", ""),
        "quantity": max(1, qty),
        "remainingItems": int(len(items) if isinstance(items, list) else 0),
        "etaSeconds": int(qinfo.get("etaThisSeconds") or _remaining_seconds_for_order(order)),
        "queuePosition": qinfo.get("position"),
        "queueAhead": qinfo.get("ahead"),
        "queueEtaSeconds": qinfo.get("etaSeconds"),
        "stepSeconds": int(ETA_SECONDS_PER_DRINK),
        "prepSeconds": int(ESP_PREP_SECONDS),
        "ingredients": ingredients,
    }

    return {"ok": True, "order": compact}


@router.post("/api/esp/status")
def esp_status(body: StatusBody, key: str):
    _check_key(key)
    status = set_live_status(_enrich_status(body.model_dump()))
    return {"ok": True, "status": status}


@router.get("/api/status")
def api_status():
    status = _enrich_status(get_live_status())
    machine = str(status.get("machine") or "").lower()
    if machine == "done":
        age = _status_age_seconds(status)
        if age >= DONE_HOLD_SECONDS:
            nxt = get_active_order_for_esp()
            queued = _queue_status_from_order(nxt)
            if queued:
                status = set_live_status(queued)
            else:
                status = set_live_status({
                    "machine": "idle",
                    "headline": "Waiting for next order",
                    "drink": "",
                    "drinkId": "",
                    "stage": "waiting",
                    "currentIngredient": "",
                    "currentIngredientIndex": 0,
                    "totalIngredients": 0,
                    "remainingSeconds": 0,
                    "progress": 0,
                    "orderId": "",
                    "ingredients": [],
                })
            status = _enrich_status(status)
    return {"ok": True, "status": status}


@router.post("/api/esp/complete")
def esp_complete(body: CompleteBody, key: str):
    _check_key(key)

    q = load_esp_queue() or []
    target = None
    for o in q:
        if str(o.get("id")) == str(body.id) and o.get("status") in ("Pending", "In Progress"):
            target = o
            break

    if target is not None:
        started = _parse_iso(target.get("startedAt") or "")
        if started is not None:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            required = max(5, int(ETA_SECONDS_PER_DRINK))
            if elapsed < required:
                return {"ok": False, "error": "Too early to complete", "waitSeconds": int(required - elapsed)}

    ok = complete_and_archive_order(body.id)
    if ok:
        current = get_live_status()
        set_live_status({
            "machine": "done",
            "headline": "Ready to serve",
            "stage": "done",
            "remainingSeconds": 0,
            "progress": 100,
            "currentIngredient": "",
            "currentIngredientIndex": max(int(current.get("totalIngredients") or 0), int(current.get("currentIngredientIndex") or 0)),
            "doneStartedAt": datetime.now(timezone.utc).isoformat(),
        })
        return {"ok": True}
    return {"ok": False, "error": "Order not found"}


@router.get("/api/queue/status")
def queue_status(orderId: str):
    info = queue_position(orderId)
    if not info:
        return {"ok": False, "error": "Not in queue (maybe already completed)"}
    return {"ok": True, "orderId": orderId, **info}


@router.get("/api/queue/active")
def queue_active(limit: int = 20):
    q = [o for o in load_esp_queue() if o.get("status") in ("Pending", "In Progress")]
    return {"ok": True, "count": len(q), "queue": q[: max(1, min(int(limit), 100))]}
