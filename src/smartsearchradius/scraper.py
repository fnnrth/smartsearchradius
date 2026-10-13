"""Scraper fuer Kleinanzeigen-Suchergebnisse.

Fragil by design: Kleinanzeigen aendert das HTML gelegentlich ohne Vorankuendigung.
Kein Retry-Framework im MVP, Fehler sollen sichtbar auftreten statt verschluckt zu werden.

Kleinanzeigen liefert zwei Markup-Varianten aus: das klassische `.aditem`-Layout und
die neuere "srp-v3"-Variante mit Tailwind-Klassen. Letztere wird per Cookie
(`__ka_srp-v3=enabled`) aktiviert, das die Seite beim ersten Request selbst setzt --
ab Seite 2 kommt darum meist v3 zurueck. Gemeinsamer Anker beider Varianten ist
`article[data-adid]`, die Feld-Selektoren unterscheiden sich.
"""

import re
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

BASE_URL = "https://www.kleinanzeigen.de"
# GET-Formular der Suchseite (`form#site-search-form`). Kleinanzeigen antwortet
# darauf mit 301 auf die kanonische Pfad-URL, z.B.
#   /s-76133/anbieter:privat/anzeige:angebote/preis:100:300/fahrrad/k0l9194r50
# Damit muessen wir diese Pfad-Grammatik nicht selbst bauen - der Server macht das.
SEARCH_PATH = "/s-suchanfrage.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PLZ_RE = re.compile(r"\b(\d{5})\b")
REQUEST_DELAY_SECONDS = 1.5

PosterType = Literal["PRIVATE", "COMMERCIAL"]
AdType = Literal["OFFER", "WANTED"]

# Pro Feld erst die klassischen, dann die srp-v3-Selektoren.
TITLE_SELECTORS = ("h2.text-module-begin a", "h3 a", "h3")
PRICE_SELECTORS = (
    ".aditem-main--middle--price-shipping--price",
    'p[class*="font-strong"]',
)
LOCATION_SELECTORS = (".aditem-main--top--left",)
NEXT_PAGE_SELECTORS = ("a.pagination-next", '[aria-label*="Nächste"]')
# srp-v3 hat keine stabile Klasse am Ort, erkennbar ist er am "12345 Ort"-Muster.
LOCATION_TEXT_RE = re.compile(r"^\d{5}\s")


class ScraperError(RuntimeError):
    pass


@dataclass
class Listing:
    id: str
    title: str
    price: str
    location_text: str
    plz: str | None
    url: str


def _clean(text: str) -> str:
    """Normalisiert Whitespace und entfernt Zero-Width-Spaces aus Ortsnamen."""
    return " ".join(text.replace("\u200b", "").split())


def _first_text(article, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        node = article.css_first(selector)
        if node is None:
            continue
        text = _clean(node.text())
        if text:
            return text
    return ""


def _location_text(article) -> str:
    text = _first_text(article, LOCATION_SELECTORS)
    if text:
        return text
    for span in article.css("span"):
        candidate = _clean(span.text())
        if LOCATION_TEXT_RE.match(candidate):
            return candidate
    return ""


def _next_url(tree) -> str | None:
    for selector in NEXT_PAGE_SELECTORS:
        node = tree.css_first(selector)
        href = node.attributes.get("href") if node else None
        if href:
            return urljoin(BASE_URL, href)
    return None


def _parse_page(html: str) -> tuple[list[Listing], str | None]:
    tree = HTMLParser(html)
    articles = tree.css("article[data-adid]")

    listings = []
    for article in articles:
        listing_id = article.attributes.get("data-adid")
        href = article.attributes.get("data-href")
        if not listing_id or not href:
            continue

        location_text = _location_text(article)
        plz_match = PLZ_RE.search(location_text)

        listings.append(
            Listing(
                id=listing_id,
                title=_first_text(article, TITLE_SELECTORS),
                price=_first_text(article, PRICE_SELECTORS),
                location_text=location_text,
                plz=plz_match.group(1) if plz_match else None,
                url=urljoin(BASE_URL, href),
            )
        )

    # Keine Anzeigen-Container, aber Anzeigen-Links im HTML: das Markup hat sich
    # geaendert. Lieber lautstark scheitern als stillschweigend "0 Treffer" melden.
    if not articles and tree.css_first('a[href*="/s-anzeige/"]') is not None:
        raise ScraperError(
            "Kleinanzeigen-Markup hat sich geaendert: keine 'article[data-adid]'-Container "
            "gefunden, obwohl die Seite Anzeigen-Links enthaelt. Selektoren in scraper.py "
            "muessen angepasst werden."
        )

    return listings, _next_url(tree)


def _search_params(
    query: str,
    plz: str,
    radius_km: int,
    min_price: int | None,
    max_price: int | None,
    poster_type: PosterType | None,
    ad_type: AdType | None,
    category_id: str | None,
    shipping_only: bool,
) -> dict[str, str]:
    """Baut die Query-Parameter des Kleinanzeigen-Suchformulars.

    Weggelassene Filter bedeuten "nicht einschraenken" - genau wie ein leeres
    Feld im Formular. Nicht unterstuetzt sind `sortingField` und `pageNum`:
    beide verwirft Kleinanzeigen beim Redirect. Die Sortierung ist hier ohnehin
    belanglos, weil wir `max_pages` Seiten komplett einsammeln und erst
    matcher.py die Auswahl trifft; die Seitennavigation laeuft ueber `_next_url`.
    """
    params = {
        "keywords": query,
        "locationStr": plz,
        "radius": str(radius_km),
        "action": "find",
    }
    if min_price is not None:
        params["minPrice"] = str(min_price)
    if max_price is not None:
        params["maxPrice"] = str(max_price)
    if poster_type is not None:
        params["posterType"] = poster_type
    if ad_type is not None:
        params["adType"] = ad_type
    if category_id is not None:
        params["categoryId"] = category_id
    if shipping_only:
        params["shipping"] = "true"
    return params


def search_listings(
    query: str,
    plz: str,
    radius_km: int,
    max_pages: int = 5,
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    poster_type: PosterType | None = None,
    ad_type: AdType | None = None,
    category_id: str | None = None,
    shipping_only: bool = False,
) -> list[Listing]:
    """Sucht Kleinanzeigen fuer `query` im `radius_km`-Umkreis um `plz`.

    `radius_km` sollte grosszuegig gewaehlt werden (ueber-fetchen ist gratis) -
    die eigentliche Fahrzeit-Filterung passiert spaeter in matcher.py.

    Die Filter wirken serverseitig. Das ist nicht nur sparsamer, sondern beim
    Preis auch die einzig verlaessliche Variante: das Preisfeld einer Anzeige ist
    Freitext und enthaelt neben "2.499 €" auch "VB", "Zu verschenken" oder gar
    nichts - clientseitig liesse sich darauf nicht sauber filtern.

    `category_id` erwartet die Kleinanzeigen-Kategorie-ID (z.B. "c217" fuer
    Fahrraeder) und schaltet serverseitig zusaetzliche kategoriespezifische
    Filter frei. Es gibt hier bewusst keine ID-Tabelle: die Liste ist lang und
    aendert sich, die ID laesst sich aus jeder Kategorie-URL ablesen.
    """
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError(
            f"min_price ({min_price}) darf nicht groesser als max_price ({max_price}) sein."
        )

    url = f"{BASE_URL}{SEARCH_PATH}"
    params: dict[str, str] | None = _search_params(
        query, plz, radius_km, min_price, max_price, poster_type, ad_type,
        category_id, shipping_only,
    )
    all_listings: list[Listing] = []
    seen_ids: set[str] = set()
    visited_urls: set[str] = set()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True
    ) as client:
        for page_num in range(1, max_pages + 1):
            response = client.get(url, params=params)
            # Nur die erste Anfrage laeuft ueber das Formular. Der Redirect landet
            # auf der kanonischen URL, und die "Naechste"-Links tragen die Filter
            # ab da im Pfad mit - Parameter erneut anzuhaengen wuerde sie doppeln.
            params = None
            visited_urls.add(str(response.url))
            if response.status_code != 200:
                raise ScraperError(
                    f"Kleinanzeigen-Suche fehlgeschlagen ({response.status_code}) "
                    f"bei {response.url}"
                )

            listings, next_url = _parse_page(response.text)
            for listing in listings:
                if listing.id not in seen_ids:
                    seen_ids.add(listing.id)
                    all_listings.append(listing)

            # `next_url` schon besucht -> Kleinanzeigen zeigt im Kreis, Schleife beenden.
            if not next_url or next_url in visited_urls or page_num == max_pages:
                break
            url = next_url
            time.sleep(REQUEST_DELAY_SECONDS)

    return all_listings
