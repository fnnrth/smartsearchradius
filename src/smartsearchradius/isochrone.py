"""OpenRouteService-Isochronen-Client mit DuckDB-Cache."""

import os

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from smartsearchradius.cache import get_cached_isochrone, store_isochrone

ORS_ISOCHRONE_URL = "https://api.openrouteservice.org/v2/isochrones/{profile}"
# Grosse Zeitfenster sind bei ORS rechenintensiv; 30s waren dafuer zu knapp.
ORS_TIMEOUT_SECONDS = 60.0
# Timeouts sind bei ORS meist transient. Ein zweiter Versuch reicht - schlaegt der
# auch fehl, liegt es an ORS und Warten hilft dem Nutzer mehr als weitere Retries.
ORS_ATTEMPTS = 2


class IsochroneError(RuntimeError):
    pass


def get_isochrone(
    lat: float, lon: float, minutes: int, profile: str = "driving-car"
) -> BaseGeometry:
    """Liefert das Fahrzeit-Polygon fuer einen Startpunkt. Nutzt den DuckDB-Cache."""
    if minutes > 60:
        raise IsochroneError("OpenRouteService begrenzt Isochronen auf maximal 60 Minuten")

    cached = get_cached_isochrone(lat, lon, profile, minutes)
    if cached is not None:
        return shape(cached["features"][0]["geometry"])

    api_key = os.environ.get("ORS_API_KEY")
    if not api_key:
        raise IsochroneError("ORS_API_KEY ist nicht gesetzt (siehe .env.example)")

    for attempt in range(1, ORS_ATTEMPTS + 1):
        try:
            response = httpx.post(
                ORS_ISOCHRONE_URL.format(profile=profile),
                headers={"Authorization": api_key},
                json={
                    "locations": [[lon, lat]],
                    "range": [minutes * 60],
                    "range_type": "time",
                },
                timeout=ORS_TIMEOUT_SECONDS,
            )
            break
        # Netzwerkebene: Timeout, DNS, abgebrochene Verbindung. Ohne diese
        # Uebersetzung in IsochroneError schlaegt der Traceback roh in die UI durch.
        except httpx.RequestError as e:
            if attempt == ORS_ATTEMPTS:
                raise IsochroneError(
                    f"OpenRouteService war nach {ORS_ATTEMPTS} Versuchen nicht erreichbar "
                    f"({type(e).__name__}). Kurz warten und erneut suchen; bei kleinerer "
                    f"Fahrzeit antwortet der Dienst schneller."
                ) from e

    if response.status_code != 200:
        raise IsochroneError(
            f"ORS-Anfrage fehlgeschlagen ({response.status_code}): {response.text}"
        )

    geojson = response.json()
    store_isochrone(lat, lon, profile, minutes, geojson)
    return shape(geojson["features"][0]["geometry"])
