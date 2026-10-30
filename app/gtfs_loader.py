"""REP-2: load a GTFS static feed (folder, .zip file or URL) into the database."""
import csv
import io
import logging
import zipfile
from pathlib import Path

import requests

from .timeutil import parse_gtfs_time

log = logging.getLogger(__name__)

REQUIRED_FILES = ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt"]


def _read_tables(source):
    """Return {filename: list of row dicts} for a folder, zip path or URL."""
    source = str(source)
    if source.startswith(("http://", "https://")):
        log.info("Downloading GTFS from %s", source)
        resp = requests.get(source, timeout=60)
        resp.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        names = {Path(n).name: n for n in archive.namelist()}
        opener = lambda name: io.TextIOWrapper(archive.open(names[name]), encoding="utf-8-sig")
        available = set(names)
    elif source.endswith(".zip"):
        archive = zipfile.ZipFile(source)
        names = {Path(n).name: n for n in archive.namelist()}
        opener = lambda name: io.TextIOWrapper(archive.open(names[name]), encoding="utf-8-sig")
        available = set(names)
    else:
        folder = Path(source)
        opener = lambda name: open(folder / name, encoding="utf-8-sig", newline="")
        available = {p.name for p in folder.glob("*.txt")}

    missing = [f for f in REQUIRED_FILES if f not in available]
    if missing:
        raise ValueError(f"GTFS feed is missing {', '.join(missing)}")

    tables = {}
    for name in REQUIRED_FILES + ["calendar.txt", "calendar_dates.txt"]:
        if name in available:
            with opener(name) as fh:
                tables[name] = list(csv.DictReader(fh))
    return tables


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_gtfs(conn, source):
    """Replace the static schedule with the feed at `source`. Returns row counts."""
    tables = _read_tables(source)

    with conn:
        for table in ["stop_times", "trips", "calendar", "calendar_dates", "routes", "stops"]:
            conn.execute(f"DELETE FROM {table}")

        conn.executemany(
            "INSERT INTO stops VALUES (?, ?, ?, ?, ?, ?)",
            [
                (r["stop_id"], r.get("stop_code"), r["stop_name"], float(r["stop_lat"]),
                 float(r["stop_lon"]), _int(r.get("wheelchair_boarding")))
                for r in tables["stops.txt"]
                if r.get("stop_lat") and r.get("stop_lon")
            ],
        )
        conn.executemany(
            "INSERT INTO routes VALUES (?, ?, ?, ?)",
            [
                (r["route_id"], r.get("route_short_name"), r.get("route_long_name"),
                 _int(r.get("route_type"), 3))
                for r in tables["routes.txt"]
            ],
        )
        conn.executemany(
            "INSERT INTO trips VALUES (?, ?, ?, ?, ?)",
            [
                (r["trip_id"], r["route_id"], r["service_id"], r.get("trip_headsign"),
                 _int(r.get("wheelchair_accessible")))
                for r in tables["trips.txt"]
            ],
        )
        conn.executemany(
            "INSERT INTO stop_times VALUES (?, ?, ?, ?, ?)",
            [
                (r["trip_id"], int(r["stop_sequence"]), r["stop_id"],
                 parse_gtfs_time(r["arrival_time"] or r["departure_time"]),
                 parse_gtfs_time(r["departure_time"] or r["arrival_time"]))
                for r in tables["stop_times.txt"]
                if r.get("arrival_time") or r.get("departure_time")
            ],
        )
        conn.executemany(
            "INSERT INTO calendar VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["service_id"], _int(r["monday"]), _int(r["tuesday"]), _int(r["wednesday"]),
                 _int(r["thursday"]), _int(r["friday"]), _int(r["saturday"]),
                 _int(r["sunday"]), r["start_date"], r["end_date"])
                for r in tables.get("calendar.txt", [])
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO calendar_dates VALUES (?, ?, ?)",
            [
                (r["service_id"], r["date"], _int(r["exception_type"]))
                for r in tables.get("calendar_dates.txt", [])
            ],
        )

    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["stops", "routes", "trips", "stop_times"]}
    log.info("Loaded GTFS: %s", counts)
    return counts
