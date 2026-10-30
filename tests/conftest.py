from datetime import datetime

import pytest
from google.transit import gtfs_realtime_pb2

from app import config, db, timeutil
from app.gtfs_loader import load_gtfs

# A fixed weekday afternoon so tests do not depend on the clock.
NOW = datetime(2026, 10, 28, 16, 0, tzinfo=timeutil.TZ)  # Wednesday 4:00 PM


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    db.init_db(c)
    load_gtfs(c, config.SAMPLE_GTFS_DIR)
    yield c
    c.close()


def empty_feed():
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    return feed
