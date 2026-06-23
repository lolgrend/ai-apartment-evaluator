"""Ogłoszenia: dodawanie, ocena, galeria, szczegóły, ulubione, udostępnianie."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import agent, scraper
from ..auth import get_current_user, require_user
from ..config import settings
from ..database import get_db
from ..listing_context import accessible_listing_catalog, read_listing_details
from ..models import Listing, ListingComment, ListingImage, User
from ..templating import templates

router = APIRouter()


def _apply_floorplan_detection(
    images: list[ListingImage], detected_indices: list[int]
) -> None:
    """Łączy wykrycie modelu z heurystyką scrapera; indeksy są 1-based."""
    detected = {index for index in detected_indices if 1 <= index <= len(images)}
    for index, image in enumerate(images, start=1):
        image.is_floorplan = image.is_floorplan or index in detected


def _get_listing_for_view(db: Session, listing_id: int, user: User) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(404, "Nie znaleziono ogłoszenia")
    if listing.user_id != user.id and not listing.shared_with_household:
        raise HTTPException(403, "Brak dostępu")
    return listing


def _get_own_listing(db: Session, listing_id: int, user: User) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None or listing.user_id != user.id:
        raise HTTPException(404, "Nie znaleziono ogłoszenia")
    return listing


@router.get("/", response_class=HTMLResponse)
def gallery(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = (
        select(Listing)
        .where(or_(Listing.user_id == user.id, Listing.shared_with_household.is_(True)))
        .order_by(Listing.created_at.desc())
    )
    listings = db.scalars(stmt).all()
    return templates.TemplateResponse(
        request, "gallery.html", {"user": user, "listings": listings}
    )


@router.get("/add", response_class=HTMLResponse)
def add_form(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "add.html", {"user": user, "error": None})


@router.post("/add")
def add_submit(
    request: Request,
    url: str = Form(""),
    raw_text: str = Form(""),
    images_text: str = Form(""),
    check_area: bool = Form(False),
    compare_previous: bool = Form(False),
    analyze_floorplan: bool = Form(False),
    extra_prompt: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    url = url.strip()
    raw_text = raw_text.strip()
    if not url and not raw_text:
        return templates.TemplateResponse(
            request, "add.html",
            {"user": user, "error": "Podaj link albo wklej treść ogłoszenia."},
            status_code=400,
        )

    title = None
    source = None
    scraped_imgs: list[scraper.ScrapedImage] = []
    listing_text = raw_text

    if url:
        try:
            sr = scraper.scrape(url)
            title = sr.title
            source = sr.source
            scraped_imgs = sr.images
            listing_text = (raw_text + "\n\n" + sr.text).strip() if raw_text else sr.text
        except Exception as exc:  # noqa: BLE001
            if not raw_text:
                return templates.TemplateResponse(
                    request, "add.html",
                    {"user": user, "error": f"Nie udało się pobrać linku: {exc}. "
                     "Wklej treść ogłoszenia ręcznie."},
                    status_code=400,
                )

    # Ręcznie wklejone URL-e zdjęć (po jednym w linii)
    manual_imgs = [
        scraper.ScrapedImage(url=ln.strip())
        for ln in images_text.splitlines()
        if ln.strip().startswith("http") and not scraper._is_junk_image(ln.strip())
    ]
    # Rzut zawsze najpierw, żeby zmieścił się w limicie i trafił do agenta.
    all_imgs = scraped_imgs + manual_imgs
    all_imgs.sort(key=lambda i: 0 if i.is_floorplan else 1)
    all_imgs = all_imgs[: settings.max_images]
    image_urls = [im.url for im in all_imgs]

    options = {
        "check_area": check_area,
        "compare_previous": compare_previous,
        "analyze_floorplan": analyze_floorplan,
        "extra_prompt": extra_prompt.strip(),
    }

    listing = Listing(
        user_id=user.id, url=url or None, source=source, title=title,
        raw_text=listing_text, status="pending", eval_options=options,
    )
    db.add(listing)
    db.flush()
    listing_images = []
    for i, img in enumerate(all_imgs):
        listing_image = ListingImage(
            listing_id=listing.id, url=img.url, position=i,
            is_floorplan=img.is_floorplan,
        )
        listing_images.append(listing_image)
        db.add(listing_image)

    # Ocena (synchronicznie)
    previous = []
    available_listings = None
    listing_reader = None
    if compare_previous:
        prev_rows = db.scalars(
            select(Listing).where(Listing.user_id == user.id, Listing.summary.isnot(None))
            .order_by(Listing.created_at.desc()).limit(10)
        ).all()
        previous = [f"{l.title or 'ogłoszenie'}: {l.summary}" for l in prev_rows]
        available_listings = accessible_listing_catalog(
            db, user, exclude_listing_id=listing.id
        )

        def listing_reader(listing_ids: list[int] | None, query: str | None, limit: int):
            return read_listing_details(
                db, user, listing_ids, query, limit, exclude_listing_id=listing.id
            )

    try:
        result = agent.evaluate(
            listing_text=listing_text, image_urls=image_urls, options=options,
            prefs=user.preferences or {}, previous_summaries=previous,
            available_listings=available_listings, listing_reader=listing_reader,
            user_id=user.id, session_id=f"listing-{listing.id}", listing_id=listing.id,
        )
        listing.status = "evaluated"
        listing.score = result.overall_score
        listing.recommendation = result.recommendation
        listing.summary = result.summary
        listing.area_sqm = result.area_sqm
        listing.price_pln = result.price_pln
        listing.rooms = result.rooms
        listing.location = result.location
        listing.title = listing.title or (result.location or "Ogłoszenie")
        listing.evaluation = result.model_dump()
        _apply_floorplan_detection(listing_images, result.floorplan_image_indices)
    except Exception as exc:  # noqa: BLE001
        listing.status = "error"
        listing.error_message = str(exc)

    db.commit()
    return RedirectResponse(f"/listing/{listing.id}", status_code=303)


@router.get("/listing/{listing_id}", response_class=HTMLResponse)
def listing_detail(
    listing_id: int, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    listing = _get_listing_for_view(db, listing_id, user)
    return templates.TemplateResponse(
        request, "listing.html",
        {"user": user, "listing": listing, "is_owner": listing.user_id == user.id,
         "public_base": settings.public_base_url},
    )


@router.post("/listing/{listing_id}/favorite")
def toggle_favorite(
    listing_id: int, db: Session = Depends(get_db), user: User = Depends(require_user),
):
    listing = _get_own_listing(db, listing_id, user)
    listing.is_favorite = not listing.is_favorite
    db.commit()
    return RedirectResponse(f"/listing/{listing.id}", status_code=303)


@router.post("/listing/{listing_id}/reevaluate")
def reevaluate(listing_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    listing = _get_own_listing(db, listing_id, user)
    options = listing.eval_options or {}
    image_urls = [im.url for im in listing.images]
    try:
        result = agent.evaluate(
            listing_text=listing.raw_text or "", image_urls=image_urls,
            options=options, prefs=user.preferences or {},
            user_id=user.id, session_id=f"listing-{listing.id}", listing_id=listing.id,
        )
        listing.status = "evaluated"
        listing.score = result.overall_score
        listing.recommendation = result.recommendation
        listing.summary = result.summary
        listing.area_sqm = result.area_sqm
        listing.price_pln = result.price_pln
        listing.rooms = result.rooms
        listing.location = result.location
        listing.evaluation = result.model_dump()
        _apply_floorplan_detection(
            list(listing.images), result.floorplan_image_indices
        )
        listing.error_message = None
    except Exception as exc:  # noqa: BLE001
        listing.status = "error"
        listing.error_message = str(exc)
    db.commit()
    return RedirectResponse(f"/listing/{listing.id}", status_code=303)


@router.post("/listing/{listing_id}/delete")
def delete_listing(listing_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    listing = _get_own_listing(db, listing_id, user)
    db.delete(listing)
    db.commit()
    return RedirectResponse("/", status_code=303)


# ── Komentarze ──────────────────────────────────────────────────────────────

@router.post("/listing/{listing_id}/comment")
def add_comment(
    listing_id: int, body: str = Form(...), pinned: bool = Form(False),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    listing = _get_listing_for_view(db, listing_id, user)
    body = body.strip()
    if body:
        db.add(ListingComment(
            listing_id=listing.id, user_id=user.id, body=body, is_pinned=pinned
        ))
        db.commit()
    return RedirectResponse(f"/listing/{listing.id}", status_code=303)


# ── Współdzielenie ──────────────────────────────────────────────────────────

@router.post("/listing/{listing_id}/share")
def toggle_share(
    listing_id: int, household: bool = Form(False), public: bool = Form(False),
    db: Session = Depends(get_db), user: User = Depends(require_user),
):
    listing = _get_own_listing(db, listing_id, user)
    listing.shared_with_household = household
    listing.is_shared = public
    if public and not listing.share_token:
        listing.share_token = secrets.token_urlsafe(16)
    db.commit()
    return RedirectResponse(f"/listing/{listing.id}", status_code=303)


@router.get("/s/{token}", response_class=HTMLResponse)
def public_view(token: str, request: Request, db: Session = Depends(get_db)):
    listing = db.scalar(select(Listing).where(Listing.share_token == token))
    if listing is None or not listing.is_shared:
        raise HTTPException(404, "Link nieaktywny")
    pinned = [c for c in listing.comments if c.is_pinned]
    return templates.TemplateResponse(
        request, "share.html", {"listing": listing, "pinned_comments": pinned}
    )
