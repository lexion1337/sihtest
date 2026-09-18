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


# ---------------------------------------------------------------- path fix
# Vercel's "rewrites" REPLACE the request path with the destination, so every
# request arrives at the app as "/api/index" -- matching no route, and
# returning FastAPI's own 404 on every page and every endpoint. The app is
# running correctly the whole time, which is what makes it hard to spot.
#
# The obvious alternative, builds + routes, proxies and preserves the path,
# but never finished building here. So the path is repaired inside the app.
#
# This is deliberately a Starlette http middleware rather than an ASGI wrapper
# function: it keeps the exported `app` a real FastAPI instance, which is what
# the host introspects to decide how to serve it. BaseHTTPMiddleware runs above
# the router, so editing scope["path"] here still decides which route matches.
#
# The prefix test is narrow enough that it can never shadow a path the app
# would otherwise serve.
@_fastapi.middleware("http")
async def _strip_mount_path(request, call_next):
    path = request.scope.get("path", "")
    if path == "/api/index" or path.startswith("/api/index/"):
        fixed = path[len("/api/index"):] or "/"
        request.scope["path"] = fixed
        request.scope["raw_path"] = fixed.encode()
    return await call_next(request)


app = _fastapi
