from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET, STATIC_DIR
from app.core.auth import init_default_admin
from app.core.storage import ensure_drinks_file

from app.routers.auth_routes import router as auth_router
from app.routers.pages_routes import router as pages_router
from app.routers.drinks_routes import router as drinks_router
from app.routers.orders_routes import router as orders_router
from app.routers.recommend_routes import router as recommend_router
from app.routers.esp_routes import router as esp_router


def create_app() -> FastAPI:
    app = FastAPI()

    # sessions
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

    # static files (background images, css, etc.)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # data init
    ensure_drinks_file()
    init_default_admin()  # admin / 1234

    # routers
    app.include_router(auth_router)
    app.include_router(pages_router)
    app.include_router(drinks_router)
    app.include_router(orders_router)
    app.include_router(recommend_router)
    app.include_router(esp_router)

    return app


app = create_app()
