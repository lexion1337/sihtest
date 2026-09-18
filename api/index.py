"""
api/index.py -- Vercel serverless entry point.

Vercel's Python runtime looks for a module-level `app` here and serves it as
an ASGI application. Everything below exists to bridge two assumptions the
local project makes that a serverless host does not allow:

  1. THE FILESYSTEM IS READ-ONLY except /tmp. The SQLite database is a derived
     artifact built from the JSONL corpora at start-up, and it is deliberately
     never committed (CLAUDE.md: "The DB is a derived artifact... Never
     hand-edit it"). So it is rebuilt into /tmp here, once per cold start, and
     reused by every warm invocation on the same instance.

  2. app.py CONNECTS AT IMPORT TIME (`CON = pipeline.connect()`). The database
     therefore has to exist BEFORE app is imported, which is why the build runs
     above the import rather than inside a start-up hook.

Cold starts pay for the rebuild -- 747 postings through the extractor. Warm
invocations pay nothing. If that ever becomes the bottleneck, the fix is to
build the database at deploy time and ship it read-only, not to cache stale
numbers.

Local development does not use this file at all. `python run.py` is unchanged.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# /tmp is the only writable location on the host. Tell pipeline before anything
# imports it, so DB_PATH resolves there everywhere -- including inside app.py.
DB = os.path.join("/tmp", "skills.db")
os.environ.setdefault("SKILL_DRIFT_DB", DB)

import pipeline  # noqa: E402  (must follow the env var above)

if not os.path.exists(DB):
    # verbose=False: build chatter on a serverless host is noise in the logs
    # and is not read by anyone.
    pipeline.build(db_path=DB, verbose=False)

import app as _app  # noqa: E402  (must follow the build above)

app = _app.app
