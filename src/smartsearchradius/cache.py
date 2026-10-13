"""DuckDB-Cache fuer Isochronen, damit wiederholte Suchen kein ORS-Kontingent verbrauchen."""

import json
from pathlib import Path

import duckdb

DB_FILE = Path(__file__).resolve().parents[2] / "cache.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS isochrones (
    lat DOUBLE,
    lon DOUBLE,
    profile VARCHAR,
    range_min INTEGER,
    geojson VARCHAR,
    fetched_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (lat, lon, profile, range_min)
);
"""


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_FILE))
    con.execute(_SCHEMA)
    return con


def get_cached_isochrone(lat: float, lon: float, profile: str, range_min: int) -> dict | None:
    con = _connect()
    row = con.execute(
        "SELECT geojson FROM isochrones WHERE lat = ? AND lon = ? AND profile = ? AND range_min = ?",
        [round(lat, 4), round(lon, 4), profile, range_min],
    ).fetchone()
    con.close()
    return json.loads(row[0]) if row else None


def store_isochrone(lat: float, lon: float, profile: str, range_min: int, geojson: dict) -> None:
    con = _connect()
    con.execute(
        "INSERT OR REPLACE INTO isochrones (lat, lon, profile, range_min, geojson) VALUES (?, ?, ?, ?, ?)",
        [round(lat, 4), round(lon, 4), profile, range_min, json.dumps(geojson)],
    )
    con.close()
