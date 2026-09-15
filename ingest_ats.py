"""
ingest_ats.py -- fetch real job postings from public ATS job-board APIs.

Unlike scraper.py (still a stub), this is real and it works. Companies hiring
through Greenhouse, Lever or Ashby publish their open roles on documented,
unauthenticated JSON endpoints so that careers pages can be embedded
elsewhere. Reading them is the intended use, not scraping around anything.

    Greenhouse  https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
    Lever       https://api.lever.co/v0/postings/{token}?mode=json
    Ashby       https://api.ashbyhq.com/posting-api/job-board/{token}

Run:  python ingest_ats.py                 # all boards in data/boards.json
      python ingest_ats.py --dry-run       # fetch and report, write nothing
      python ingest_ats.py --only lever    # one ATS at a time

THE DATE SPLIT (the single most important thing in this file)
-------------------------------------------------------------
Lever `createdAt` and Ashby `publishedAt` are true creation timestamps. A
posting dated 2025-Q3 really was opened in 2025-Q3, so it can go in a
quarterly bin.

Greenhouse `updated_at` is LAST-MODIFIED. A role opened in 2025 and edited
last week reports as last week. Measured on Postman's board, all 64 postings
carried an updated_at inside a single quarter -- the field is not merely
noisy, it is degenerate for time-series purposes.

So every record carries:
    date_kind             "created" | "published" | "modified"
    time_series_eligible  true only when the date is a real creation date

Records with time_series_eligible=false are still ingested and still feed
skill extraction and the cross-sectional views. They are excluded from
quarterly bins in analysis.py, and the UI states the exclusion. This is a
deliberate design decision, not an oversight, and it is written down in three
places so it reads that way.

SCALE
-----
Boards come from data/boards.json. A failing board is logged and skipped, never
fatal, because with 40+ boards some token will always be stale. Requests are
sequential with a delay; we are a guest on someone else's API.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOARDS_PATH = os.path.join(HERE, "data", "boards.json")
OUT_PATH = os.path.join(HERE, "data", "postings_real.jsonl")

USER_AGENT = ("SkillDriftAnalyzer/0.1 (Smart India Hackathon 2026 student "
              "project, SIH26134; contact cocgamer450@gmail.com)")
REQUEST_DELAY_S = 1.5
TIMEOUT_S = 45

# Fields every record must carry to satisfy the pipeline contract.
REQUIRED = ("id", "title", "company", "location", "posted_date", "role",
            "description_text", "source")


# ------------------------------------------------------------------ helpers

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")


def clean_text(raw):
    """HTML -> plain text, keeping paragraph breaks so bullets stay readable.

    Order matters and got this wrong once. Greenhouse returns its content
    HTML-ESCAPED ("&lt;p&gt;"), so stripping tags before unescaping leaves the
    markup untouched and then turns it into visible text -- which is how
    "data-renderer-mark" and "content-intro" ended up looking like skill
    candidates. Unescape first, then strip, then unescape entities that were
    nested inside the markup.
    """
    if not raw:
        return ""
    t = html.unescape(raw)                       # escaped markup -> real markup
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h[1-6]|/tr)\s*/?>", "\n", t)
    t = _TAG.sub(" ", t)                         # now the tags are really gone
    t = html.unescape(t)                         # &amp;, &nbsp; inside the text
    t = t.replace(" ", " ")
    t = _WS.sub(" ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return "\n".join(line.strip() for line in t.split("\n")).strip()


def iso_from_epoch_ms(ms):
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000.0, dt.timezone.utc).date().isoformat()
    except Exception:
        return None


def iso_from_string(s):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    return m.group(0) if m else None


# ------------------------------------------------------- role classification

# Conservative title rules mapping real postings onto the three roles the rest
# of the project measures. Anything we are not confident about becomes
# "Other (unclassified)" rather than being forced into a bucket -- a wrong role
# label would corrupt every share computed for that role. The unclassified
# records are still ingested: they are real evidence and still drill-downable.
ROLE_RULES = [
    ("Data Analyst", [
        r"\bdata analyst\b", r"\bbusiness intelligence\b", r"\bbi analyst\b",
        r"\banalytics? (manager|lead|associate|specialist)\b",
        r"\binsights? analyst\b", r"\bdecision scien",
        r"\breporting analyst\b", r"\bmis\b",
    ], [r"\bengineer\b", r"\bscientist\b"]),

    ("Business Analyst", [
        r"\bbusiness analyst\b", r"\bproduct analyst\b",
        r"\bprocess analyst\b", r"\bfunctional analyst\b",
        r"\bbusiness systems analyst\b",
    ], []),

    ("Backend Developer", [
        r"\bback[ -]?end\b", r"\bserver[ -]side\b", r"\bplatform engineer\b",
        r"\bsde\b", r"\bsoftware development engineer\b",
        # Deliberately NOT matching language names (java/python/golang/node).
        # Those are also skills we later MEASURE, so using them to assign a
        # role would let a change in that skill's prevalence move both the
        # numerator and who enters the denominator. Verified to fire zero
        # times on the current corpus: removing it costs nothing today and
        # prevents the circularity as more boards are added.
        r"\bapi engineer\b", r"\binfrastructure engineer\b",
        r"\bsoftware engineer\b",
    ], [r"\bfront[ -]?end\b", r"\bmobile\b", r"\bandroid\b", r"\bios\b",
        r"\bqa\b", r"\bsdet\b", r"\bdata engineer\b", r"\bml engineer\b"]),
]

UNCLASSIFIED = "Other (unclassified)"


def classify_role(title):
    t = (title or "").lower()
    for role, includes, excludes in ROLE_RULES:
        if any(re.search(p, t) for p in includes):
            if not any(re.search(p, t) for p in excludes):
                return role
    return UNCLASSIFIED


# --------------------------------------------------------------- per-ATS map

def from_greenhouse(board, payload, fetched_at):
    out = []
    for j in payload.get("jobs", []):
        text = clean_text(j.get("content", ""))
        date = iso_from_string(j.get("updated_at"))
        if not date:
            continue                      # unusable date -> drop, never guess
        out.append({
            "id": "greenhouse-%s-%s" % (board["token"], j.get("id")),
            "title": (j.get("title") or "").strip(),
            "company": board.get("company") or board["token"],
            "location": ((j.get("location") or {}).get("name") or "").strip() or "Unspecified",
            "posted_date": date,
            "role": classify_role(j.get("title")),
            "description_text": text,
            "source": "greenhouse",
            # --- the date split ---
            "date_kind": "modified",
            "time_series_eligible": False,
            "date_note": "Greenhouse updated_at is last-modified, not creation date",
            # --- provenance ---
            "board_token": board["token"],
            "url": j.get("absolute_url"),
            "fetched_at": fetched_at,
        })
    return out


def from_lever(board, payload, fetched_at):
    out = []
    for j in payload:
        text = clean_text(j.get("descriptionPlain") or j.get("description") or "")
        date = iso_from_epoch_ms(j.get("createdAt"))
        if not date:
            continue
        cats = j.get("categories") or {}
        out.append({
            "id": "lever-%s-%s" % (board["token"], j.get("id")),
            "title": (j.get("text") or "").strip(),
            "company": board.get("company") or board["token"],
            "location": (cats.get("location") or "").strip() or "Unspecified",
            "posted_date": date,
            "role": classify_role(j.get("text")),
            "description_text": text,
            "source": "lever",
            "date_kind": "created",
            "time_series_eligible": True,
            "date_note": "Lever createdAt is a true creation timestamp",
            "board_token": board["token"],
            "url": j.get("hostedUrl"),
            "fetched_at": fetched_at,
        })
    return out


def from_ashby(board, payload, fetched_at):
    out = []
    for j in payload.get("jobs", []):
        text = clean_text(j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        date = iso_from_string(j.get("publishedAt") or j.get("updatedAt"))
        if not date:
            continue
        out.append({
            "id": "ashby-%s-%s" % (board["token"], j.get("id")),
            "title": (j.get("title") or "").strip(),
            "company": board.get("company") or board["token"],
            "location": (j.get("location") or "").strip() or "Unspecified",
            "posted_date": date,
            "role": classify_role(j.get("title")),
            "description_text": text,
            "source": "ashby",
            "date_kind": "published",
            "time_series_eligible": True,
            "date_note": "Ashby publishedAt is a true publication timestamp",
            "board_token": board["token"],
            "url": j.get("jobUrl"),
            "fetched_at": fetched_at,
        })
    return out


ADAPTERS = {
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true", from_greenhouse),
    "lever":      ("https://api.lever.co/v0/postings/%s?mode=json", from_lever),
    "ashby":      ("https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=false", from_ashby),
}


# ------------------------------------------------------------------ ingest

def ingest_board(board, fetched_at):
    """Fetch one board. Returns (records, report). Never raises."""
    ats, token = board["ats"], board["token"]
    rep = {"ats": ats, "token": token, "company": board.get("company", token),
           "fetched": 0, "kept": 0, "dropped_no_date": 0, "empty_text": 0,
           "error": None, "roles": {}}
    if ats not in ADAPTERS:
        rep["error"] = "unknown ats %r" % ats
        return [], rep

    url_tpl, adapter = ADAPTERS[ats]
    try:
        payload = fetch_json(url_tpl % token)
    except urllib.error.HTTPError as e:
        rep["error"] = "HTTP %s" % e.code
        return [], rep
    except Exception as e:
        rep["error"] = type(e).__name__ + ": " + str(e)[:90]
        return [], rep

    raw_n = len(payload.get("jobs", [])) if isinstance(payload, dict) else len(payload)
    rep["fetched"] = raw_n
    try:
        recs = adapter(board, payload, fetched_at)
    except Exception as e:
        rep["error"] = "parse failed: %s: %s" % (type(e).__name__, str(e)[:90])
        return [], rep

    rep["dropped_no_date"] = raw_n - len(recs)
    rep["empty_text"] = sum(1 for r in recs if not r["description_text"])
    rep["kept"] = len(recs)
    for r in recs:
        rep["roles"][r["role"]] = rep["roles"].get(r["role"], 0) + 1
    return recs, rep


def load_boards(path=BOARDS_PATH, only=None):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    boards = doc.get("boards", [])
    if only:
        boards = [b for b in boards if b["ats"] == only]
    return boards


def main():
    ap = argparse.ArgumentParser(description="Ingest real postings from ATS job boards")
    ap.add_argument("--boards", default=BOARDS_PATH)
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--only", choices=sorted(ADAPTERS), help="restrict to one ATS")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()

    boards = load_boards(args.boards, args.only)
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print("ingest_ats: %d board(s), fetched_at=%s" % (len(boards), fetched_at))
    print("-" * 78)

    all_recs, reports = [], []
    for i, b in enumerate(boards):
        recs, rep = ingest_board(b, fetched_at)
        reports.append(rep)
        status = ("ERROR " + rep["error"]) if rep["error"] else "ok"
        print("  %-11s %-14s fetched=%-4d kept=%-4d %s"
              % (rep["ats"], rep["token"], rep["fetched"], rep["kept"], status))
        if rep["roles"]:
            print("               roles: %s" % dict(sorted(
                rep["roles"].items(), key=lambda kv: -kv[1])))
        all_recs.extend(recs)
        if i < len(boards) - 1:
            time.sleep(REQUEST_DELAY_S)

    # A duplicate id would mean the same posting twice, which inflates shares.
    seen, deduped = set(), []
    for r in all_recs:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        deduped.append(r)
    n_dupes = len(all_recs) - len(deduped)

    missing = [(r["id"], [k for k in REQUIRED if k not in r])
               for r in deduped if any(k not in r for k in REQUIRED)]
    if missing:
        raise SystemExit("records missing required fields: %s" % missing[:3])

    print("-" * 78)
    ok_boards = sum(1 for r in reports if not r["error"])
    print("boards ok      : %d / %d" % (ok_boards, len(reports)))
    print("records        : %d (%d duplicate ids dropped)" % (len(deduped), n_dupes))
    by_source, by_elig, by_role = {}, {"eligible": 0, "excluded": 0}, {}
    for r in deduped:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_elig["eligible" if r["time_series_eligible"] else "excluded"] += 1
        by_role[r["role"]] = by_role.get(r["role"], 0) + 1
    print("by source      : %s" % by_source)
    print("time bins      : %d eligible, %d EXCLUDED (modified-date only)"
          % (by_elig["eligible"], by_elig["excluded"]))
    print("by role        : %s" % dict(sorted(by_role.items(), key=lambda kv: -kv[1])))
    empty = sum(1 for r in deduped if not r["description_text"])
    lens = sorted(len(r["description_text"]) for r in deduped)
    if lens:
        print("description len: min=%d median=%d max=%d | %d empty"
              % (lens[0], lens[len(lens) // 2], lens[-1], empty))

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in deduped:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\nwrote %d records -> %s" % (len(deduped), args.out))
    print("next: python pipeline.py")


if __name__ == "__main__":
    main()
