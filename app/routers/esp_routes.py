
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
    load_drinks,
)
from app.core.status import get_live_status, set_live_status


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


router = APIRouter()


def _pretty_label(s: str) -> str:
    parts = str(s or "").replace("-", " ").replace("_", " ").split()
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def _drink_lookup() -> dict[str, dict]:
    data = {}
    for d in load_drinks() or []:
        did = str(d.get("id") or "").strip()
        if not did:
            continue
        data[did] = {
            "name": str(d.get("name") or did).strip(),
            "ingredients": list(d.get("ingredients") or []),
        }
    return data


def _enrich_status(raw: dict) -> dict:
    s = dict(raw or {})
    lookup = _drink_lookup()
    did = str(s.get("drinkId") or "").strip()
    meta = lookup.get(did) or {}
    canonical_name = str(meta.get("name") or did or s.get("drink") or "").strip()
    ingredients = [ _pretty_label(x) for x in (meta.get("ingredients") or []) ]

    current_drink = str(s.get("drink") or "").strip()
    if canonical_name and (not current_drink or current_drink in ingredients):
        s["drink"] = canonical_name

    total = int(s.get("totalIngredients") or 0)
    if not total and ingredients:
        total = len(ingredients)
        s["totalIngredients"] = total

    stage = str(s.get("stage") or s.get("machine") or "").lower()
    current_ing = str(s.get("currentIngredient") or "").strip()
    if current_ing:
        current_ing = _pretty_label(current_ing)

    if not current_ing and ingredients and stage not in {"idle", "waiting", "done", "cooldown"}:
        current_ing = ingredients[0]
    s["currentIngredient"] = current_ing

    idx = int(s.get("currentIngredientIndex") or 0)
    if idx <= 0 and current_ing and total > 0 and stage not in {"idle", "waiting", "done", "cooldown"}:
        idx = 1
        s["currentIngredientIndex"] = idx

    oid = str(s.get("orderId") or "").strip()
    if oid:
        qinfo = queue_position(oid) or {}
        if stage == "queued" and int(s.get("remainingSeconds") or 0) <= 0 and qinfo:
            s["remainingSeconds"] = int(qinfo.get("etaSeconds") or 0)
        if not s.get("headline"):
            if stage == "queued":
                ahead = qinfo.get("ahead") if isinstance(qinfo, dict) else None
                note = f" • {ahead} ahead" if isinstance(ahead, int) and ahead > 0 else ""
                s["headline"] = f"Order queued{note}"

    if stage == "queued" and current_ing and not s.get("headline"):
        s["headline"] = "Order queued"

    return s


def _pretty_ingredient_name(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return s.replace("_", " ").replace("-", " ").title()


def _drink_lookup() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in (load_drinks() or []):
        if isinstance(d, dict) and d.get("id"):
            out[str(d.get("id"))] = d
    return out


def _enrich_status(status: dict) -> dict:
    s = dict(status or {})
    drink_id = str(s.get("drinkId") or "")
    info = _drink_lookup().get(drink_id, {})
    ingredients = [_pretty_ingredient_name(x) for x in (info.get("ingredients") or []) if str(x or "").strip()]
    if ingredients:
        s.setdefault("ingredients", ingredients)
        if not s.get("totalIngredients"):
            s["totalIngredients"] = len(ingredients)
    if not s.get("drink") and info.get("name"):
        s["drink"] = info.get("name")
    if s.get("machine") == "queued" and not s.get("currentIngredient") and ingredients:
        s["currentIngredient"] = ", ".join(ingredients[:4])
    return s


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


@router.get("/api/esp/next")
def esp_next(key: str):
    """ESP polls this endpoint for the current job."""
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
    return {"ok": True, "status": _enrich_status(get_live_status())}


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
            "headline": "Drink Ready",
            "stage": "done",
            "remainingSeconds": 0,
            "progress": 100,
            "currentIngredient": "",
            "currentIngredientIndex": max(int(current.get("totalIngredients") or 0), int(current.get("currentIngredientIndex") or 0)),
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
