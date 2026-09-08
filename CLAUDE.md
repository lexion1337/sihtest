# CLAUDE.md — Skill Drift Analyzer

Read this file completely before writing any code. It is written for a
session that starts with zero context.

---

## PROJECT

**Skill Drift Analyzer** — Smart India Hackathon 2026, Problem Statement
**SIH26134** (Government of Maharashtra: *"Challenges in aligning skill
development programs with industry requirements and emerging job market
demands"*).

## WHO THE USER IS

BTech Computer Science student, Reva University, Bangalore. Six-member team.

- **College internal hackathon: 10 September 2026.**
- If they win it, the national Grand Finale is a 36-hour build in December 2026.
- They work in **short sessions with limited quota**. Every session must end
  with something that runs. Prefer finishing one vertical slice over starting
  three horizontal ones.

## THE PROBLEM WE'RE SOLVING

A single job posting now draws thousands of applicants within an hour.
Off-campus candidates compete against IIT graduates and people with years of
experience. Meanwhile AI is absorbing entry-level tasks faster than any
curriculum or government skilling programme can revise itself.

The failure here is **not a shortage of training. It is a shortage of
INFORMATION.** Of the 3,000 people who applied to that posting, not one was
told in advance which specific skill they were missing. NSQF qualification
packs and college syllabi update on multi-year cycles; job requirements move
every quarter. Nobody measures the gap between them, so nobody can close it.

## WHAT WE ARE BUILDING

An **evidence layer**. We measure what employers actually asked for, over
time, per role — from real job postings — and diff that against what NSQF
packs and college curricula actually teach.

The output is a concrete, checkable finding:

> "this skill appeared in 40% of Data Analyst postings this quarter and
> appears in zero syllabi."

## WHAT WE ARE NOT BUILDING

Not a chatbot. Not a course recommender. Not an LLM wrapper. Judges will see
forty of those.

The defensible core is the **DATASET** and the **MEASUREMENT** — data nobody
else bothered to collect, and honest numbers computed over it. An LLM may
assist with skill extraction later; it is a component, never the product.

**If a feature can be replicated by a team in one evening with an API key, it
is not our differentiator.**

## HONESTY RULES (non-negotiable — these decide whether we win or get caught)

1. Every number shown must trace to real computation over real records.
2. Never fabricate a statistic for a slide.
3. Synthetic or seed data must be labelled as such **everywhere it surfaces in
   the UI**, not just in code comments.
4. Always display sample size alongside any percentage.
5. If a bucket has too few records to support a claim, **say so in the UI**
   rather than smoothing over it.

These are not stylistic preferences. A judge who catches one invented number
ends the run. When in doubt, show the smaller, uglier, true number.

---

## STACK

Chosen for zero setup friction. **Do not add build tooling.**

- Python 3 (developed on 3.13)
- FastAPI + uvicorn
- SQLite (stdlib `sqlite3`)
- Vanilla HTML + Chart.js via CDN

`python run.py` must start everything. **No npm, no bundler, no Docker, no
migrations framework, no ORM.**

Only external dependency: `fastapi` + `uvicorn`. Everything else is stdlib.

## ARCHITECTURE

Pipeline, strictly one direction. Each stage is a plain module runnable on its
own with `python <module>.py`.

```
data/postings.jsonl        600 seed postings, every record source="synthetic"
        |
        v
skills.py                  SKILL_DICT (~120 terms + aliases) -> regex/alias match
        |                  offline, no network, instant
        v
data/skills.db (SQLite)    table posting_skills(posting_id, skill, role,
        |                                       posted_date, source)
        |                  table postings(id, title, company, location,
        |                                 posted_date, role, source)
        v
analysis.py                per role, bucket by quarter, share = postings
        |                  mentioning skill / postings in bucket
        |                  emits first_seen, latest_share, change, trend label
        |                  buckets with n < 20 flagged low_confidence
        v
data/curriculum.json       BTech CS syllabus skill list
        |
        v
analysis.py:curriculum_gap()   rising AND latest_share > 15% AND not taught
        |
        v
app.py (FastAPI)  ->  static/index.html + Chart.js
```

### Key invariants

- **`share` denominator is postings in that (role, quarter) bucket** — not
  total postings, not skill mentions. Always carry `n` next to it.
- **`LOW_CONFIDENCE_N = 20`.** Buckets below this are computed but tagged
  `low_confidence: true`, and the UI must render that tag.
- **Quarter format is `YYYY-Qn`** (string, sorts correctly).
- The DB is a **derived artifact**. It can be deleted and rebuilt from
  `postings.jsonl` at any time. Never hand-edit it.
- `scraper.py` is a **stub only** — clean `fetch(role, pages) -> list[dict]`
  interface matching the postings.jsonl schema. The real National Career
  Service / Naukri scrape is a later session. It must raise
  `NotImplementedError`, never return fake rows silently.

### Trend labels (`analysis.py`)

Computed on `change = latest_share - first_share` across the window:

- `rising` if change >= +5 percentage points
- `declining` if change <= -5 percentage points
- `stable` otherwise

Thresholds live in constants at the top of `analysis.py`. If they change, the
UI legend must change with them.

## FILE MAP

| File | Role |
|---|---|
| `run.py` | Entry point. Builds DB if missing, then serves. |
| `pipeline.py` | Rebuilds SQLite from postings.jsonl. Idempotent. |
| `skills.py` | Skill dictionary + extraction. Offline. |
| `analysis.py` | Quarterly drift + curriculum gap. Pure reads. |
| `scraper.py` | **Stub.** Real scrape, later session. |
| `app.py` | FastAPI routes + JSON API. |
| `static/index.html` | Single-page dashboard. |
| `tools/gen_seed.py` | Regenerates `data/postings.jsonl`. Deterministic (seeded). |
| `data/postings.jsonl` | 600 synthetic postings. Committed. |
| `data/curriculum.json` | BTech CS syllabus skills. Committed. |
| `data/skills.db` | Derived. Not committed. |
| `PROGRESS.md` | **Update at the end of every session.** |

## WORKING AGREEMENT

- Update `PROGRESS.md` at the end of **every** session: what runs, what
  doesn't, what the single next task is.
- End each session with a working `python run.py`.
- If time runs short, degrade the dashboard to a static HTML table. **Never
  skip the pipeline steps — the numbers are the product, the chart is
  packaging.**
