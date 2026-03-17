from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.storage import ensure_drinks_file, load_drinks

router = APIRouter()


@router.get("/api/drinks")
def api_drinks():
    ensure_drinks_file()
    return JSONResponse(load_drinks())


@router.get("/api/drink-links")
def api_drink_links():
    """Convenience endpoint for Canva: gives you the link for each drink."""
    ensure_drinks_file()
    drinks = load_drinks()
    out = []
    for d in drinks:
        did = d.get("id")
        out.append({
            "id": did,
            "name": d.get("name"),
            "calories": d.get("calories", 0),
            "path": f"/drink/{did}",
        })
    return JSONResponse(out)
