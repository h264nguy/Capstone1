from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import json
from pathlib import Path

from app.core.auth import current_user
from app.core.storage import load_orders

# -------------------------
# Ingredient labels (normalized id -> display)
# -------------------------

# -------------------------
# Drink ingredients lookup (from app/data/drinks.json)
# -------------------------
try:
    _DRINKS_PATH = Path(__file__).resolve().parents[1] / "data" / "drinks.json"
    with open(_DRINKS_PATH, "r", encoding="utf-8") as _f:
        _drinks_data = json.load(_f)
    DRINK_INGREDIENTS = {d.get("id"): d.get("ingredients", []) for d in _drinks_data if isinstance(d, dict)}
except Exception:
    DRINK_INGREDIENTS = {}

INGREDIENT_LABELS = {
  "coca_cola": "Coca-Cola",
  "red_bull": "Red Bull",
  "ginger_ale": "Ginger Ale",
  "orange_juice": "Orange Juice",
  "sprite": "Sprite",
  "water": "Water",
  "lemonade": "Lemonade",
  "water": "Splash of Water",
  "sprite": "Splash of Sprite",
}

def pretty_ingredient(ing: str) -> str:
    if not ing:
        return ""
    return INGREDIENT_LABELS.get(ing, ing.replace("_"," ").title())
from app.ml.recommender import recommend_for_user, recommend_for_user_and_mood, ALLOWED_MOODS

router = APIRouter()


def _last_ordered_order(username: str) -> dict | None:
    """Return the last order row for this user (dict with drinkId/drinkName), or None."""
    try:
        orders = load_orders()
    except Exception:
        orders = []
    if not isinstance(orders, list) or not orders:
        return None
    user_orders = [o for o in orders if isinstance(o, dict) and o.get("username") == username]
    if not user_orders:
        return None
    user_orders.sort(key=lambda o: str(o.get("ts") or ""))
    return user_orders[-1]

def _based_on_ingredients(last_order: dict | None) -> list[str]:
    if not last_order:
        return []
    did = last_order.get("drinkId") or last_order.get("drink_id") or last_order.get("id")
    if not did:
        return []
    return list(DRINK_INGREDIENTS.get(did, []) or [])


@router.get("/api/recommendations")
def api_recommendations(request: Request, k: int = 3, mood: str | None = None):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Not logged in"}, status_code=401)

    kk = max(1, min(int(k), 3))

    if mood:
        mood_norm = str(mood).strip().lower()
        # Treat 'none' as no mood filter
        if mood_norm == 'none':
            try:
                request.session['mood'] = None
            except Exception:
                pass
            mood = None
            mood_norm = None
        else:
            # store selection in session so checkout can attach it
            try:
                request.session['mood'] = mood_norm
            except Exception:
                pass

            if mood_norm in ALLOWED_MOODS:
                recs = recommend_for_user_and_mood(user, mood_norm, k=kk)
                last_order = _last_ordered_order(user)
                based_on = (last_order or {}).get('drinkName') or (last_order or {}).get('drinkId')
                based_on_ingredients = _based_on_ingredients(last_order)
                return JSONResponse({'ok': True, 'username': user, 'mood': mood_norm, 'based_on': based_on, 'based_on_ingredients': based_on_ingredients, 'recommendations': recs})

            # invalid mood passed -> fall back to default recommendations (do not lock session)
            try:
                request.session['mood'] = None
            except Exception:
                pass
            mood = None
            mood_norm = None
    recs = recommend_for_user(user, k=kk)
    last_order = _last_ordered_order(user)
    based_on = (last_order or {}).get("drinkName") or (last_order or {}).get("drinkId")
    based_on_ingredients = _based_on_ingredients(last_order)
    return JSONResponse({"ok": True, "username": user, "mood": None, "based_on": based_on, "based_on_ingredients": based_on_ingredients, "recommendations": recs})