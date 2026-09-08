"""
app.py -- FastAPI routes and JSON API for the Skill Drift Analyzer.

The API is deliberately thin: every endpoint is a straight pass-through of
what analysis.py computed. No numbers are produced here.

/api/postings is the point of the whole design -- it lets anyone click a
percentage in the UI and read the actual postings behind it. If a number
cannot be drilled into, it should not be on screen.
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import analysis
import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")

app = FastAPI(title="Skill Drift Analyzer", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CON = pipeline.connect()
CURRICULUM = analysis.load_curriculum()


def _check_role(role):
    valid = analysis.roles(CON)
    if role not in valid:
        raise HTTPException(404, "unknown role %r; known roles: %s" % (role, valid))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


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
def api_posting(posting_id: str):
    """Full text of one posting, plus the skills extracted from it."""
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
    return {"posting": dict(row), "skills": found, "description_text": text}


@app.get("/api/health")
def api_health():
    return JSONResponse({"ok": True, "postings": analysis.overview(CON)["n_postings"]})
