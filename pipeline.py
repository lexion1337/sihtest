"""
pipeline.py -- rebuilds data/skills.db from data/postings.jsonl.

The database is a DERIVED artifact. Delete it any time; this rebuilds it.
Never hand-edit it -- edit the JSONL (or the scraper) and re-run.

Run:  python pipeline.py
"""

import datetime as dt
import json
import os
import sqlite3

import skills as skills_mod

HERE = os.path.dirname(os.path.abspath(__file__))
POSTINGS_PATH = os.path.join(HERE, "data", "postings.jsonl")
DB_PATH = os.path.join(HERE, "data", "skills.db")

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
    source       TEXT NOT NULL,   -- "synthetic" for seed data, else the scrape source
    n_skills     INTEGER NOT NULL
);

CREATE TABLE posting_skills (
    posting_id   TEXT NOT NULL,
    skill        TEXT NOT NULL,
    role         TEXT NOT NULL,
    posted_date  TEXT NOT NULL,
    quarter      TEXT NOT NULL,
    source       TEXT NOT NULL,
    PRIMARY KEY (posting_id, skill),
    FOREIGN KEY (posting_id) REFERENCES postings(id)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE INDEX idx_ps_role_quarter ON posting_skills(role, quarter);
CREATE INDEX idx_ps_skill        ON posting_skills(skill);
CREATE INDEX idx_p_role_quarter  ON postings(role, quarter);
"""


def quarter_of(iso_date):
    y, m, _d = (int(x) for x in iso_date.split("-"))
    return "%d-Q%d" % (y, (m - 1) // 3 + 1)


def read_postings(path=POSTINGS_PATH):
    required = ("id", "title", "company", "location", "posted_date",
                "role", "description_text", "source")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            missing = [k for k in required if k not in rec]
            if missing:
                raise ValueError("%s:%d missing fields %s" % (path, lineno, missing))
            rows.append(rec)
    return rows


def build(db_path=DB_PATH, postings_path=POSTINGS_PATH, verbose=True):
    records = read_postings(postings_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    p_rows, s_rows = [], []
    seen_ids = set()
    for rec in records:
        if rec["id"] in seen_ids:
            raise ValueError("duplicate posting id: %s" % rec["id"])
        seen_ids.add(rec["id"])
        q = quarter_of(rec["posted_date"])
        found = skills_mod.extract_skills(rec["description_text"])
        p_rows.append((rec["id"], rec["title"], rec["company"], rec["location"],
                       rec["posted_date"], q, rec["role"], rec["source"], len(found)))
        for sk in found:
            s_rows.append((rec["id"], sk, rec["role"], rec["posted_date"], q, rec["source"]))

    con.executemany("INSERT INTO postings VALUES (?,?,?,?,?,?,?,?,?)", p_rows)
    con.executemany("INSERT INTO posting_skills VALUES (?,?,?,?,?,?)", s_rows)

    sources = {}
    for r in p_rows:
        sources[r[7]] = sources.get(r[7], 0) + 1
    meta = {
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "n_postings": str(len(p_rows)),
        "n_skill_mentions": str(len(s_rows)),
        "skill_dict_size": str(skills_mod.skill_count()),
        "sources": json.dumps(sources),
        "date_min": min(r[4] for r in p_rows) if p_rows else "",
        "date_max": max(r[4] for r in p_rows) if p_rows else "",
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", sorted(meta.items()))
    con.commit()
    con.close()

    if verbose:
        print("built %s" % db_path)
        print("  postings        : %d" % len(p_rows))
        print("  skill mentions  : %d (%.1f per posting)"
              % (len(s_rows), len(s_rows) / max(1, len(p_rows))))
        print("  sources         : %s" % sources)
        print("  date range      : %s .. %s" % (meta["date_min"], meta["date_max"]))
    return meta


def connect(db_path=DB_PATH):
    """Open the DB read-only-ish, building it first if it does not exist."""
    if not os.path.exists(db_path):
        build(db_path, verbose=False)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


if __name__ == "__main__":
    build()
