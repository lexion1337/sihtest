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

_fastapi = _app.app


async def app(scope, receive, send):
    """ASGI entry point, with one defensive path fix.

    vercel.json uses `routes`, which proxies and preserves the visitor's path.
    If it is ever switched back to `rewrites`, the path is REPLACED by the
    destination and every request arrives as "/api/index" -- which matches no
    route and returns FastAPI's own 404 on every page. That happened once and
    the failure is silent and confusing, because the app is running perfectly
    and still answers nothing.

    So: if the mount path arrives instead of the real one, strip it. The check
    is deliberately narrow -- it rewrites only this exact prefix, and never
    touches a path the app could legitimately serve.
    """
    if scope.get("type") in ("http", "websocket"):
        path = scope.get("path", "")
        if path == "/api/index" or path.startswith("/api/index/"):
            rest = path[len("/api/index"):]
            scope = dict(scope, path=rest or "/", raw_path=(rest or "/").encode())
    await _fastapi(scope, receive, send)
