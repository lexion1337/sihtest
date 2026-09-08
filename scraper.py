"""
scraper.py -- STUB. Real posting collection is NOT implemented yet.

This file exists to fix the interface now so that the rest of the pipeline
(pipeline.py -> skills.py -> analysis.py) does not have to change when the
real collector lands. Everything downstream reads data/postings.jsonl, so the
only contract that matters is the record shape returned by fetch().

STATUS: not implemented. fetch() raises NotImplementedError on purpose.
It must NEVER quietly return fabricated rows -- a stub that returns fake data
is how invented numbers end up on a slide. See the honesty rules in CLAUDE.md.

TODO (later session):
  * Target National Career Service (ncs.gov.in) first. It is a Government of
    India portal, which fits the Maharashtra problem statement, and its terms
    are friendlier than the commercial boards.
  * Then evaluate Naukri / Indeed. Check robots.txt and terms of service for
    each before writing a single request. If scraping is disallowed, use the
    official API or a licensed dataset instead -- do not just do it anyway.
  * Rate limit hard (>= 2s between requests), set a real User-Agent with a
    contact address, cache raw HTML to data/raw/ so re-parsing never needs a
    re-fetch, and make the whole thing resumable.
  * Deduplicate. The same requisition is reposted across boards and weeks;
    counting it twice inflates every share on the dashboard. Suggested key:
    (normalised company, normalised title, first 200 chars of description).
  * posted_date is the field the entire quarterly analysis hinges on. Many
    boards show "3 days ago" rather than a date. Resolve it to an absolute
    date at fetch time and record how it was resolved.
  * Set source to the actual origin ("ncs.gov.in", "naukri.com", ...) and
    never to "synthetic". The UI keys its demo-data banner off this field.
"""

# Roles the analysis currently supports. Keep in sync with the role values
# used in data/postings.jsonl.
SUPPORTED_ROLES = ["Data Analyst", "Backend Developer", "Business Analyst"]

# Record shape that fetch() must return, matching data/postings.jsonl exactly.
RECORD_FIELDS = ("id", "title", "company", "location", "posted_date", "role",
                 "description_text", "source")


def fetch(role: str, pages: int = 1) -> list[dict]:
    """Fetch live job postings for `role`.

    Args:
        role: one of SUPPORTED_ROLES.
        pages: number of result pages to walk.

    Returns:
        A list of dicts with exactly RECORD_FIELDS:
            id               stable unique string, prefixed by source
            title            posting title as shown on the board
            company          employer name
            location         city, state
            posted_date      ISO yyyy-mm-dd, resolved to an absolute date
            role             the normalised role bucket (one of SUPPORTED_ROLES)
            description_text plain text of the full posting body
            source           origin host, e.g. "ncs.gov.in". Never "synthetic".

    Raises:
        NotImplementedError: always, for now.
    """
    raise NotImplementedError(
        "scraper.fetch() is a stub. Live collection is not implemented yet; "
        "the dashboard is running on synthetic seed data from "
        "data/postings.jsonl. See the TODO at the top of scraper.py."
    )


def validate(records: list[dict]) -> list[dict]:
    """Check records against the pipeline contract before they are written.

    Useful now: whatever the real fetch() ends up doing, it can pipe through
    this and fail loudly rather than writing rows the pipeline cannot read.
    """
    for i, rec in enumerate(records):
        missing = [f for f in RECORD_FIELDS if f not in rec]
        if missing:
            raise ValueError("record %d missing fields: %s" % (i, missing))
        if rec["source"] == "synthetic":
            raise ValueError(
                "record %d claims source='synthetic' but came from the scraper; "
                "that label is reserved for generated seed data" % i)
        if rec["role"] not in SUPPORTED_ROLES:
            raise ValueError("record %d has unsupported role %r" % (i, rec["role"]))
        d = rec["posted_date"]
        if not (isinstance(d, str) and len(d) == 10 and d[4] == "-" and d[7] == "-"):
            raise ValueError("record %d posted_date %r is not ISO yyyy-mm-dd" % (i, d))
    return records


if __name__ == "__main__":
    print(__doc__)
    try:
        fetch("Data Analyst", pages=1)
    except NotImplementedError as exc:
        print("fetch() ->", exc)
