"""
run.py -- the single entry point. `python run.py` and the dashboard is up.

Does three things in order:
  1. generates data/postings.jsonl if it is missing
  2. rebuilds data/skills.db if it is missing or older than its inputs
  3. serves the dashboard on http://127.0.0.1:8000

No npm, no bundler, no Docker. Only fastapi + uvicorn are needed.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POSTINGS = os.path.join(HERE, "data", "postings.jsonl")
DB = os.path.join(HERE, "data", "skills.db")
INPUTS = [POSTINGS, os.path.join(HERE, "skills.py")]


def db_is_stale():
    if not os.path.exists(DB):
        return True, "database does not exist yet"
    db_mtime = os.path.getmtime(DB)
    for src in INPUTS:
        if os.path.exists(src) and os.path.getmtime(src) > db_mtime:
            return True, "%s changed since the last build" % os.path.basename(src)
    return False, ""


def prepare(force=False):
    if not os.path.exists(POSTINGS):
        print("[1/2] data/postings.jsonl missing -- generating seed corpus...")
        sys.path.insert(0, HERE)
        from tools import gen_seed
        gen_seed.main()
    else:
        print("[1/2] seed corpus present: data/postings.jsonl")

    stale, why = db_is_stale()
    if force or stale:
        print("[2/2] building data/skills.db (%s)..." % (why or "forced"))
        import pipeline
        pipeline.build()
    else:
        print("[2/2] database up to date: data/skills.db")


def main():
    ap = argparse.ArgumentParser(description="Skill Drift Analyzer")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--rebuild", action="store_true",
                    help="force a rebuild of the SQLite database before serving")
    ap.add_argument("--reload", action="store_true", help="uvicorn autoreload (development)")
    args = ap.parse_args()

    prepare(force=args.rebuild)

    try:
        import uvicorn
    except ImportError:
        print("\nuvicorn is not installed. Run:\n    pip install fastapi uvicorn\n")
        raise SystemExit(1)

    print("\n" + "=" * 66)
    print("  Skill Drift Analyzer  ->  http://%s:%d" % (args.host, args.port))
    print("  DEMO DATA: synthetic seed corpus. scraper.fetch() is still a stub.")
    print("  Ctrl+C to stop.")
    print("=" * 66 + "\n")

    uvicorn.run("app:app", host=args.host, port=args.port, reload=args.reload,
                log_level="warning")


if __name__ == "__main__":
    main()
