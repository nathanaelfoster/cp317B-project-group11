"""Generate the small sample GTFS feed in data/sample_gtfs.

The stops are real Waterloo Region locations with approximate coordinates, but
the routes, timetables and accessibility flags are made up for demos and tests.
Run: python tools/make_sample_gtfs.py
"""
import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_gtfs"

# stop_id, code, name, lat, lon, wheelchair_boarding (1 yes, 2 no)
STOPS = [
    ("CONESTOGA", "1001", "Conestoga Station", 43.4980, -80.5288, 1),
    ("COLUMBIA_KING", "1002", "Columbia St. / King St.", 43.4842, -80.5305, 1),
    ("UW_STATION", "1003", "University of Waterloo Station", 43.4733, -80.5413, 1),
    ("UNIV_KING", "1004", "University Ave. / King St.", 43.4726, -80.5265, 1),
    ("LAURIER_PARK", "1005", "Laurier-Waterloo Park Station", 43.4741, -80.5285, 1),
    ("ALBERT_SEAGRAM", "1006", "Albert St. / Seagram Dr.", 43.4762, -80.5320, 2),
    ("PHILLIP_COLUMBIA", "1007", "Phillip St. / Columbia St.", 43.4810, -80.5400, 1),
    ("PUBLIC_SQUARE", "1008", "Waterloo Public Square Station", 43.4652, -80.5228, 1),
    ("GRAND_RIVER_HOSP", "1009", "Grand River Hospital Station", 43.4559, -80.5112, 1),
    ("KITCHENER_CITY_HALL", "1010", "Kitchener City Hall Station", 43.4508, -80.4895, 1),
    ("FAIRWAY", "1011", "Fairway Station", 43.4248, -80.4405, 1),
]

# route_id, short name, long name, route_type, stop pattern, headsigns, weekday headway (min)
ROUTES = [
    ("7", "7", "King", 3,
     ["CONESTOGA", "COLUMBIA_KING", "UNIV_KING", "PUBLIC_SQUARE", "GRAND_RIVER_HOSP",
      "KITCHENER_CITY_HALL", "FAIRWAY"],
     ("Fairway Station", "Conestoga Station"), 10),
    ("201", "201", "iXpress Fischer-Hallman", 3,
     ["UW_STATION", "UNIV_KING", "COLUMBIA_KING", "CONESTOGA"],
     ("Conestoga", "University of Waterloo"), 15),
    ("301", "301", "ION", 0,
     ["CONESTOGA", "UW_STATION", "LAURIER_PARK", "PUBLIC_SQUARE", "GRAND_RIVER_HOSP",
      "KITCHENER_CITY_HALL", "FAIRWAY"],
     ("Fairway", "Conestoga"), 10),
    ("9", "9", "Lakeshore", 3,
     ["PUBLIC_SQUARE", "ALBERT_SEAGRAM", "PHILLIP_COLUMBIA"],
     ("Lakeshore", "Waterloo Public Square"), 30),
]

FIRST_TRIP = 6 * 60   # minutes after midnight
LAST_TRIP = 23 * 60 + 30
MINUTES_BETWEEN_STOPS = 3


def hhmmss(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}:00"


def write(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("agency.txt", ["agency_id", "agency_name", "agency_url", "agency_timezone"],
          [("SAMPLE", "Sample data (not GRT)", "https://example.com", "America/Toronto")])
    write("stops.txt",
          ["stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon", "wheelchair_boarding"],
          STOPS)
    write("routes.txt",
          ["route_id", "route_short_name", "route_long_name", "route_type"],
          [(r[0], r[1], r[2], r[3]) for r in ROUTES])
    write("calendar.txt",
          ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
           "saturday", "sunday", "start_date", "end_date"],
          [("WKDY", 1, 1, 1, 1, 1, 0, 0, "20260101", "20271231"),
           ("WKND", 0, 0, 0, 0, 0, 1, 1, "20260101", "20271231")])

    trips, stop_times = [], []
    for route_id, _, _, _, pattern, headsigns, headway in ROUTES:
        for service_id, gap in (("WKDY", headway), ("WKND", headway * 2)):
            for direction, stops in enumerate((pattern, list(reversed(pattern)))):
                for start in range(FIRST_TRIP, LAST_TRIP + 1, gap):
                    trip_id = f"{route_id}-{service_id}-{direction}-{hhmmss(start)[:5].replace(':', '')}"
                    trips.append((route_id, service_id, trip_id, headsigns[direction], direction, 1))
                    for seq, stop_id in enumerate(stops, start=1):
                        t = hhmmss(start + (seq - 1) * MINUTES_BETWEEN_STOPS)
                        stop_times.append((trip_id, t, t, stop_id, seq))

    write("trips.txt",
          ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id",
           "wheelchair_accessible"], trips)
    write("stop_times.txt",
          ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"], stop_times)
    print(f"Wrote {len(trips)} trips and {len(stop_times)} stop times to {OUT}")


if __name__ == "__main__":
    main()
