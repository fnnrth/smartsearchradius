"""Streamlit-MVP: Kleinanzeigen-Suche gefiltert per Fahrzeit-Isochrone."""

import html

import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from smartsearchradius.isochrone import IsochroneError, get_isochrone
from smartsearchradius.matcher import filter_by_isochrone
from smartsearchradius.plz_lookup import resolve_plz
from smartsearchradius.scraper import ScraperError, search_listings

load_dotenv()

PROFILES = {"Auto": "driving-car", "Fahrrad": "cycling-regular"}
# Label -> Wert des Kleinanzeigen-Suchformulars; None heisst "nicht einschraenken".
POSTER_TYPES = {"Alle": None, "Nur privat": "PRIVATE", "Nur gewerblich": "COMMERCIAL"}
AD_TYPES = {"Angebote": "OFFER", "Gesuche": "WANTED", "Beides": None}

st.set_page_config(page_title="SmartSearchRadius", layout="wide")
st.title("SmartSearchRadius")
st.caption("Kleinanzeigen filtern nach echter Fahrzeit statt Luftlinien-Radius")

with st.sidebar:
    start_plz = st.text_input("Start-PLZ", value="76133")
    minutes = st.slider("Fahrzeit (Minuten)", min_value=5, max_value=60, value=30, step=5)
    profile_label = st.selectbox("Verkehrsmittel", list(PROFILES.keys()))
    query = st.text_input("Suchbegriff", value="fahrrad")
    radius_km = st.slider(
        "Über-Fetch-Radius für die Kleinanzeigen-Suche (km)",
        min_value=10,
        max_value=200,
        value=100,
        help="Grosszuegig waehlen: nur ein Filter, kostet keine zusaetzlichen API-Calls.",
    )

    st.divider()
    st.caption("Filter (wirken direkt in der Kleinanzeigen-Suche)")
    price_from, price_to = st.columns(2)
    min_price = price_from.number_input(
        "Preis ab (€)", min_value=0, value=None, step=10, placeholder="egal"
    )
    max_price = price_to.number_input(
        "Preis bis (€)", min_value=0, value=None, step=10, placeholder="egal"
    )
    poster_label = st.selectbox("Anbieter", list(POSTER_TYPES))
    ad_label = st.selectbox("Anzeigenart", list(AD_TYPES))
    shipping_only = st.checkbox("Nur Anzeigen mit Versand")
    category_id = (
        st.text_input(
            "Kategorie-ID (optional)",
            placeholder="z.B. c217",
            help="Schraenkt auf eine Kategorie ein und schaltet deren Zusatzfilter frei. "
            "Die ID steht am Ende jeder Kategorie-URL auf kleinanzeigen.de.",
        ).strip()
        or None
    )

    search_clicked = st.button("Suchen", type="primary")

if search_clicked:
    # Alten Treffer verwerfen, damit ein Fehlschlag keine veralteten Ergebnisse stehen laesst.
    st.session_state.pop("search", None)

    # Vor dem Isochronen-Call pruefen: der kostet ein ORS-Kontingent.
    if min_price is not None and max_price is not None and min_price > max_price:
        st.error("'Preis ab' darf nicht größer als 'Preis bis' sein.")
        st.stop()

    start_coords = resolve_plz(start_plz)
    if start_coords is None:
        st.error(f"PLZ '{start_plz}' nicht in der lokalen PLZ-Tabelle gefunden.")
        st.stop()
    start_lat, start_lon = start_coords

    with st.spinner("Berechne Isochrone..."):
        try:
            polygon = get_isochrone(start_lat, start_lon, minutes, PROFILES[profile_label])
        except IsochroneError as e:
            st.error(str(e))
            st.stop()

    with st.spinner("Durchsuche Kleinanzeigen..."):
        try:
            listings = search_listings(
                query,
                start_plz,
                radius_km,
                min_price=int(min_price) if min_price is not None else None,
                max_price=int(max_price) if max_price is not None else None,
                poster_type=POSTER_TYPES[poster_label],
                ad_type=AD_TYPES[ad_label],
                category_id=category_id,
                shipping_only=shipping_only,
            )
        except ScraperError as e:
            st.error(str(e))
            st.stop()

    st.session_state["search"] = {
        "start_lat": start_lat,
        "start_lon": start_lon,
        "minutes": minutes,
        "polygon": polygon,
        "result": filter_by_isochrone(listings, polygon),
    }

# Gerendert wird immer aus dem Session-State, nie direkt aus `search_clicked`:
# `st_folium` meldet den Kartenzustand ans Backend zurueck und loest damit einen
# Rerun aus. In diesem Rerun ist der Button wieder False - ohne Session-State
# waere die Seite danach leer.
search = st.session_state.get("search")
if search is None:
    st.info("Parameter in der Seitenleiste waehlen und auf **Suchen** klicken.")
    st.stop()

result = search["result"]
start_lat, start_lon = search["start_lat"], search["start_lon"]
polygon = search["polygon"]

st.subheader(
    f"{len(result.within)} Treffer innerhalb {search['minutes']} Min "
    f"({len(result.outside)} ausserhalb, {len(result.unresolved)} ohne PLZ)"
)

fmap = folium.Map(location=[start_lat, start_lon], zoom_start=9)
folium.Marker(
    [start_lat, start_lon], tooltip="Startpunkt", icon=folium.Icon(color="blue")
).add_to(fmap)
folium.GeoJson(
    polygon.__geo_interface__,
    style_function=lambda _: {"fillColor": "green", "color": "green", "fillOpacity": 0.15},
).add_to(fmap)
for m in result.within:
    # Titel/Preis/URL kommen ungefiltert von Verkaeufern, folium rendert sie als HTML.
    title = html.escape(m.listing.title)
    price = html.escape(m.listing.price)
    url = html.escape(m.listing.url, quote=True)
    folium.Marker(
        [m.lat, m.lon],
        tooltip=f"{title} – {price}",
        popup=f'<a href="{url}" target="_blank">{title}</a><br>{price}',
        icon=folium.Icon(color="green"),
    ).add_to(fmap)

st_folium(fmap, key="isochrone_map", use_container_width=True, height=550)

st.markdown("### Treffer innerhalb der Fahrzeit")
for m in result.within:
    st.markdown(
        f"- [{m.listing.title}]({m.listing.url}) — {m.listing.price} ({m.listing.location_text})"
    )

if result.unresolved:
    with st.expander(f"{len(result.unresolved)} Anzeigen ohne auflösbare PLZ"):
        for listing in result.unresolved:
            st.markdown(f"- [{listing.title}]({listing.url}) — {listing.price}")
