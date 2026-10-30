"""Date and time helpers for GTFS service days."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TIMEZONE)
DAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def now_local():
    return datetime.now(TZ)


def parse_gtfs_time(value):
    """'25:10:00' -> 90600. GTFS times can run past midnight."""
    h, m, s = (int(part) for part in value.strip().split(":"))
    return h * 3600 + m * 60 + s


def scheduled_datetime(service_date, secs):
    """Turn a service date plus seconds after midnight into an aware datetime."""
    midnight = datetime.combine(service_date, time(0), tzinfo=TZ)
    return midnight + timedelta(seconds=secs)


def secs_since_midnight(dt, service_date):
    midnight = datetime.combine(service_date, time(0), tzinfo=TZ)
    return int((dt - midnight).total_seconds())


def parse_service_date(value):
    """Accept GTFS 'YYYYMMDD' or ISO 'YYYY-MM-DD'."""
    value = value.replace("-", "")
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def active_service_ids(conn, service_date):
    ymd = service_date.strftime("%Y%m%d")
    column = DAY_COLUMNS[service_date.weekday()]
    ids = {
        row["service_id"]
        for row in conn.execute(
            f"SELECT service_id FROM calendar WHERE {column} = 1 AND start_date <= ? AND end_date >= ?",
            (ymd, ymd),
        )
    }
    for row in conn.execute(
        "SELECT service_id, exception_type FROM calendar_dates WHERE date = ?", (ymd,)
    ):
        if row["exception_type"] == 1:
            ids.add(row["service_id"])
        else:
            ids.discard(row["service_id"])
    return ids
