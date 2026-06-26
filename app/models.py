"""ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_PREFERENCES: dict = {
    "size_min": None,
    "size_max": None,
    "price_max": None,
    "rooms_min": None,
    "location_notes": "",
    "memory_notes": [],            # list of persistent notes ("must have a balcony")
    "weights": {"price": 3, "location": 3, "size": 3},  # 1-5
    "default_check_area": True,
    "model": None,                 # None = global MODEL value from env
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    listings: Mapped[list["Listing"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|evaluated|error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    # Extracted data / evaluation (denormalized for the gallery).
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_pln: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    eval_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Sharing.
    share_token: Mapped[str | None] = mapped_column(String(48), unique=True, nullable=True, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_with_household: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="listings")
    images: Mapped[list["ListingImage"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="ListingImage.position"
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )
    comments: Mapped[list["ListingComment"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="ListingComment.created_at"
    )


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_floorplan: Mapped[bool] = mapped_column(Boolean, default=False)

    listing: Mapped["Listing"] = relationship(back_populates="images")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    listing: Mapped["Listing"] = relationship(back_populates="messages")


class ListingComment(Base):
    __tablename__ = "listing_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # pinned comment
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    listing: Mapped["Listing"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship()
