from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(REPO_ROOT / "templates"))


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request):
    return templates.TemplateResponse("status.html", {"request": request})
