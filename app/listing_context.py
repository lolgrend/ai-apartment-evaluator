"""Kontrolowany, read-only dostęp agenta do zapisanych mieszkań."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Listing, User


def accessible_listing_catalog(
    db: Session, user: User, *, exclude_listing_id: int | None = None
) -> list[dict]:
    stmt = _accessible_stmt(user)
    if exclude_listing_id is not None:
        stmt = stmt.where(Listing.id != exclude_listing_id)
    rows = db.scalars(stmt.order_by(Listing.created_at.desc()).limit(100)).all()
    return [
        {
            "id": row.id,
            "title": row.title or f"Ogłoszenie #{row.id}",
            "location": row.location,
        }
        for row in rows
    ]


def read_listing_details(
    db: Session,
    user: User,
    listing_ids: list[int] | None,
    query: str | None,
    limit: int,
    *,
    exclude_listing_id: int | None = None,
) -> list[dict]:
    """Zwraca wyłącznie rekordy, które użytkownik może zobaczyć w aplikacji."""
    stmt = _accessible_stmt(user)
    if exclude_listing_id is not None:
        stmt = stmt.where(Listing.id != exclude_listing_id)
    if listing_ids:
        stmt = stmt.where(Listing.id.in_(listing_ids))
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(or_(
            Listing.title.ilike(pattern),
            Listing.location.ilike(pattern),
            Listing.raw_text.ilike(pattern),
        ))

    rows = db.scalars(stmt.order_by(Listing.created_at.desc()).limit(limit)).all()
    return [_serialize_listing(row) for row in rows]


def _accessible_stmt(user: User):
    return select(Listing).where(
        or_(Listing.user_id == user.id, Listing.shared_with_household.is_(True))
    )


def _serialize_listing(listing: Listing) -> dict:
    return {
        "id": listing.id,
        "title": listing.title or f"Ogłoszenie #{listing.id}",
        "url": listing.url,
        "source": listing.source,
        "price_pln": listing.price_pln,
        "area_sqm": listing.area_sqm,
        "rooms": listing.rooms,
        "location": listing.location,
        "score": listing.score,
        "recommendation": listing.recommendation,
        "summary": listing.summary,
        "evaluation": listing.evaluation,
        "user_comments": [
            {"body": comment.body, "pinned": comment.is_pinned}
            for comment in listing.comments
        ],
        "source_listing_text": listing.raw_text,
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,
    }
