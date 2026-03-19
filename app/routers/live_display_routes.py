from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.storage import load_esp_done, load_esp_queue, load_drinks, queue_position

router = APIRouter()

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

INGREDIENT_LABELS = {
    "coca_cola": "Coca-Cola",
    "red_bull": "Red Bull",
    "ginger_ale": "Ginger Ale",
    "orange_juice": "Orange Juice",
    "sprite": "Sprite",
    "water": "Water",
    "lemonade": "Lemonade",
}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _drink_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in load_drinks() or []:
        did = str(d.get("id") or "").strip()
        if did:
            out[did] = d
    return out


def _pretty_ingredient(v: str) -> str:
    if not v:
        return ""
    return INGREDIENT_LABELS.get(v, str(v).replace("_", " ").title())


def _step_state(ingredients: list[str], elapsed: int, total: int) -> tuple[int, str, int]:
    ingredients = ingredients or ["Mixing"]
    count = max(1, len(ingredients))
    total = max(1, int(total))
    elapsed = max(0, int(elapsed))
    raw = min(count - 1, int((elapsed / total) * count))
    shown = min(count, raw + (1 if elapsed > 0 else 0))
    return shown, _pretty_ingredient(ingredients[raw]), count


@router.get('/live-display')
def live_display_page(request: Request):
    return TEMPLATES.TemplateResponse('live_display.html', {'request': request})


@router.get('/live')
def live_display_alias(request: Request):
    return TEMPLATES.TemplateResponse('live_display.html', {'request': request})


@router.get('/api/live-display')
def api_live_display() -> JSONResponse:
    drinks = _drink_map()
    queue = [o for o in (load_esp_queue() or []) if o.get('status') in ('Pending', 'In Progress')]
    done = load_esp_done() or []

    queue_cards = []
    current = None

    for o in queue:
        oid = str(o.get('id') or '')
        info = queue_position(oid) or {}
        items = o.get('items') or []
        first = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
        drink_id = str(first.get('drinkId') or '')
        drink_name = str(first.get('drinkName') or 'Drink')
        meta = drinks.get(drink_id, {})
        ingredients = meta.get('ingredients') or first.get('ingredients') or []
        if not isinstance(ingredients, list):
            ingredients = []

        started = _parse_iso(o.get('startedAt'))
        elapsed = int((_now() - started).total_seconds()) if started else 0
        est = int(o.get('estSeconds') or info.get('estSeconds') or 1)
        remaining_this = int(info.get('etaThisSeconds') or max(0, est - elapsed))
        step, current_ingredient, total_steps = _step_state(ingredients, elapsed, est)
        progress = max(0, min(100, round((elapsed / max(1, est)) * 100))) if o.get('status') == 'In Progress' else 0

        card = {
            'id': oid,
            'drinkId': drink_id,
            'drinkName': drink_name,
            'status': o.get('status') or 'Pending',
            'position': int(info.get('position') or 0),
            'ahead': int(info.get('ahead') or 0),
            'etaSeconds': int(info.get('etaSeconds') or 0),
            'etaThisSeconds': remaining_this,
            'estSeconds': est,
            'ingredients': [_pretty_ingredient(x) for x in ingredients],
            'currentIngredient': current_ingredient,
            'step': step,
            'totalSteps': total_steps,
            'progressPercent': progress,
        }
        queue_cards.append(card)
        if o.get('status') == 'In Progress' and current is None:
            current = card

    if current is None and queue_cards:
        current = queue_cards[0]

    last_done = None
    if done:
        latest = done[-1]
        finished_at = _parse_iso(latest.get('completedAt')) or _parse_iso(latest.get('startedAt')) or _parse_iso(latest.get('ts'))
        age = int((_now() - finished_at).total_seconds()) if finished_at else 999999
        if age <= 20:
            items = latest.get('items') or []
            first = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
            last_done = {
                'drinkName': first.get('drinkName') or latest.get('drinkName') or 'Your drink',
                'secondsAgo': age,
            }

    return JSONResponse({
        'ok': True,
        'current': current,
        'queue': queue_cards,
        'queueCount': len(queue_cards),
        'lastDone': last_done,
        'serverTime': _now().isoformat(),
    })
