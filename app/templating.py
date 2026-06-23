"""Współdzielona instancja silnika szablonów Jinja2."""
from __future__ import annotations

import os

import bleach
import markdown
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_DIR)

_REC_LABEL = {
    "strong_yes": "Zdecydowanie tak",
    "yes": "Tak",
    "maybe": "Może",
    "no": "Nie",
}
_REC_CLASS = {"strong_yes": "rec-strong", "yes": "rec-yes", "maybe": "rec-maybe", "no": "rec-no"}


def _score_class(score: int | None) -> str:
    if score is None:
        return "score-none"
    if score >= 75:
        return "score-high"
    if score >= 50:
        return "score-mid"
    return "score-low"


# Rozpoznanie portalu po fragmencie hosta -> (czytelna nazwa, symbol).
_SOURCES = (
    ("otodom", ("Otodom", "O")),
    ("olx", ("OLX", "OLX")),
    ("morizon", ("Morizon", "M")),
    ("gratka", ("Gratka", "G")),
    ("domiporta", ("Domiporta", "D")),
    ("nieruchomosci-online", ("Nieruchomości-online", "N")),
    ("allegro", ("Allegro", "A")),
    ("facebook", ("Facebook", "f")),
)


def _source_meta(source: str | None) -> tuple[str, str]:
    low = (source or "").lower()
    for key, meta in _SOURCES:
        if key in low:
            return meta
    return (source or "Źródło", "↗")


_CHAT_TAGS = {
    "a", "blockquote", "br", "code", "del", "em", "h2", "h3", "h4",
    "li", "ol", "p", "pre", "strong", "table", "tbody", "td", "th",
    "thead", "tr", "ul",
}


def _chat_markdown(value: str | None) -> Markup:
    """Renderuje Markdown modelu i usuwa niebezpieczny HTML/URL-e."""
    rendered = markdown.markdown(
        value or "",
        extensions=["nl2br", "sane_lists", "tables"],
        output_format="html",
    )
    cleaned = bleach.clean(
        rendered,
        tags=_CHAT_TAGS,
        attributes={"a": ["href", "title"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return Markup(cleaned)


templates.env.filters["rec_label"] = lambda r: _REC_LABEL.get(r, "—")
templates.env.filters["rec_class"] = lambda r: _REC_CLASS.get(r, "")
templates.env.filters["score_class"] = _score_class
templates.env.filters["source_label"] = lambda s: _source_meta(s)[0]
templates.env.filters["source_symbol"] = lambda s: _source_meta(s)[1]
templates.env.filters["chat_markdown"] = _chat_markdown
