"""FastAPI application entrypoint."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from .auth import hash_password
from .config import settings
from .database import SessionLocal, init_db
from .models import DEFAULT_PREFERENCES, User
from .routers import auth as auth_router
from .routers import chat as chat_router
from .routers import listings as listings_router
from .routers import settings as settings_router


def _seed_admin() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(User).limit(1)) is None:
            db.add(User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
                preferences=dict(DEFAULT_PREFERENCES),
            ))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _seed_admin()
    yield


app = FastAPI(title="Apartment Evaluator", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 24 * 30)

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.include_router(auth_router.router)
app.include_router(listings_router.router)
app.include_router(chat_router.router)
app.include_router(settings_router.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/manifest.webmanifest")
def manifest():
    return RedirectResponse("/static/manifest.webmanifest")
