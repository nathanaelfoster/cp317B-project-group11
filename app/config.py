"""Runtime settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("WIMI_DB", BASE_DIR / "data" / "wimi.sqlite3"))

# "sample" runs fully offline against data/sample_gtfs and a simulated live feed.
# "live" polls Grand River Transit's GTFS-Realtime feeds.
MODE = os.environ.get("WIMI_MODE", "sample")

TIMEZONE = "America/Toronto"

# REP-3: poll the realtime feed every 30 seconds.
POLL_SECONDS = int(os.environ.get("WIMI_POLL_SECONDS", "30"))

# If the last successful collection is older than this, live data is treated as
# unavailable and riders are told so (Data Reliability NFR).
STALE_AFTER_SECONDS = int(os.environ.get("WIMI_STALE_AFTER", "90"))

SAMPLE_GTFS_DIR = BASE_DIR / "data" / "sample_gtfs"

# GRT open data endpoints. Check the current URLs on the Region of Waterloo open
# data portal before running in live mode; they can be overridden here.
GRT_STATIC_URL = os.environ.get(
    "GRT_STATIC_URL", "https://www.regionofwaterloo.ca/opendatadownloads/GRT_GTFS.zip"
)
GRT_TRIP_UPDATES_URL = os.environ.get(
    "GRT_TRIP_UPDATES_URL", "https://webapps.regionofwaterloo.ca/api/grt-routes/api/tripupdates"
)
GRT_ALERTS_URL = os.environ.get(
    "GRT_ALERTS_URL", "https://webapps.regionofwaterloo.ca/api/grt-routes/api/alerts"
)
