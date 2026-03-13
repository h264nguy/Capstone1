
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.config import LIVE_STATUS_FILE
from app.core.storage import _read_json, _write_json


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_status() -> Dict[str, Any]:
    return {
        "machine": "idle",
        "headline": "Idle",
        "drink": "",
        "drinkId": "",
        "stage": "waiting",
        "currentIngredient": "",
        "currentIngredientIndex": 0,
        "totalIngredients": 0,
        "remainingSeconds": 0,
        "progress": 0,
        "orderId": "",
        "updatedAt": _utc_now_iso(),
    }


def get_live_status() -> Dict[str, Any]:
    data = _read_json(LIVE_STATUS_FILE, default=default_status())
    if not isinstance(data, dict):
        data = default_status()
    merged = default_status()
    merged.update(data)
    return merged


def set_live_status(update: Dict[str, Any]) -> Dict[str, Any]:
    status = get_live_status()
    for k, v in (update or {}).items():
        status[k] = v
    status["updatedAt"] = _utc_now_iso()
    _write_json(LIVE_STATUS_FILE, status)
    return status


def clear_live_status(headline: str = "Idle") -> Dict[str, Any]:
    status = default_status()
    status["headline"] = headline
    _write_json(LIVE_STATUS_FILE, status)
    return status
