"""
tools/probe_boards.py -- test candidate ATS board tokens before adding them.

Probe before you build. A token either returns jobs or it does not, and the
answer takes one request; guessing and then debugging an ingest run does not.

For each candidate this reports jobs found, how many carry a usable CREATION
date, and how many look India-based -- because those, not the raw count, are
what raise the usable column in analysis.collection_yield().

Prefer Lever: its createdAt is a true creation date. Greenhouse exposes only
updated_at, so its records cannot enter the historical series (they still feed
the cross-sectional views, and can join a prospective series later).

Run:  python tools/probe_boards.py
      python tools/probe_boards.py --write      (append verified to boards.json)
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

BOARDS_PATH = os.path.join(HERE, "data", "boards.json")
UA = ("SkillDriftAnalyzer/0.1 (Smart India Hackathon 2026 student project, "
      "SIH26134; contact cocgamer450@gmail.com)")
DELAY = 1.5

INDIA_HINTS = ("india", "bengaluru", "bangalore", "mumbai", "pune", "delhi",
               "gurugram", "gurgaon", "noida", "hyderabad", "chennai", "kolkata",
               "ahmedabad", "jaipur", "kochi", "surat", "indore", "chandigarh",
               "coimbatore", "thane", "nagpur", "remote - in")

# Indian product-tech companies plausibly on a public board. Unverified: that
# is the point of this script.
CANDIDATES = [
    ("lever", "razorpay"), ("lever", "sharechat"), ("lever", "groww"),
    ("lever", "slice"), ("lever", "cars24"), ("lever", "bharatpe"),
    ("lever", "unacademy"), ("lever", "zetwerk"), ("lever", "moglix"),
    ("lever", "ninjacart"), ("lever", "porter"), ("lever", "zepto"),
    ("lever", "licious"), ("lever", "rupeek"), ("lever", "jupiter"),
    ("lever", "khatabook"), ("lever", "urbancompany"), ("lever", "mindtickle"),
    ("lever", "leadsquared"), ("lever", "capillarytech"), ("lever", "clevertap"),
    ("lever", "yellowmessenger"), ("lever", "gupshup"), ("lever", "exotel"),
    ("lever", "plivo"), ("lever", "whatfix"), ("lever", "hasura"),
    ("lever", "browserstack"), ("lever", "innovaccer"), ("lever", "darwinbox"),
    ("lever", "chargebee"), ("lever", "dream11"), ("lever", "phonepe"),
    ("greenhouse", "razorpay"), ("greenhouse", "flipkart"),
    ("greenhouse", "freshworks"), ("greenhouse", "browserstack"),
    ("greenhouse", "chargebee"), ("greenhouse", "hasura"),
    ("greenhouse", "zomato"), ("greenhouse", "swiggy"),
]

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/%s?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=false",
}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe(ats, token):
    out = {"ats": ats, "token": token, "jobs": 0, "dated": 0, "india": 0,
           "error": None, "date_kind": None, "sample_titles": [],
           "sample_locations": []}
    try:
        payload = fetch(URLS[ats] % token)
    except urllib.error.HTTPError as e:
        out["error"] = "HTTP %s" % e.code
        return out
    except Exception as e:
        out["error"] = type(e).__name__
        return out

    jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        out["error"] = "unexpected shape"
        return out
    out["jobs"] = len(jobs)
    out["date_kind"] = {"lever": "created", "ashby": "published",
                        "greenhouse": "modified"}[ats]

    for j in jobs:
        if ats == "lever":
            if j.get("createdAt"):
                out["dated"] += 1
            loc = ((j.get("categories") or {}).get("location") or "")
        elif ats == "ashby":
            if j.get("publishedAt"):
                out["dated"] += 1
            loc = j.get("location") or ""
        else:
            loc = ((j.get("location") or {}).get("name") or "")
            # Greenhouse has no creation date at all; dated stays 0 on purpose.
        if any(h in loc.lower() for h in INDIA_HINTS):
            out["india"] += 1
        if len(out["sample_titles"]) < 4:
            title = j.get("text") or j.get("title") or ""
            out["sample_titles"].append(title[:56])
            out["sample_locations"].append(str(loc)[:36])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="append verified boards to data/boards.json")
    args = ap.parse_args()

    print("probing %d candidate tokens (%.1fs apart, polite)\n" % (len(CANDIDATES), DELAY))
    print("  %-11s %-16s %6s %6s %6s  %s"
          % ("ATS", "TOKEN", "JOBS", "DATED", "INDIA", "STATUS"))
    print("  " + "-" * 72)

    live = []
    for i, (ats, token) in enumerate(CANDIDATES):
        r = probe(ats, token)
        status = r["error"] or ("ok (%s date)" % r["date_kind"])
        print("  %-11s %-16s %6s %6s %6s  %s"
              % (ats, token, r["jobs"] or "-", r["dated"] or "-",
                 r["india"] or "-", status))
        if not r["error"] and r["jobs"]:
            live.append(r)
            # LIVENESS IS NOT IDENTITY. A token can belong to a completely
            # different company: "porter" on Lever is a US healthcare staffing
            # firm, not the Indian logistics company, and it returned 26
            # nurse-practitioner vacancies. Print evidence so a human can tell.
            for t, l in zip(r["sample_titles"], r["sample_locations"]):
                print("                 e.g. %-56s | %s" % (t, l))
        if i < len(CANDIDATES) - 1:
            time.sleep(DELAY)

    print()
    print("=" * 76)
    print("LIVE BOARDS: %d of %d candidates" % (len(live), len(CANDIDATES)))
    print("=" * 76)
    tot_jobs = sum(r["jobs"] for r in live)
    tot_dated = sum(r["dated"] for r in live)
    tot_india = sum(r["india"] for r in live)
    print("  jobs available     : %d" % tot_jobs)
    print("  with creation date : %d  (only these can enter the historical series)"
          % tot_dated)
    print("  India-located      : %d" % tot_india)
    print()
    print("  CHECK THE SAMPLE TITLES ABOVE before adding any board. A 200")
    print("  response proves the token EXISTS, not that it belongs to the")
    print("  company you meant.")
    print()
    print("  Adding boards raises 'collected'. Only the DATED and India-located")
    print("  ones raise what analysis.collection_yield() calls")
    print("  'historically_eligible', and none of them establish that the jobs")
    print("  are reachable by the trainees a curriculum serves.")

    if args.write and live:
        doc = json.load(open(BOARDS_PATH, encoding="utf-8"))
        have = {(b["ats"], b["token"]) for b in doc["boards"]}
        added = 0
        for r in live:
            key = (r["ats"], r["token"])
            if key in have:
                continue
            doc["boards"].append({
                "ats": r["ats"], "token": r["token"],
                "company": r["token"].title(), "verified": True,
                "probed_jobs": r["jobs"], "probed_on": dt.date.today().isoformat(),
            })
            added += 1
        with open(BOARDS_PATH, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("\n  wrote %d new board(s) to data/boards.json" % added)
        print("  next: python ingest_ats.py && python pipeline.py && python verify.py")


if __name__ == "__main__":
    main()
