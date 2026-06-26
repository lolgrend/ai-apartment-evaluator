"""Settings: user preferences and account management for admins."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin, require_user
from ..config import MODEL_OPTIONS, settings
from ..database import get_db
from ..models import DEFAULT_PREFERENCES, User
from ..templating import templates

router = APIRouter()


def _to_int(v: str) -> int | None:
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


@router.get("/settings", response_class=HTMLResponse)
def settings_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    prefs = {**DEFAULT_PREFERENCES, **(user.preferences or {})}
    other_users = []
    if user.is_admin:
        other_users = db.scalars(select(User).order_by(User.username)).all()
    return templates.TemplateResponse(
        request, "settings.html",
        {"user": user, "prefs": prefs, "other_users": other_users, "saved": False,
         "model_options": MODEL_OPTIONS, "default_model": settings.model},
    )


@router.post("/settings")
def settings_save(
    request: Request,
    size_min: str = Form(""), size_max: str = Form(""),
    price_max: str = Form(""), rooms_min: str = Form(""),
    location_notes: str = Form(""), memory_notes: str = Form(""),
    weight_price: int = Form(3), weight_location: int = Form(3), weight_size: int = Form(3),
    default_check_area: bool = Form(False),
    model: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    prefs = {
        "size_min": _to_int(size_min),
        "size_max": _to_int(size_max),
        "price_max": _to_int(price_max),
        "rooms_min": _to_int(rooms_min),
        "location_notes": location_notes.strip(),
        "memory_notes": [ln.strip() for ln in memory_notes.splitlines() if ln.strip()],
        "weights": {
            "price": max(1, min(5, weight_price)),
            "location": max(1, min(5, weight_location)),
            "size": max(1, min(5, weight_size)),
        },
        "default_check_area": default_check_area,
        "model": model if model in MODEL_OPTIONS else None,
    }
    user.preferences = prefs
    db.commit()
    other_users = db.scalars(select(User).order_by(User.username)).all() if user.is_admin else []
    return templates.TemplateResponse(
        request, "settings.html",
        {"user": user, "prefs": prefs, "other_users": other_users, "saved": True,
         "model_options": MODEL_OPTIONS, "default_model": settings.model},
    )


@router.post("/settings/users")
def add_user(
    username: str = Form(...), password: str = Form(...),
    db: Session = Depends(get_db), admin: User = Depends(require_admin),
):
    username = username.strip()
    if username and not db.scalar(select(User).where(User.username == username)):
        db.add(User(
            username=username, password_hash=hash_password(password),
            is_admin=False, preferences=dict(DEFAULT_PREFERENCES),
        ))
        db.commit()
    return RedirectResponse("/settings", status_code=303)
