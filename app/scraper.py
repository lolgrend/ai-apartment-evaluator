"""Pobieranie i parsowanie ogłoszeń.

Tryby:
  - httpx:      szybkie pobranie HTML
  - playwright: pełna przeglądarka (Chromium) — radzi sobie z anty-botem (OLX/Otodom)
  - auto:       httpx → jeśli treść wygląda na zablokowaną/pustą, próbuj playwright
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import settings

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_BLOCK_HINTS = ("captcha", "verify you are human", "dostęp został zablokowany", "cloudflare")

# Słowa kluczowe sygnalizujące rzut/plan mieszkania (PL + EN).
_FLOORPLAN_HINTS = ("rzut", "plan mieszkania", "plan lokalu", "floor plan", "floorplan")

# Fragmenty URL-i, które są elementami UI portalu (logo, ikony, sprite'y,
# placeholdery) — to nie są zdjęcia mieszkania i nie wolno ich dodawać.
_JUNK_IMAGE_HINTS = (
    "logo", "sprite", "icon", "favicon", "placeholder", "avatar",
    "watermark", "/static/", "statics.", "/assets/", "badge",
)


def _is_junk_image(url: str) -> bool:
    """True dla grafik UI portalu (logo otodom/olx/morizon, ikony itp.)."""
    low = url.lower()
    if low.endswith(".svg") or ".svg?" in low:
        return True
    return any(h in low for h in _JUNK_IMAGE_HINTS)


@dataclass
class ScrapedImage:
    url: str
    is_floorplan: bool = False


@dataclass
class ScrapeResult:
    url: str | None = None
    source: str | None = None
    title: str | None = None
    text: str = ""
    images: list[ScrapedImage] = field(default_factory=list)
    price_pln: int | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    location: str | None = None


def _source_of(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host or "nieznane"


def _looks_blocked(html: str) -> bool:
    low = html.lower()
    if len(low) < 600:
        return True
    return any(h in low for h in _BLOCK_HINTS)


def _looks_like_floorplan(*hints: str | None) -> bool:
    blob = " ".join(h for h in hints if h).lower()
    return any(kw in blob for kw in _FLOORPLAN_HINTS)


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[ScrapedImage]:
    found: list[ScrapedImage] = []
    # Najpierw og:image (zwykle główne, dobre zdjęcie)
    for og in soup.find_all("meta", attrs={"property": "og:image"}):
        if og.get("content"):
            full = urljoin(base_url, og["content"])
            if not _is_junk_image(full):
                found.append(ScrapedImage(url=full))
    # Potem <img> z sensownych źródeł
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-srcset", "").split(" ")[0]
        if not src or src.startswith("data:"):
            continue
        full = urljoin(base_url, src)
        if _is_junk_image(full):
            continue
        if not (
            any(full.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp"))
            or "image" in full
        ):
            continue
        parent_label = ""
        parent = img.parent
        if parent is not None:
            parent_label = " ".join(filter(None, [
                parent.get("aria-label") if parent.has_attr("aria-label") else None,
                parent.get("title") if parent.has_attr("title") else None,
            ]))
        is_fp = _looks_like_floorplan(
            img.get("alt"), img.get("title"), img.get("aria-label"),
            img.get("data-testid"), parent_label,
        )
        found.append(ScrapedImage(url=full, is_floorplan=is_fp))

    # Deduplikacja z zachowaniem kolejności; rzut wygrywa, jeśli ten sam URL.
    seen: dict[str, ScrapedImage] = {}
    for im in found:
        cur = seen.get(im.url)
        if cur is None:
            seen[im.url] = im
        elif im.is_floorplan and not cur.is_floorplan:
            seen[im.url] = im
    out = list(seen.values())

    # Posortuj: najpierw rzut(y), reszta w kolejności wystąpień.
    out.sort(key=lambda i: 0 if i.is_floorplan else 1)
    return out[: settings.max_images]


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return "\n".join(lines)[:20000]


# ── Heurystyki wyciągania liczb (działają też na wklejonym tekście) ──────────

def extract_price(text: str) -> int | None:
    # np. "650 000 zł", "650000 PLN", "650 tys. zł"
    m = re.search(r"(\d[\d  .]{4,})\s*(zł|pln)", text, re.IGNORECASE)
    if m:
        digits = re.sub(r"[  .]", "", m.group(1))
        if digits.isdigit():
            val = int(digits)
            if 10_000 <= val <= 50_000_000:
                return val
    m = re.search(r"(\d{2,4})\s*tys", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    return None


def extract_area(text: str) -> float | None:
    m = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*m(?:2|²|\^?2)\b", text, re.IGNORECASE)
    if m:
        val = float(m.group(1).replace(",", "."))
        if 8 <= val <= 1000:
            return val
    return None


def extract_rooms(text: str) -> int | None:
    m = re.search(r"(\d)\s*(?:pok(?:oje|oi|ój)?|-?pok)\b", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 12:
            return val
    return None


def _parse_html(html: str, url: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    text = _clean_text(BeautifulSoup(html, "html.parser"))
    res = ScrapeResult(
        url=url,
        source=_source_of(url),
        title=title,
        text=text,
        images=_extract_images(soup, url),
        price_pln=extract_price(text),
        area_sqm=extract_area(text),
        rooms=extract_rooms(text),
    )
    return res


def _fetch_httpx(url: str) -> str:
    headers = {"User-Agent": _UA, "Accept-Language": "pl-PL,pl;q=0.9"}
    with httpx.Client(follow_redirects=True, timeout=20.0, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def _fetch_playwright(url: str) -> str:
    # Import leniwy — Playwright bywa nieobecny w środowisku dev.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(user_agent=_UA, locale="pl-PL")
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)  # dociągnięcie treści dynamicznej

            # Akceptacja cookies (Otodom/OLX) — best-effort.
            for sel in (
                "button#onetrust-accept-btn-handler",
                "button:has-text('Akceptuję')",
                "button:has-text('Zgadzam się')",
            ):
                try:
                    page.locator(sel).first.click(timeout=1500)
                    break
                except Exception:  # noqa: BLE001
                    continue

            # Przewinięcie strony — wymusza lazy-load większości galerii.
            try:
                for _ in range(6):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(350)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(800)
            except Exception:  # noqa: BLE001
                pass

            # Spróbuj kliknąć przycisk „Rzut" / „Plan mieszkania", żeby wczytać obrazek do DOM.
            for sel in (
                "button:has-text('Rzut')",
                "a:has-text('Rzut')",
                "[aria-label*='Rzut' i]",
                "button:has-text('Plan mieszkania')",
                "button:has-text('Plan lokalu')",
            ):
                try:
                    loc = page.locator(sel).first
                    loc.scroll_into_view_if_needed(timeout=1500)
                    loc.click(timeout=1500)
                    page.wait_for_timeout(1200)
                    break
                except Exception:  # noqa: BLE001
                    continue

            # Wróć na górę dla porządku i daj DOM-owi się ustabilizować.
            try:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(400)
            except Exception:  # noqa: BLE001
                pass

            return page.content()
        finally:
            browser.close()


def scrape(url: str) -> ScrapeResult:
    """Pobiera ogłoszenie zgodnie z trybem skonfigurowanym w env."""
    mode = settings.scraper_mode
    html = ""

    if mode in ("httpx", "auto"):
        try:
            html = _fetch_httpx(url)
        except Exception:
            html = ""

    if mode == "playwright" or (mode == "auto" and (not html or _looks_blocked(html))):
        try:
            html = _fetch_playwright(url)
        except Exception as exc:  # noqa: BLE001
            if not html:
                raise RuntimeError(f"Nie udało się pobrać ogłoszenia: {exc}") from exc

    if not html:
        raise RuntimeError("Pusta odpowiedź — wklej treść ogłoszenia ręcznie.")

    return _parse_html(html, url)
