"""
pipeline.py -- rebuilds data/skills.db from one or more JSONL corpora.

The database is a DERIVED artifact. Delete it any time; this rebuilds it.
Never hand-edit it -- edit the JSONL (or the ingesters) and re-run.

MULTI-SOURCE
------------
By default the build loads EVERY data/postings*.jsonl file it finds, so
dropping data/postings_real.jsonl next to data/postings.jsonl is enough to get
it into the corpus. Each record keeps its own `source` field end to end:
JSONL -> postings.source -> posting_skills.source -> meta.sources -> the API
-> the provenance banner in the UI.

Nothing anywhere hardcodes "this corpus is synthetic". The banner is computed
from the source counts of what was actually loaded (see analysis.provenance),
so all-synthetic, mixed and all-real each render honestly.

Run:  python pipeline.py
"""

import datetime as dt
import glob
import threading
import json
import os
import sqlite3

import locations as loc_mod
import skills as skills_mod

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
# Kept for backward compatibility: callers that want only the seed corpus.
POSTINGS_PATH = os.path.join(DATA_DIR, "postings.jsonl")
# What build() loads when it is not told otherwise.
POSTINGS_GLOB = os.path.join(DATA_DIR, "postings*.jsonl")
# The database is a DERIVED artifact and is never committed. On a read-only
# host (a serverless deploy, for example) the project directory cannot be
# written to, so the path is overridable and the DB is rebuilt into a writable
# location at start-up. Locally this env var is unset and nothing changes.
DB_PATH = os.environ.get("SKILL_DRIFT_DB") or os.path.join(DATA_DIR, "skills.db")

SCHEMA = """
DROP TABLE IF EXISTS postings;
DROP TABLE IF EXISTS posting_skills;
DROP TABLE IF EXISTS meta;

CREATE TABLE postings (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    location     TEXT NOT NULL,
    posted_date  TEXT NOT NULL,   -- ISO yyyy-mm-dd
    quarter      TEXT NOT NULL,   -- yyyy-Qn, derived from posted_date
    role         TEXT NOT NULL,
    source       TEXT NOT NULL,   -- "synthetic" for seed data, else the ingest source
    -- The date split. Greenhouse only exposes a last-modified timestamp, which
    -- cannot support a quarterly bin (see ingest_ats.py). Such records are
    -- still ingested and still feed skill extraction; they are excluded from
    -- the time series and analysis.py enforces that.
    date_kind    TEXT NOT NULL,   -- created | published | modified
    ts_eligible  INTEGER NOT NULL,-- 1 = may appear in quarterly bins
    -- Normalised from the raw location string by locations.py. The PS asks
    -- for demand by location and district-level plans; the raw strings spell
    -- one city three ways, so they must collapse before any per-city share.
    city         TEXT NOT NULL,
    state        TEXT,
    country      TEXT,
    n_skills     INTEGER NOT NULL
);

CREATE TABLE posting_skills (
    posting_id   TEXT NOT NULL,
    skill        TEXT NOT NULL,
    role         TEXT NOT NULL,
    posted_date  TEXT NOT NULL,
    quarter      TEXT NOT NULL,
    source       TEXT NOT NULL,
    ts_eligible  INTEGER NOT NULL,
    PRIMARY KEY (posting_id, skill),
    FOREIGN KEY (posting_id) REFERENCES postings(id)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE INDEX idx_ps_role_quarter ON posting_skills(role, quarter);
CREATE INDEX idx_ps_skill        ON posting_skills(skill);
CREATE INDEX idx_p_role_quarter  ON postings(role, quarter);
CREATE INDEX idx_p_city          ON postings(city);
"""


def quarter_of(iso_date):
    y, m, _d = (int(x) for x in iso_date.split("-"))
    return "%d-Q%d" % (y, (m - 1) // 3 + 1)


REQUIRED_FIELDS = ("id", "title", "company", "location", "posted_date",
                   "role", "description_text", "source")


def resolve_paths(postings_path=None):
    """Normalise the many ways a caller can name corpora into a list of paths.

    None -> every data/postings*.jsonl on disk, sorted (postings.jsonl first,
    then postings_real.jsonl, etc). A str/PathLike -> that one file. Any
    iterable -> those files, in the given order.
    """
    if postings_path is None:
        paths = sorted(glob.glob(POSTINGS_GLOB))
        if not paths:
            raise FileNotFoundError(
                "no corpora matched %s -- run tools/gen_seed.py first" % POSTINGS_GLOB)
        return paths
    if isinstance(postings_path, (str, os.PathLike)):
        return [os.fspath(postings_path)]
    return [os.fspath(p) for p in postings_path]


def read_one(path):
    """Parse a single JSONL corpus, validating the record contract."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("%s:%d is not valid JSON: %s" % (path, lineno, exc))
            missing = [k for k in REQUIRED_FIELDS if k not in rec]
            if missing:
                raise ValueError("%s:%d missing fields %s" % (path, lineno, missing))
            rows.append(rec)
    return rows


def read_postings(postings_path=None):
    """Merged records across every requested corpus.

    Accepts None (discover all), a single path, or a list of paths. The old
    single-path call signature still works unchanged.
    """
    out = []
    for p in resolve_paths(postings_path):
        out.extend(read_one(p))
    return out


def build(db_path=DB_PATH, postings_path=None, verbose=True):
    """Rebuild the database from one or more corpora.

    postings_path: None (all data/postings*.jsonl), a single path, or a list.
    """
    paths = resolve_paths(postings_path)

    records, per_file, origin_of = [], [], {}
    for p in paths:
        rows = read_one(p)
        for r in rows:
            # A duplicate id across corpora is a real data problem (the same
            # job ingested twice would inflate every share downstream), so
            # fail loudly and name both files rather than silently dedupe.
            if r["id"] in origin_of:
                raise ValueError(
                    "duplicate posting id %r appears in both %s and %s"
                    % (r["id"], os.path.basename(origin_of[r["id"]]), os.path.basename(p)))
            origin_of[r["id"]] = p
        per_file.append((p, len(rows), sorted({r["source"] for r in rows})))
        records.extend(rows)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    p_rows, s_rows = [], []
    for rec in records:
        # Duplicate ids were already rejected across corpora above.
        q = quarter_of(rec["posted_date"])
        found = skills_mod.extract_skills(rec["description_text"])
        # Seed records predate the date-split fields; their posted_date is a
        # true creation date by construction, so they default to eligible.
        date_kind = rec.get("date_kind", "created")
        eligible = 1 if rec.get("time_series_eligible", True) else 0
        place = loc_mod.normalise(rec["location"])
        p_rows.append((rec["id"], rec["title"], rec["company"], rec["location"],
                       rec["posted_date"], q, rec["role"], rec["source"],
                       date_kind, eligible, place["city"], place["state"],
                       place["country"], len(found)))
        for sk in found:
            s_rows.append((rec["id"], sk, rec["role"], rec["posted_date"], q,
                           rec["source"], eligible))

    con.executemany("INSERT INTO postings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", p_rows)
    con.executemany("INSERT INTO posting_skills VALUES (?,?,?,?,?,?,?)", s_rows)

    sources = {}
    for r in p_rows:
        sources[r[7]] = sources.get(r[7], 0) + 1
    n_excluded = sum(1 for r in p_rows if r[9] == 0)
    n_unknown_city = sum(1 for r in p_rows if r[10] == "Unknown")
    excluded_by_source = {}
    for r in p_rows:
        if r[9] == 0:
            excluded_by_source[r[7]] = excluded_by_source.get(r[7], 0) + 1
    meta = {
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "n_postings": str(len(p_rows)),
        "n_skill_mentions": str(len(s_rows)),
        "skill_dict_size": str(skills_mod.skill_count()),
        "sources": json.dumps(sources),
        "source_files": json.dumps([os.path.basename(p) for p, _n, _s in per_file]),
        "n_ts_excluded": str(n_excluded),
        "n_unknown_city": str(n_unknown_city),
        "ts_excluded_by_source": json.dumps(excluded_by_source),
        "date_min": min(r[4] for r in p_rows) if p_rows else "",
        "date_max": max(r[4] for r in p_rows) if p_rows else "",
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", sorted(meta.items()))
    con.commit()
    con.close()

    if verbose:
        print("built %s" % db_path)
        print("  corpora loaded  : %d" % len(per_file))
        for p, n, srcs in per_file:
            print("      %-28s %4d postings  source=%s"
                  % (os.path.basename(p), n, ",".join(srcs)))
        print("  postings        : %d" % len(p_rows))
        print("  skill mentions  : %d (%.1f per posting)"
              % (len(s_rows), len(s_rows) / max(1, len(p_rows))))
        print("  source counts   : %s" % sources)
        if n_excluded:
            print("  time-series     : %d rows EXCLUDED (modified-date only) %s"
                  % (n_excluded, excluded_by_source))
        print("  date range      : %s .. %s" % (meta["date_min"], meta["date_max"]))
    return meta


_LOCAL = threading.local()


class _ThreadLocalConnection:
    """One real SQLite connection PER THREAD, behind a connection-like object.

    FastAPI runs synchronous endpoints in a threadpool, so a single shared
    sqlite3 connection is used by several threads at once. sqlite3 does not
    serialise that: two threads stepping cursors on the same connection can
    truncate each other's result sets.

    The symptom was ugly and intermittent. The dashboard fires four requests in
    parallel on load; sometimes analysis.roles() came back short, so
    _check_role could not find "Data Analyst" and the endpoint returned 404 on
    a role that plainly exists. Sequential curl never reproduced it. This would
    have failed at random during a live demo.

    Each thread gets its own connection. SQLite handles multi-connection reads
    fine, and this pipeline only ever reads through here.
    """

    def __init__(self, db_path):
        self._db_path = db_path

    def _con(self):
        con = getattr(_LOCAL, "con", None)
        if con is None or getattr(_LOCAL, "path", None) != self._db_path:
            con = sqlite3.connect(self._db_path, check_same_thread=False)
            con.row_factory = sqlite3.Row
            _LOCAL.con = con
            _LOCAL.path = self._db_path
        return con

    def execute(self, *a, **k):
        return self._con().execute(*a, **k)

    def executemany(self, *a, **k):
        return self._con().executemany(*a, **k)

    def commit(self):
        return self._con().commit()

    def close(self):
        con = getattr(_LOCAL, "con", None)
        if con is not None:
            con.close()
            _LOCAL.con = None


def connect(db_path=DB_PATH):
    """A read handle that is safe to use from several threads.

    Building the database if it is missing stays here so that any entry point
    -- run.py, analysis.py, verify.py -- works from a clean checkout.
    """
    if not os.path.exists(db_path):
        build(db_path, verbose=False)
    return _ThreadLocalConnection(db_path)


if __name__ == "__main__":
    build()
