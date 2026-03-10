from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from typing import Dict, List, Tuple

from app.core.storage import load_orders, load_drinks


def _format_ing(ing: str) -> str:
    return str(ing).replace("_", " ").strip()

def _user_ing_counts(username: str, drink_by_id: Dict[str, dict]) -> Counter:
    orders = load_orders()
    c: Counter = Counter()
    for o in orders:
        if str(o.get("username")) != str(username):
            continue
        did = o.get("drinkId")
        if did is None:
            continue
        d = drink_by_id.get(str(did))
        if not d:
            continue
        ings = d.get("ingredients") if isinstance(d, dict) else None
        if not isinstance(ings, list):
            continue
        try:
            qty = int(o.get("quantity", 1))
        except Exception:
            qty = 1
        qty = max(1, qty)
        for ing in ings:
            if ing:
                c[str(ing)] += qty
    return c

def _attach_why(recs: List[dict], username: str, drink_by_id: Dict[str, dict], mood: str | None = None) -> List[dict]:
    counts = _user_ing_counts(username, drink_by_id)
    top_ings = [ing for ing, _ in counts.most_common(6)]
    out: List[dict] = []
    for d in recs:
        if not isinstance(d, dict):
            continue
        dd = dict(d)  # copy so we don't mutate global drink objects
        why: List[str] = []
        if mood:
            why.append(f"Matches mood: {mood}")
        ings = dd.get("ingredients")
        if isinstance(ings, list) and top_ings:
            common = [ing for ing in ings if str(ing) in set(top_ings)]
            # keep order, unique, max 3
            seen = set()
            picked = []
            for ing in common:
                s = str(ing)
                if s in seen:
                    continue
                seen.add(s)
                picked.append(_format_ing(s).title())
                if len(picked) >= 3:
                    break
            if picked:
                why.append("Shares: " + ", ".join(picked))
        if not why:
            why.append("Popular choice")
        dd["why"] = why
        out.append(dd)
    return out


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity of sparse vectors."""
    if not a or not b:
        return 0.0
    dot = 0.0
    for k, av in a.items():
        bv = b.get(k)
        if bv is not None:
            dot += av * bv
    na = sqrt(sum(v * v for v in a.values()))
    nb = sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _build_user_vectors() -> Tuple[Dict[str, Dict[str, float]], Counter]:
    """Returns (user->drinkId->count, global_drink_counts)."""
    orders = load_orders()
    user_vec: Dict[str, Counter] = defaultdict(Counter)
    global_counts: Counter = Counter()

    for o in orders:
        username = o.get("username")
        drink_id = o.get("drinkId")
        qty = o.get("quantity", 1)

        if not username or not drink_id:
            continue

        try:
            qty = int(qty)
        except Exception:
            qty = 1

        if qty < 1:
            qty = 1

        did = str(drink_id)
        user_vec[str(username)][did] += qty
        global_counts[did] += qty

    return ({u: dict(c) for u, c in user_vec.items()}, global_counts)


def recommend_for_user(username: str, k: int = 5) -> List[dict]:
    """
    Collaborative filtering-ish recommender.

    - If user has history: find similar users (cosine) and score drinks they like.
    - If not: return globally popular drinks.

    Returns list of drink dicts (id, name, calories).
    """
    drinks = load_drinks()
    drink_by_id = {
        str(d.get("id")): d
        for d in drinks
        if isinstance(d, dict) and d.get("id") is not None
    }

    user_vectors, global_counts = _build_user_vectors()
    target = user_vectors.get(str(username), {})

    def popular(exclude: set[str]) -> List[str]:
        return [did for did, _ in global_counts.most_common() if did not in exclude]

    tried = set(target.keys())

    # --- Cold start: no history for this user ---
    if not target:
        ids = popular(exclude=set()) if global_counts else [str(d.get("id")) for d in drinks if d.get("id") is not None]
        out: List[dict] = []
        for did in ids:
            d = drink_by_id.get(str(did))
            if d:
                out.append(d)
            if len(out) >= k:
                break
        return _attach_why(out, username, drink_by_id, mood=None)

    # --- Find similar users ---
    sims: List[Tuple[str, float]] = []
    for other, vec in user_vectors.items():
        if other == str(username):
            continue
        s = _cosine(target, vec)
        if s > 0:
            sims.append((other, s))

    sims.sort(key=lambda x: x[1], reverse=True)
    sims = sims[:25]  # cap

    # --- Score candidate drinks from similar users ---
    scores: Counter = Counter()
    for other, s in sims:
        vec = user_vectors.get(other, {})
        for did, cnt in vec.items():
            if did in tried:
                continue
            scores[did] += s * float(cnt)

    ranked_ids = [did for did, _ in scores.most_common()]

    # If no similar-user signal, fallback to popularity excluding tried
    if not ranked_ids:
        ranked_ids = popular(exclude=tried)

    # Final fallback: any untried drinks from menu
    if not ranked_ids:
        ranked_ids = [str(d.get("id")) for d in drinks if d.get("id") is not None and str(d.get("id")) not in tried]

    out: List[dict] = []
    for did in ranked_ids:
        d = drink_by_id.get(str(did))
        if d:
            out.append(d)
        if len(out) >= k:
            break

    return out
# -------------------------
# Mood-based logic (category rules from the UI)
# -------------------------

# The UI categories (from your screenshot) are STRICT:
#   Energized: Sprite, Coca-Cola, Red Bull
#   Sweet: Orange Juice, Ginger Ale
#   Chill: Water AND Low Calories
#   Adventurous: "Unusual combo" (we treat as cross-category mixes / complex ingredient overlap)

MOOD_INGREDIENTS: Dict[str, set[str]] = {
    "energized": {"sprite", "coca_cola", "red_bull"},
    "sweet": {"orange_juice", "ginger_ale"},
}

ALLOWED_MOODS = {"energized", "sweet", "chill", "adventurous"}

# Calories threshold used for the "low calories" rule (tunable).
LOW_CAL_THRESHOLD = 70


def _is_low_cal(drink: dict) -> bool:
    try:
        return int(drink.get("calories", 0)) <= LOW_CAL_THRESHOLD
    except Exception:
        return False


def _drink_matches_mood(drink: dict, mood: str) -> bool:
    mood = (mood or "").strip().lower()
    ings = drink.get("ingredients") or []
    if not isinstance(ings, list):
        ings = []

    ing_set = {str(i) for i in ings if i}

    if mood in ("energized", "sweet"):
        return len(ing_set & MOOD_INGREDIENTS[mood]) > 0

    if mood == "chill":
        # Chill must be BOTH water-based AND low-cal (per your definition)
        return ("water" in ing_set) and _is_low_cal(drink)

    if mood == "adventurous":
        # "Unusual combo" heuristic:
        # - cross-category mix (at least one energized + one sweet ingredient), OR
        # - 3+ ingredients and matches at least 2 of the other categories.
        energized = len(ing_set & MOOD_INGREDIENTS["energized"]) > 0
        sweet = len(ing_set & MOOD_INGREDIENTS["sweet"]) > 0
        chill = ("water" in ing_set) and _is_low_cal(drink)

        if energized and sweet:
            return True

        if len(ing_set) >= 3:
            matches = int(energized) + int(sweet) + int(chill)
            return matches >= 2

        return False

    return False


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union) if union else 0.0


def recommend_for_user_and_mood(username: str, mood: str, k: int = 3) -> List[dict]:
    """
    Ingredient + history recommender (matches the capstone demo story):

    - Filter candidates to the selected mood category (rules above).
    - Score candidates using:
        1) Ingredient preference: user's ingredient counts from ALL their past orders
        2) Similarity to user's most-ordered drinks (ingredient overlap)
        3) "Most ordered drinks" boost for THIS user
        4) Small global popularity fallback

    Returns up to 3 drinks, each with a "why" field.
    """
    mood = (mood or "").strip().lower()
    if mood not in ALLOWED_MOODS:
        return recommend_for_user(username, k=max(1, min(int(k), 3)))

    k = max(1, min(int(k), 3))

    drinks = load_drinks()
    drink_by_id = {str(d.get("id")): d for d in drinks if isinstance(d, dict) and d.get("id") is not None}

    # --- Build user drink counts + ingredient counts ---
    orders = load_orders()
    user_drink_counts: Counter = Counter()
    global_counts: Counter = Counter()
    for o in orders:
        did = o.get("drinkId")
        if did is None:
            continue
        try:
            qty = int(o.get("quantity", 1))
        except Exception:
            qty = 1
        qty = max(1, qty)

        did = str(did)
        global_counts[did] += qty

        if str(o.get("username")) == str(username):
            user_drink_counts[did] += qty

    user_ing_counts = _user_ing_counts(username, drink_by_id)
    max_ing = max(user_ing_counts.values()) if user_ing_counts else 1

    # Top ordered drinks for this user (used for similarity)
    top_user_drinks = [did for did, _ in user_drink_counts.most_common(3)]
    top_ing_sets: List[set[str]] = []
    for did in top_user_drinks:
        d = drink_by_id.get(did)
        ings = d.get("ingredients") if isinstance(d, dict) else []
        if isinstance(ings, list):
            top_ing_sets.append({str(i) for i in ings if i})

    # --- Candidate pool: only drinks in this mood category ---
    candidates: List[dict] = []
    for d in drinks:
        if not isinstance(d, dict) or d.get("id") is None:
            continue
        if _drink_matches_mood(d, mood):
            candidates.append(d)

    # If nothing matches (shouldn't), fallback to baseline
    if not candidates:
        return recommend_for_user(username, k=k)

    scored: List[tuple[float, dict]] = []
    for d in candidates:
        did = str(d.get("id"))
        ings = d.get("ingredients") or []
        if not isinstance(ings, list):
            ings = []
        ing_set = {str(i) for i in ings if i}

        # 1) ingredient preference score (0..1-ish)
        pref = sum(float(user_ing_counts.get(ing, 0)) / float(max_ing) for ing in ing_set) / max(1.0, float(len(ing_set)))

        # 2) similarity to user's favorites (0..1)
        sim = 0.0
        for s in top_ing_sets:
            sim = max(sim, _jaccard(ing_set, s))

        # 3) most-ordered boost for this user's account (scaled)
        ud = float(user_drink_counts.get(did, 0))
        ud_boost = (ud ** 0.5) / 5.0  # small

        # 4) global popularity (tiny)
        gp = float(global_counts.get(did, 0))
        gp_boost = (gp ** 0.5) / 12.0

        # overall score (weights tuned for demo clarity)
        score = (0.55 * pref) + (0.25 * sim) + (0.15 * ud_boost) + (0.05 * gp_boost)
        scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Unique top-k (guard against duplicates)
    out: List[dict] = []
    seen = set()
    for _, d in scored:
        did = str(d.get("id"))
        if did in seen:
            continue
        seen.add(did)
        out.append(d)
        if len(out) >= k:
            break

    return _attach_why(out, username, drink_by_id, mood=mood)
