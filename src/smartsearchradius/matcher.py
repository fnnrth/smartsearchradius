"""Filtert Kleinanzeigen anhand des Fahrzeit-Isochronen-Polygons."""

from dataclasses import dataclass

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from smartsearchradius.plz_lookup import resolve_plz
from smartsearchradius.scraper import Listing


@dataclass
class MatchedListing:
    listing: Listing
    lat: float
    lon: float


@dataclass
class MatchResult:
    within: list[MatchedListing]
    outside: list[MatchedListing]
    unresolved: list[Listing]


def filter_by_isochrone(listings: list[Listing], polygon: BaseGeometry) -> MatchResult:
    within: list[MatchedListing] = []
    outside: list[MatchedListing] = []
    unresolved: list[Listing] = []

    for listing in listings:
        coords = resolve_plz(listing.plz) if listing.plz else None
        if coords is None:
            unresolved.append(listing)
            continue

        lat, lon = coords
        matched = MatchedListing(listing=listing, lat=lat, lon=lon)
        if polygon.contains(Point(lon, lat)):
            within.append(matched)
        else:
            outside.append(matched)

    return MatchResult(within=within, outside=outside, unresolved=unresolved)
