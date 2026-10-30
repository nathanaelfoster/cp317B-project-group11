"""Start the prototype: set up the database if needed, start the collector, serve the app.

    python run.py                 # sample mode, http://localhost:5000
    python run.py --reset         # rebuild the sample database
    WIMI_MODE=live python run.py  # use GRT's live feeds (see README)
"""
import argparse
import logging

from app import config, db
from app.api import create_app
from app.collector import Collector, collect_once, default_source
from app.gtfs_loader import load_gtfs
from app.simulate import seed_history


def setup(reset=False):
    if reset and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    conn = db.connect()
    db.init_db(conn)
    if conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 0:
        if config.MODE == "sample":
            load_gtfs(conn, config.SAMPLE_GTFS_DIR)
            n = seed_history(conn)
            logging.info("Seeded %d sample historical arrivals", n)
        else:
            load_gtfs(conn, config.GRT_STATIC_URL)
    collect_once(conn, default_source())  # so the first page load has live data
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete and rebuild the database")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    setup(reset=args.reset)
    Collector().start()
    create_app().run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
