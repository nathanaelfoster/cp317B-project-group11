-- REP-2: Transit Data Storage
-- Static schedule tables mirror GTFS. trip_updates holds every recorded arrival,
-- linked to its trip and stop, with the service date and time it was recorded.

CREATE TABLE IF NOT EXISTS stops (
    stop_id             TEXT PRIMARY KEY,
    stop_code           TEXT,
    stop_name           TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    wheelchair_boarding INTEGER NOT NULL DEFAULT 0  -- 0 unknown, 1 accessible, 2 not accessible
);

CREATE TABLE IF NOT EXISTS routes (
    route_id    TEXT PRIMARY KEY,
    short_name  TEXT,
    long_name   TEXT,
    route_type  INTEGER
);

CREATE TABLE IF NOT EXISTS trips (
    trip_id               TEXT PRIMARY KEY,
    route_id              TEXT NOT NULL REFERENCES routes(route_id),
    service_id            TEXT NOT NULL,
    headsign              TEXT,
    wheelchair_accessible INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id        TEXT NOT NULL REFERENCES trips(trip_id),
    stop_sequence  INTEGER NOT NULL,
    stop_id        TEXT NOT NULL REFERENCES stops(stop_id),
    arrival_secs   INTEGER NOT NULL,  -- seconds after midnight; may exceed 86400
    departure_secs INTEGER NOT NULL,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id, arrival_secs);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip_stop ON stop_times(trip_id, stop_id);

CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER, tuesday INTEGER, wednesday INTEGER, thursday INTEGER,
    friday INTEGER, saturday INTEGER, sunday INTEGER,
    start_date TEXT,  -- YYYYMMDD
    end_date   TEXT
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id     TEXT NOT NULL,
    date           TEXT NOT NULL,  -- YYYYMMDD
    exception_type INTEGER NOT NULL,  -- 1 added, 2 removed
    PRIMARY KEY (service_id, date)
);

-- One row per trip, stop and service day. Each collection overwrites the row
-- with the newest prediction, so after the bus passes the row holds its
-- recorded arrival.
CREATE TABLE IF NOT EXISTS trip_updates (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id            TEXT NOT NULL REFERENCES trips(trip_id),
    stop_id            TEXT NOT NULL REFERENCES stops(stop_id),
    route_id           TEXT NOT NULL,
    service_date       TEXT NOT NULL,     -- YYYY-MM-DD
    service_dow        INTEGER NOT NULL,  -- 0 Monday .. 6 Sunday
    scheduled_secs     INTEGER NOT NULL,  -- scheduled arrival, seconds after midnight
    scheduled_arrival  TEXT NOT NULL,     -- ISO 8601 with offset
    predicted_arrival  TEXT,              -- ISO 8601 with offset; NULL when cancelled
    delay_seconds      INTEGER,
    cancelled          INTEGER NOT NULL DEFAULT 0,
    recorded_at        TEXT NOT NULL,
    UNIQUE (trip_id, stop_id, service_date)
);
CREATE INDEX IF NOT EXISTS idx_tu_stop ON trip_updates(stop_id, service_dow, scheduled_secs);
CREATE INDEX IF NOT EXISTS idx_tu_route ON trip_updates(route_id, service_dow, scheduled_secs);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    header       TEXT,
    description  TEXT,
    effect       TEXT,
    cause        TEXT,
    active_start TEXT,
    active_end   TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_entities (
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    route_id TEXT,
    stop_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_entities_alert ON alert_entities(alert_id);

-- Data Reliability NFR: every collection attempt is logged, success or not.
CREATE TABLE IF NOT EXISTS collection_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    attempted_at TEXT NOT NULL,
    success      INTEGER NOT NULL,
    trip_updates INTEGER NOT NULL DEFAULT 0,
    alerts       INTEGER NOT NULL DEFAULT 0,
    duration_ms  INTEGER,
    message      TEXT
);
