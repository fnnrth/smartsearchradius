"""Offline PLZ -> (lat, lon) Auflösung, ersetzt eine Geocoding-API."""

import csv
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "plz_centroids.csv"


@lru_cache(maxsize=1)
def load_plz_table() -> dict[str, tuple[float, float]]:
    table: dict[str, tuple[float, float]] = {}
    with DATA_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            table[row["plz"]] = (float(row["lat"]), float(row["lon"]))
    return table


def resolve_plz(plz: str) -> tuple[float, float] | None:
    return load_plz_table().get(plz.strip())
