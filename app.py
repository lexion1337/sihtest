"""
app.py -- FastAPI routes and JSON API for the Skill Drift Analyzer.

The API is deliberately thin: every endpoint is a straight pass-through of
what analysis.py computed. No numbers are produced here.

/api/postings is the point of the whole design -- it lets anyone click a
percentage in the UI and read the actual postings behind it. If a number
cannot be drilled into, it should not be on screen.
"""

import os

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import analysis
import phrases
import pipeline
import skills

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")

app = FastAPI(title="Skill Drift Analyzer", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CON = pipeline.connect()
CURRICULUM = analysis.load_curriculum()


@app.middleware("http")
async def no_store_api(request, call_next):
    """API responses must never be cached.

    The database is rebuilt between runs (python pipeline.py), so a cached
    response can show numbers that no longer exist -- and a stale 404 can make
    a working dashboard look broken, which is exactly what happened during
    development. For a project whose claim is that every number traces to a
    current record, serving a stale one is a correctness bug, not a nuisance.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


def _check_role(role):
    valid = analysis.roles(CON)
    if role not in valid:
        raise HTTPException(404, "unknown role %r; known roles: %s" % (role, valid))


# Three pages, one server. The split is a progressive-disclosure decision,
# recorded in FRONTEND_PLAN.md: a reader should never meet a term the previous
# layer did not teach them.
#
#   /          explains the project to someone with zero context. No statistics.
#   /dashboard the evidence: counts, sample sizes, plain-language verdicts.
#   /method    how we checked: p-values, corrections, audits, limits.
#
# The honesty rules apply identically on all three. Plain language on / is a
# presentation choice, never permission to drop a sample size or a caveat.


def _page(name):
    # no-store on the pages too, for the same reason as the API: the database
    # is rebuilt between runs and the pages are edited between demos. A browser
    # holding yesterday's HTML against today's numbers is the stale-data bug
    # this project already fixed once at the API layer.
    return FileResponse(os.path.join(STATIC_DIR, name),
                        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/")
def index():
    return _page("index.html")


@app.get("/dashboard")
def dashboard():
    return _page("dashboard.html")


@app.get("/method")
def method():
    return _page("method.html")


@app.get("/api/overview")
def api_overview():
    ov = analysis.overview(CON)
    ov["roles"] = analysis.roles(CON)
    ov["curriculum"] = {
        "name": CURRICULUM["name"],
        "version": CURRICULUM.get("version"),
        "source": CURRICULUM.get("source"),
        "source_note": CURRICULUM.get("source_note"),
        "n_subjects": CURRICULUM["n_subjects"],
        "n_skills_taught": len(CURRICULUM["taught_skills"]),
    }
    ov["scraper_implemented"] = False
    return ov


@app.get("/api/drift")
def api_drift(role: str = Query(...),
              top: int = Query(8, ge=1, le=30),
              rank_by: str = Query("latest", pattern="^(latest|change)$")):
    _check_role(role)
    d = analysis.drift(CON, role)
    chosen = analysis.top_skills(d, k=top, rank_by=rank_by)
    return {
        "role": d["role"],
        "n_postings": d["n_postings"],
        # Rows kept out of the quarterly bins because their date is only a
        # last-modified timestamp. The UI renders this as a design decision.
        "excluded_from_time_series": d["excluded_from_time_series"],
        "quarters": d["quarters"],
        "latest_quarter": d["latest_quarter"],
        "latest_n": d["latest_n"],
        "baseline_quarters": d["baseline_quarters"],
        "thresholds": d["thresholds"],
        "rank_by": rank_by,
        "n_skills_total": len(d["skills"]),
        "top": chosen,
    }


@app.get("/api/gap")
def api_gap(role: str = Query(...)):
    _check_role(role)
    return analysis.curriculum_gap(CON, role, CURRICULUM)


@app.get("/api/findings")
def api_findings(role: str = Query(...)):
    """Supported AND discarded drift alerts. Discarded ones are first-class."""
    _check_role(role)
    return analysis.findings(CON, role, CURRICULUM)


@app.get("/api/finding")
def api_finding(role: str = Query(...), skill: str = Query(...)):
    """Everything needed to state one finding honestly, in one payload."""
    _check_role(role)
    f = analysis.finding(CON, role, skill, CURRICULUM)
    if f is None:
        raise HTTPException(404, "skill %r not measured for role %r" % (skill, role))
    return f


@app.get("/api/sensitivity")
def api_sensitivity(role: str = Query(...)):
    """Which recommendations survive across plausible decision thresholds."""
    _check_role(role)
    return analysis.threshold_sensitivity(CON, role, CURRICULUM)


@app.get("/api/yield")
def api_yield():
    """Collection funnel: collected -> unique -> in role -> dated -> usable."""
    return analysis.collection_yield(CON)


@app.get("/api/phrases")
def api_phrases(min_postings: int = Query(3, ge=1, le=50),
                min_employers: int = Query(2, ge=1, le=20),
                limit: int = Query(40, ge=1, le=200)):
    """Dictionary-absent candidate terms, for human adjudication.

    Discovery only. Nothing here is counted anywhere else on the site and
    nothing is added to the dictionary by this endpoint.
    """
    return phrases.discover(pipeline.read_postings(),
                            min_postings=min_postings,
                            min_employers=min_employers, limit=limit)


@app.get("/api/locations")
def api_locations(role: str = Query(None),
                  country: str = Query("India"),
                  top: int = Query(6, ge=1, le=20)):
    """Demand by location -- named explicitly in the problem statement, and
    the first step toward its district-level training plans."""
    if role:
        _check_role(role)
    return analysis.demand_by_location(CON, role=role, country=country,
                                       top_skills=top)


@app.get("/api/obsolete")
def api_obsolete(role: str = Query(...)):
    """The gap table reversed: what the curriculum teaches that demand does
    not ask for. Answers 'what should we stop funding'."""
    _check_role(role)
    return analysis.obsolete_courses(CON, role, CURRICULUM)


@app.get("/api/skills")
def api_skills(role: str = Query(...)):
    """Every skill measured for this role, not just the top N."""
    _check_role(role)
    d = analysis.drift(CON, role)
    return {"role": role, "latest_quarter": d["latest_quarter"],
            "latest_n": d["latest_n"], "skills": d["skills"]}


@app.get("/api/postings")
def api_postings(role: str = Query(...),
                 skill: str = Query(None),
                 quarter: str = Query(None),
                 limit: int = Query(25, ge=1, le=200)):
    """The evidence behind a number: the actual postings counted.

    With `skill` and `quarter` set, this returns exactly the postings that
    made up the numerator of that cell's percentage.
    """
    _check_role(role)
    params = [role]
    if skill:
        sql = ("SELECT p.* FROM postings p JOIN posting_skills s "
               "ON s.posting_id = p.id WHERE p.role = ? AND s.skill = ?")
        params.append(skill)
    else:
        sql = "SELECT p.* FROM postings p WHERE p.role = ?"
    if quarter:
        sql += " AND p.quarter = ?"
        params.append(quarter)

    total = CON.execute("SELECT COUNT(*) c FROM (%s)" % sql, params).fetchone()["c"]
    sql += " ORDER BY p.posted_date DESC LIMIT ?"
    params.append(limit)

    rows = []
    for r in CON.execute(sql, params):
        rows.append({
            "id": r["id"], "title": r["title"], "company": r["company"],
            "location": r["location"], "posted_date": r["posted_date"],
            "quarter": r["quarter"], "source": r["source"],
            "n_skills": r["n_skills"],
        })
    return {"role": role, "skill": skill, "quarter": quarter,
            "total_matching": total, "returned": len(rows), "postings": rows}


@app.get("/api/posting/{posting_id}")
def api_posting(posting_id: str, skill: str = Query(None)):
    """Full text of one posting, plus the skills extracted from it.

    With ?skill=, also returns the sentences that caused that skill to be
    counted, so the drawer can show WHY the posting entered the numerator.
    """
    row = CON.execute("SELECT * FROM postings WHERE id = ?", (posting_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "no posting %r" % posting_id)
    found = [r["skill"] for r in CON.execute(
        "SELECT skill FROM posting_skills WHERE posting_id = ? ORDER BY skill",
        (posting_id,))]
    # description_text lives in the JSONL, not the DB (the DB stores what we
    # measured, not the raw corpus). Look it up on demand.
    text = None
    for rec in pipeline.read_postings():
        if rec["id"] == posting_id:
            text = rec["description_text"]
            break
    out = {"posting": dict(row), "skills": found, "description_text": text}
    if skill:
        import skills as skills_mod
        out["match_sentences"] = skills_mod.match_sentences(text or "", skill)
        out["matched_skill"] = skill
    return out


@app.post("/api/extract")
def api_extract(payload: dict = Body(...)):
    """Run the extractor over TEXT THE VISITOR SUPPLIES, live.

    This exists to answer the question the click-through evidence cannot: not
    "are your numbers real" but "does your thing actually work, on text you
    have never seen". A judge can paste a job advertisement off their own phone
    and watch the same deterministic pass that produced every figure on the
    site run over it.

    Nothing here touches the corpus or any stored number, and nothing is
    written. It is the measurement instrument, exposed.

    It also returns the terms it could NOT match. A closed dictionary means an
    untracked skill is UNMEASURED, not absent, and the honest way to show that
    is to hand the reader the words we missed rather than only the ones we hit.
    """
    text = (payload or {}).get("text") or ""
    text = text[:20000]                      # generous; bounded so a paste cannot stall a worker
    if not text.strip():
        raise HTTPException(400, "no text supplied")

    taught = {t.lower() for t in CURRICULUM["taught_skills"]}
    found = []
    for name in skills.extract_skills(text):
        hits = skills.match_sentences(text, name)
        found.append({
            "skill": name,
            "category": skills.skill_category(name),
            "taught": name.lower() in taught,
            "evidence": hits[0]["sentence"] if hits else None,
            "matched_text": hits[0]["matched"] if hits else None,
        })

    # Technical-looking phrases the dictionary does not carry. Discovery only:
    # these are candidates for a human to adjudicate, never counted anywhere.
    known = phrases._known_surface_forms()
    matched_low = {f["skill"].lower() for f in found}
    # Tokens of everything already matched, so a phrase that merely brushes
    # past a term we DID find ("dashboards in Power") is not paraded as a miss.
    matched_tokens = {w for k in matched_low for w in k.split() if len(w) > 2}

    cand = {}
    for phrase, surface, _sent in phrases._candidate_phrases(text):
        if phrase in known or phrase in matched_low:
            continue
        if any(phrase in k or k in phrase for k in matched_low):
            continue
        if set(phrase.split()) & matched_tokens:
            continue
        cand.setdefault(phrase, surface)

    # Prefer the shortest form: "ArgoCD" is a better candidate to adjudicate
    # than "ArgoCD and Istio", and listing both is noise.
    unknown = []
    for phrase in sorted(cand, key=lambda x: (len(x), x)):
        if any(kept in phrase for kept in unknown):
            continue
        unknown.append(phrase)
    unknown = [cand[p] for p in unknown][:12]

    return {
        "n_chars": len(text),
        "dictionary_size": skills.skill_count(),
        "n_found": len(found),
        "n_not_taught": sum(1 for f in found if not f["taught"]),
        "found": found,
        "untracked_candidates": unknown,
        "curriculum": CURRICULUM["name"],
        "note": ("Deterministic dictionary match, no model and no network. A "
                 "term outside the dictionary is unmeasured, not absent - the "
                 "untracked list shows what that cost on this text."),
    }


@app.get("/api/health")
def api_health():
    return JSONResponse({"ok": True, "postings": analysis.overview(CON)["n_postings"]})
