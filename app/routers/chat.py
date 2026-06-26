"""Listing chat route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import agent
from ..auth import require_user
from ..database import get_db
from ..listing_context import accessible_listing_catalog, read_listing_details
from ..models import ChatMessage, Listing, User

router = APIRouter()


@router.post("/listing/{listing_id}/chat")
def send_message(
    listing_id: int, request: Request, message: str = Form(...),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    listing = db.get(Listing, listing_id)
    if listing is None or (listing.user_id != user.id and not listing.shared_with_household):
        raise HTTPException(404, "Listing not found")

    message = message.strip()
    if not message:
        return RedirectResponse(f"/listing/{listing.id}#chat", status_code=303)

    history = [{"role": m.role, "content": m.content} for m in listing.messages]
    db.add(ChatMessage(listing_id=listing.id, role="user", content=message))

    available_listings = accessible_listing_catalog(db, user)

    def listing_reader(listing_ids: list[int] | None, query: str | None, limit: int):
        return read_listing_details(db, user, listing_ids, query, limit)

    try:
        reply = agent.chat(
            listing_text=listing.raw_text or "", evaluation=listing.evaluation,
            history=history, user_message=message, prefs=user.preferences or {},
            available_listings=available_listings,
            listing_reader=listing_reader,
            user_id=user.id, session_id=f"listing-{listing.id}", listing_id=listing.id,
        )
    except Exception as exc:  # noqa: BLE001
        reply = f"Model error: {exc}"

    db.add(ChatMessage(listing_id=listing.id, role="assistant", content=reply))
    db.commit()
    return RedirectResponse(f"/listing/{listing.id}#chat", status_code=303)
