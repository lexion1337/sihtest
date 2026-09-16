# PROGRESS.md

**Update this file at the end of every session.** Read `CLAUDE.md` first — it
holds the problem statement, the honesty rules, and the architecture.

Last updated: **2026-09-16** (session 5 -- frontend rebuild)
Deadline: **SIH internal hackathon, 16 September 2026 — TOMORROW.**
Venue: REVA Rangasthala / Amphi Theatre, 8:30 AM - 4:30 PM.
Bar for internal: **30% of the project ready**, measured against the problem
statement's 15 required elements, not against lines of code.

---

## TL;DR

`python run.py` serves **three pages** on http://127.0.0.1:8000. It works.

| Route | Who it is for | Statistics shown |
|---|---|---|
| `/` | anyone, zero context | **none** -- no p-values anywhere |
| `/dashboard` | interested judge | counts, sample sizes, plain verdicts |
| `/method` | teacher, statistician, sceptic | **everything** -- p-values, BH, Fisher, audits |

Built to the plan in `FRONTEND_PLAN.md`, which is now DONE. The three-second
image (a job ad, the syllabus, the missing skill lit between them) finally
exists, on `/`. Chart conventions follow the UK Government Analysis Function
guidance for statistical publications -- headline that states the message,
statistical subtitle, source line, and colour never carrying meaning on its
own -- because the audience is a government department.

**The corpus is MIXED: 747 postings = 600 synthetic + 147 REAL.** The real
ones come from public ATS job-board APIs (Greenhouse, Lever), ingested by
`ingest_ats.py`. The provenance banner reads "MIXED DATA" and is
computed from the source counts of what was actually loaded, not a hardcoded
flag, so it cannot lie about this.

Session 2's conclusion that no real data was obtainable was **overturned in
session 3** by a route session 2 never tried: company ATS boards rather than
job portals. NCS and Naukri are still dead ends and still documented below.

**The one number that matters and that we still do not have: extraction recall
on real text.** `data/recall_review.md` holds 30 real postings ready to be
marked up by hand. Nobody has marked them. Until someone does, the honest
answer to "how do you know extraction works on real text" is a measured proxy,
not recall.

---

## HOW TO RUN

```bash
python run.py
```

That is the whole thing. It generates the seed corpus if missing, rebuilds the
SQLite database if stale, then serves. Only `fastapi` and `uvicorn` are needed
(`pip install fastapi uvicorn`); everything else is Python stdlib.

Useful extras:

| Command | Does |
|---|---|
| `python run.py --port 8010` | serve on another port |
| `python run.py --rebuild` | force a database rebuild first |
| `python skills.py` | dictionary size + a sample extraction |
| `python tools/gen_seed.py` | regenerate `data/postings.jsonl` (deterministic) |
| `python pipeline.py` | rebuild `data/skills.db` from the JSONL |
| `python analysis.py` | print drift + curriculum gap for all roles to stdout |
| `python scraper.py` | prints the TODO and shows `fetch()` raising |

---

## WHAT RUNS (verified 2026-09-15)

**1. Seed data — done.** `data/postings.jsonl`, 600 postings, 200 each for Data
Analyst / Backend Developer / Business Analyst, spread 2024-01-06 → 2026-09-30.
Every record carries `"source": "synthetic"`. Descriptions are Naukri-style
(responsibilities, Must Have / Good to Have, experience, notice period). Drift
is encoded as linear probability ramps per skill, e.g. Advanced Excel
0.88 → 0.42 and LLM 0.01 → 0.46 for Data Analyst. Regenerating is deterministic
(seed 20260910), so the numbers below reproduce exactly.

**2. Skill extraction — done.** `skills.py`, **136 canonical skills** with
aliases, across categories `data / ai / backend / business / fundamentals`.
Pure regex + alias matching, offline, no network, runs in well under a second
over the whole corpus. Custom word boundaries handle `C++`, `.NET`, `CI/CD`,
`Node.js`, and a strict case-sensitive rule for `R` so that `R&D` and
`R-Studio` do not produce false hits.

**3. Drift computation — done.** `analysis.py`. Per role, bucketed by quarter.
For each skill: full quarterly series, `first_seen`, `latest_share`, pooled
`baseline_share` over the first two quarters, `change_pp`, a
rising/stable/declining label, a 95% Wilson confidence interval, and a
two-proportion z-test p-value. Buckets under `LOW_CONFIDENCE_N = 20` are
flagged and the flag is rendered in the UI.

**4. Curriculum gap — done.** `data/curriculum.json` is a 22-subject BTech CSE
composite (DBMS, OS, DSA, Java, ML, networks, electives) mapping to 38 distinct
taught skills. `curriculum_gap()` returns skills that are rising **and** in
≥15% of the latest quarter's postings **and** absent from the syllabus.
`load_curriculum()` fails loudly if the JSON names a skill that `skills.py`
does not know, so the two files cannot silently drift apart.

**5. Dashboard — done.** `app.py` + `static/index.html`, Chart.js from CDN.
Role selector, chart ranking toggle (most-demanded / biggest movers), multi-line
quarterly chart, the gap table, and a second table of skills that are demanded
**and** already taught (so the gap table can be read in context). Low-confidence
quarters are drawn as **dashed** segments with an explicit note listing every
quarter's sample size.

**6. REAL DATA INGEST — done, session 3.** `ingest_ats.py` reads the
documented, unauthenticated job-board APIs that companies publish so their
careers pages can be embedded elsewhere:

    Greenhouse  boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
    Lever       api.lever.co/v0/postings/{token}?mode=json
    Ashby       api.ashbyhq.com/posting-api/job-board/{token}   (adapter ready, untested)

Boards live in `data/boards.json`, so going from 3 boards to 40+ is a config
edit, not a code change. A failing board is logged and skipped, never fatal.
Requests are sequential with a 1.5 s delay.

**THE DATE SPLIT.** Lever `createdAt` and Ashby `publishedAt` are true creation
timestamps. Greenhouse `updated_at` is LAST-MODIFIED. Measured: all 64 Postman
postings carry an `updated_at` inside a single quarter, so the field is not
merely noisy, it is **degenerate** for time bins. Every record therefore
carries `date_kind` and `time_series_eligible`; the DB carries `ts_eligible` on
both tables; `analysis._quarter_totals()` and the skill-count query filter on
it; and the chart renders a note naming the excluded rows and why. Excluded
postings still feed skill extraction and the tables — only the quarterly view
drops them.

**7. MULTI-SOURCE LOADER — done, session 3.** `pipeline.build()` and
`read_postings()` accept `None` (discover every `data/postings*.jsonl`), a
single path, or a list. Duplicate ids across corpora are rejected by name
rather than silently deduped. `analysis.provenance()` classifies a corpus as
empty / synthetic / mixed / real from its source counts, and the banner keys
off that.

**8. Chart.js VENDORED — done, session 3.** `static/chart.umd.min.js`, 200,807
bytes. The dashboard now loads **zero external hosts** — verified by the
browser network log showing 5 requests, all to 127.0.0.1. Venue Wi-Fi shared by
~50 teams cannot break the chart.

**9. DEMAND BY LOCATION — done, session 3.** `locations.py` normalises the raw
location strings (one city appeared as `Bangalore, Karnataka`, `bengaluru` and
`Bengaluru, Karnataka, India`). `postings` gains city/state/country;
`analysis.demand_by_location()` reports which skills are demanded where, with
posting counts and an n<20 flag per city. State is tracked because the customer
is the Government of Maharashtra. Measured: **Pune 67, Mumbai 62, Nagpur 27**
in Maharashtra; Bengaluru 115. Unrecognised locations become "Unknown" (5 rows,
all genuinely foreign cities) rather than a guess. `/api/locations`.

**10. OBSOLETE / OVERSUPPLIED COURSES — done, session 3.** The gap table
reversed: `analysis.obsolete_courses()` finds skills the curriculum teaches
that demand does not ask for, split into obsolete / declining / never-seen, each
naming the subject codes that teach it so a recommendation points at a course
rather than a word. `/api/obsolete`. The UI carries an explicit caveat that
absence from job adverts is not proof a subject is worthless.

**11. Scraper — stub only, as specified.** `scraper.py` fixes the `fetch(role,
pages) -> list[dict]` interface and raises `NotImplementedError`. It also ships
a `validate()` helper that rejects any record claiming `source="synthetic"`,
so the real collector cannot accidentally launder fake rows into the corpus.

### Beyond the brief (worth knowing about)

- **`/api/postings` + `/api/posting/{id}` evidence drill-down.** Clicking any
  row in the gap table opens a panel listing the exact postings counted in that
  numerator, and clicking one loads its full description text. Verified: the
  dbt / 2026-Q3 cell reads "8 of 25" and the drawer returns exactly 8 postings.
  This is the strongest answer to "did you make these numbers up".
- **Significance testing.** See "the noise problem" below.

---

## VERIFIED NUMBERS (reproduce with `python analysis.py`)

### Real corpus, ingested 2026-09-09 (`python ingest_ats.py`)

| Board | ATS | Jobs | Date field | Time-series eligible |
|---|---|---|---|---|
| Postman | Greenhouse | 64 | `updated_at` (modified) | **No — all 64 excluded** |
| Meesho | Lever | 50 | `createdAt` (created) | Yes |
| CRED | Lever | 11 | `createdAt` (created) | Yes |

125 real postings. Counts drift daily as boards change, so every record carries
`fetched_at`.

**Role classification** (conservative title rules; anything uncertain becomes
`Other (unclassified)` rather than being forced into a bucket, because a wrong
role label corrupts every share for that role):

- Backend Developer **17**, Data Analyst **1**, Other (unclassified) **107**

These boards are overwhelmingly Account Executives, Solutions Engineers,
Customer Success, Marketing and Finance. That is the coverage skew this file
already predicted, now **quantified rather than assumed**.

**Consequence to say out loud: only 18 of 125 real postings are in a role we
measure, and only 5 are BOTH in a measured role AND time-series-eligible.** The
real data can support a cross-sectional view of current demand. It cannot
support a real quarterly time series yet. More boards is the only fix.

### EXTRACTION ON REAL TEXT — the headline finding

| Corpus | n | Mean skills/posting | Median | Zero-skill |
|---|---|---|---|---|
| Synthetic | 600 | **11.8** | 12 | 0 (0.0%) |
| Real (all) | 125 | **2.6** | 1 | **58 (46.4%)** |

That raw comparison is **confounded by role mix** — an Account Executive
posting correctly yields zero skills. On the roles we actually measure:

| Role | n | Mean | Median | Zero-skill |
|---|---|---|---|---|
| Backend Developer + Data Analyst | **18** | **5.4** | 6 | 2 (11.1%) |
| Other (unclassified) | 107 | 2.1 | 0 | 56 (52.3%) |

**On comparable roles, extraction finds roughly half as many skills per posting
on real text as on synthetic — 5.4 vs 11.8.** The synthetic figure is a ceiling
artefact because the generator and extractor share `skills.py`.

**This is NOT recall.** True recall needs a human to read each posting and list
what should have been found. `data/recall_review.md` has 30 real postings ready
for that markup. `SKILL_DEFS` was deliberately NOT tuned to improve these
numbers.

### Synthetic corpus

600 postings, 7061 skill mentions, 11.8 per posting.

Postings per role per quarter: 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 25
(2024-Q1 → 2026-Q3). **Seven of eleven quarters are below n=20 and flagged.**

Data Analyst, 2026-Q3, n=25 — 17 candidate gaps, **9 significant at p<0.05**:

| Skill | Share | Sample | 95% CI | vs baseline | p |
|---|---|---|---|---|---|
| Data Cleaning | 56.0% | 14/25 | 37.1–73.3% | +28.0 pp | 0.045 |
| LLM | 48.0% | 12/25 | 30.0–66.5% | +48.0 pp | 0.000 |
| BigQuery | 40.0% | 10/25 | 23.4–59.3% | +28.0 pp | 0.024 |
| Prompt Engineering | 36.0% | 9/25 | 20.2–55.5% | +32.0 pp | 0.005 |
| Snowflake | 36.0% | 9/25 | 20.2–55.5% | +24.0 pp | 0.047 |
| Agent Orchestration | 32.0% | 8/25 | 17.2–51.6% | +32.0 pp | 0.002 |
| dbt | 32.0% | 8/25 | 17.2–51.6% | +32.0 pp | 0.002 |
| Apache Airflow | 24.0% | 6/25 | 11.5–43.4% | +20.0 pp | 0.042 |
| OpenAI API | 20.0% | 5/25 | 8.9–39.1% | +20.0 pp | 0.018 |

Backend Developer: 22 candidate gaps (Docker 76%, Kubernetes 64%,
Microservices 60%, CI/CD 52%, Observability 48%).
Business Analyst: 10 candidate gaps, 4 significant (LLM 44%, Prompt
Engineering 32%).

---

## THE NOISE PROBLEM (read this before quoting any number)

**600 postings is not enough to make quarterly claims, and the tool now says so
itself.** At n=25 a skill's share moves ±10 percentage points on sampling noise
alone. The analysis once labelled Google Sheets "rising +12 pp" for Data
Analyst when the generator's own curve for it is *declining* (0.30 → 0.18).

**Describe that correctly.** It is NOT a false discovery. p=0.221 produced no
rejection, so nothing was ever discovered — a false positive requires a
rejection. It is a **noisy sign reversal that the decision rule correctly
withheld from the alert list**, which is a real and useful thing for the tool
to do, but a different claim. Wrong-direction estimates should be tracked as
their own category. This wording was corrected in session 4 after external
review; the earlier phrasing overclaimed.

Rather than hide it, `analysis.py` now runs a **two-proportion z-test** between
the baseline window and the latest quarter, and the UI marks every row
`significant` or `not significant` with its p-value. Google Sheets now reads
p=0.221, not significant. Of 17 Data Analyst candidate gaps, only 9 survive.

Two consequences:

1. **Never quote a "not significant" row as a finding.** It is a direction, not
   a measurement. The honest line is: *"the sample is not yet big enough."*
2. **This is an argument for the project, not against it.** The fix is more
   data — which is exactly what the scraper is for. A judge asking "how do you
   know that is real?" should be shown the p-value column and the sample size,
   not talked around.

---

## KNOWN LIMITATIONS AND BROKEN THINGS

**Nothing is currently broken.** These are honest gaps, in priority order.

1. **Real data is thin and skewed, and the sample cannot carry a time series.**
   125 real postings, but only 18 in a measured role and only 5 both measured
   and time-series-eligible. Coverage is limited to companies on Greenhouse /
   Lever / Ashby with public boards whose token we found — venture-funded
   product-tech firms. **Systematically missing: IT services (TCS, Infosys,
   Wipro), where most Indian CS graduates go**, plus non-tech, government, PSU
   and small firms. Say this before a judge does.

   Related: **survivorship bias.** A posting created in 2023 that is still open
   in 2026 is a posting that did not get filled. A time series built from
   currently-open postings samples slow-to-fill roles.

   `scraper.fetch()` still raises by design — NCS and Naukri remain dead ends.
2. **The drift is synthetic by construction.** The generator encodes the ramps
   the analysis then measures. This validates the *pipeline*, not any claim
   about the market. Do not present the trends as findings about hiring.
3. **Extraction recall is ~100% on this corpus by construction** — the
   generator and extractor share `skills.py`, and the round-trip check is
   clean (0 incidental matches, 0 misses). **This does not validate the
   extractor against real postings**, which have typos, HTML, tables, bullet
   glyphs and phrasing the dictionary has never seen. Expect recall to drop
   sharply on the first real scrape; budget a session for it.
4. **The curriculum is a synthetic composite**, not a real cited syllabus.
   `source_note` in the JSON says this and the dashboard prints it. Replace it
   with Reva University's published CSE scheme before any public claim.
5. **No deduplication.** Real boards repost the same requisition across weeks
   and sites; counting duplicates inflates every share. `scraper.py` has a
   suggested dedup key in its TODO. Must land with the scraper, not after.
6. **Role assignment is a stored field.** Seed records declare their role. Real
   postings will need a classifier or a keyword rule to bucket them, and that
   is a source of error nobody has measured yet.
7. **`/api/posting/{id}` linearly scans the JSONL** to fetch description text,
   because the DB stores what was measured rather than the raw corpus. Fine at
   600 records, too slow past a few thousand. Store the text (or an offset) in
   SQLite when the corpus grows.
8. **Extraction runs on `description_text` only**, not the title. Deliberate:
   titles like "Java Backend Developer" would put a floor under a skill's share
   independent of the posting body. Revisit once real data lands.
9. **No automated test suite.** The round-trip and API checks were run manually
   this session. Worth a `tests/` directory before the Grand Finale.
10. Chart.js is loaded from a CDN, so the dashboard **needs internet for the
    chart to draw**. Tables still render offline. If the venue Wi-Fi is bad on
    10 September, vendor `chart.umd.min.js` into `static/` beforehand.

---

## DATA SOURCE INVESTIGATION (session 2)

Everything below is a *result*, not a to-do. Two routes were tested to
destruction so that a future session does not repeat the work.

### A. National Career Service (ncs.gov.in) — BLOCKED, 0 postings

Reconnaissance only. **No scraping was performed**; the session stopped at the
permission gate as instructed.

| Check | Finding |
|---|---|
| `robots.txt` | **Does not exist.** `www.ncs.gov.in/robots.txt` 301-redirects to the homepage; `ncs.gov.in/robots.txt` returns **HTTP 404** serving the Angular app shell. So there are no crawl directives at all — nothing disallowed, nothing allowed. |
| Terms & Conditions (`/terms&condition`) | Liability and accuracy disclaimer only. Governed by Indian law. **No scraping or reproduction clause.** |
| Disclaimer (`/disclaimer`) | Liability disclaimer only. No reproduction clause. |
| Previous site's Copyright Policy | The old `pages/copyright-policy.aspx` stated contents *"may not be reproduced partially or fully, without due permission from the Directorate General of Employment & Training (DGET)"*. **That page no longer exists** on the rebuilt site. The current site does not restate it. |
| Documented public API | **None.** No developer portal, no published API. |
| Site architecture | Angular SPA. `/job-search` now **404s** — routes changed in a site rebuild. Listings render client-side from an undocumented internal JSON backend. |

**The blocking issue is not robots.txt — it is that there is nothing legitimate
to scrape.** Because the portal is client-rendered with no documented API,
"scraping NCS" would mean calling an **undocumented internal API** rather than
parsing published HTML. That is a materially different decision from ordinary
web scraping and it needs an explicit human call, ideally with DGE's blessing,
not a unilateral one made by a script. Combined with a historical copyright
policy that required DGET permission, the honest position is: **ask first.**

### B. data.gov.in — REAL AND OPEN, BUT WRONG SHAPE

The NCS catalog on data.gov.in exists and is openly licensed (NDSAP), but
contains **6 resources, all aggregate statistics**, no job postings:

- "Qualification wise Jobseeker Registration till 30 September 2023" (552 bytes)
- "Age Group wise Jobseeker Registration till 30 September 2023" (281 bytes)
- "Minimum qualification wise Vacancies Mobilised till 30 September 2023" (612 bytes)
- "State Wise Vacancies Mobilised till 30 September 2023" (1.4 KB)
- "Sector wise Vacancies Mobilised till 30 September 2023" (1.0 KB)
- "State wise Jobseeker Registration on NCS portal till 30 June 2022" (2.2 KB)

File sizes of 281 bytes to 2.2 KB confirm these are small count tables.
**Zero job descriptions, zero skill text, coverage ends September 2023.**
Useless for skill extraction, which needs free text. Do not re-check this.

### C. Wayback Machine + Naukri — LOOKS VIABLE, IS NOT (verified)

This one is worth reading carefully, because the top-line numbers are
encouraging and the reality is not.

Captures of Naukri's individual JD URL pattern (`naukri.com/job-listings*`):

| Window | Distinct archived JD URLs |
|---|---|
| 2024 | **9,537** |
| 2025 | **8,167** |
| 2026 (Jan-Sep) | **7** |

That looked like ~17,700 real historical postings. **It is not.** Ten snapshots
were fetched and parsed, spanning January 2022 to August 2025:

| Snapshot | Visible text | JSON-LD JobPosting |
|---|---|---|
| 2022-01-19, 2022-01-17 | 0 chars | no |
| 2023-07-05 | 49 chars | no |
| 2023-12-05 | 54 chars | no |
| 2024-05-24 | 0 chars | no |
| 2024-10-01, 2024-10-24 | 0 chars | no |
| 2025-01-19, 2025-03-10 | 0 chars | no |
| 2025-08-01, 2025-08-04 | 0 chars | no |

Naukri is a Next.js client-rendered app. The archived HTML contains the page
in its pre-fetch state — literally
`"jobDetailsResp":{"data":null,"loading":true,"error":null}`. The description
was fetched by XHR after page load and **the crawler never captured it**.

The description *does* live at `naukri.com/jobapi/v4/job/{jobId}`, and Wayback
has archived some of those JSON responses — but only **342 distinct captures
across 2023-2026 combined** (46 / 76 / 102 / 118 per year), scattered across
arbitrary jobs rather than our three roles. Far too few, and not targetable.

**Consequence: Common Crawl will fail the same way** for Naukri and for any
other client-rendered board. Do not spend a session on it without first
checking that the target is server-rendered.

Also note the 2026 column: **7 captures.** Even if archives worked, Wayback
covers the past and not the present, so it could never have replaced a live
feed — only complemented one.

### D. Kaggle — small, mostly stale, and one active trap

71 Naukri-related datasets exist, but they cluster in 2019-2023.

**Best schema match:** PromptCloud, *"Naukri Jobs Data - Dec 2023"* —
licence **CC0: Public Domain**, `.ldjson` format (same shape as our JSONL),
and the fields are exactly what we need, verified by inspection:
`uniq_id`, `crawl_timestamp`, `job_title`, **`post_date`** (a real absolute
date), **`job_description`** (full free text). The problem is volume: the
published file is `naukri.com-jobs__20231201_20231231_sample.ldjson` at
**49.52 kB** — an explicit *sample*, roughly 25-40 records. PromptCloud
publishes samples on Kaggle and sells the full extract.

**TRAP — do not use:** *"India Tech Jobs 2024-2026 | Salary & Skills"* is the
only Kaggle dataset that appears to cover our exact window. Its own
description says it **"simulates 5,000 real-world tech job postings"**. It is
synthetic. If anyone on the team ingests it believing it is real, we breach
our own honesty rules and hand a judge the exact failure we are trying to
expose in everyone else. Flagged here permanently.

**Nothing was found on Kaggle with real Indian JD text covering 2024-2025.**

### E. Best real corpus found — real text, real dates, wrong country

`lang-uk/recruitment-dataset-job-descriptions-english` (Hugging Face), the
Djinni recruitment dataset:

- **141,897 rows**, licence **MIT**, 146 MB
- `Long Description` — full free text, 51 to 12,600 characters
- `Published` — ISO 8601 dates
- Coverage **October 2020 to December 2023** — a genuine 3-year time series
- Also carries `Position`, `Company Name`, `Exp Years`, `Primary Keyword`
- **Market: Ukraine IT sector. NOT India.**

This cannot support any claim about the Indian job market and must never be
presented as one. What it *can* do is fix our biggest methodological weakness
(limitation 3): it is real, messy, human-written job text with real dates, so
running the existing pipeline over it unchanged would show whether our
extraction and drift maths survive contact with reality.

Other large corpora exist but are also non-India: LinkedIn Job Postings
2023-2024 (Kaggle), National Labor Exchange (30M+ US postings 2024-25),
Multi-National Job Advertisements (2.5M AU/US/UK, Jun 2023-Jun 2024).

### F. The honest bottom line

**An openly licensed, date-stamped, description-bearing corpus of *Indian* job
postings covering 2024-2025 does not appear to exist in public.** That is a
finding, and it is arguably the strongest evidence for why this project should
exist at all: nobody has collected this data, which is precisely why nobody can
measure the gap. Say that out loud on the 10th rather than hiding it.

### Recall-review artifact — NOT PRODUCED

The 30-posting extraction review was conditional on real data arriving. No real
data arrived, so no artifact was produced. Producing one from synthetic
postings would have been worthless: recall on the seed corpus is ~100% by
construction, because the generator and extractor share `skills.py`.

## SESSION 4 — EXTERNAL STATISTICAL AND DESIGN REVIEW, IMPLEMENTED

An external review (GPT/"Astra", full text in the team's Downloads) produced
the sharpest criticism the project has had. What follows is what changed.

### The criticism that matters most, and is NOT fixed by code

> "Even with a million perfectly dated, correctly extracted advertisements, you
> have not shown that the missing syllabus terms represent missing competence,
> that employers face a shortage of that competence, or that teaching it would
> improve placement. Your instrument measures vocabulary differences and then
> recommends treatment."

This is non-identification and it is correct. A syllabus keyword can be absent
while the competency is taught under a broader learning outcome, and present
while taught badly. Advertisements observe employer demand *language*, not
competent labour supply — so "oversupplied" cannot be inferred from a
curriculum diff at all. Every output was relabelled accordingly, and the
Methods "Limits" row now states this explicitly in the UI.

### Three defects it found in our code, all confirmed by measurement

1. **No multiple-comparison correction.** "Significant" was raw p<0.05 across
   ~40 tests per role, where ~2 false alerts are expected by chance. Now
   Benjamini-Hochberg, reported ALONGSIDE raw p rather than relabelling it.
   Data Analyst gaps 9 → 4; Backend 9 → 5; Business Analyst 4 → 2.
2. **"Never seen" used the latest-quarter denominator.** `AWS: 0 of 25` was
   really `0 of 201` across 11 quarters — understating the evidence 8×.
3. **Latent circularity in the role classifier.** It matched on language names
   that are also measured competencies, so a change in that skill could move
   both the numerator and who enters the denominator. Measured first: fired on
   0 of 725 titles, so latent not active. Removed anyway.

### Statistical work added

- **Fisher exact cross-check.** The z-test is a normal approximation; at n=25
  near 5% prevalence expected cell counts fall to 1-3. Fisher runs alongside as
  a conservative check. NOT substituted — Fisher is severely conservative here
  (simulated actual rejection ≈ 0.08/0.88/2.22% at 5/10/20% prevalence against
  nominal 5%, versus the z-test's 1.98/4.87/5.49%).
- **Newcombe intervals for the CHANGE.** Wilson intervals describe each
  prevalence; whether two of them overlap is not a test of the difference.
- **Threshold sensitivity.** A prespecified 3×3 grid reports WHICH
  recommendations persist. For Data Analyst, LLM, Prompt Engineering, Agent
  Orchestration and dbt pass in **all nine cells**. Read narrowly: the cells
  reuse the same observations and are not independent confirmations. It rules
  out a threshold chosen to flatter the result; it is not validity.

### Open-vocabulary discovery — `phrases.py`

The dictionary is closed, so an unlisted competency has prevalence zero *by
construction*. That made "detects emerging skills" unsupportable. `phrases.py`
finds dictionary-absent 1-4 word phrases in requirement-like sentences, counts
once per posting, and ranks by DISTINCT EMPLOYERS first (ten copied adverts
from one employer are one lead, not ten).

**It found real holes: API (65 postings, 2 employers), AI (27), DevOps (21) and
SRE (4) are genuine competencies the 136-term dictionary misses entirely.**

It adds nothing to the dictionary and claims nothing about rising — with five
time-series-eligible real postings there is no series to measure a rise
against. Discovery and confirmation stay separate, or every dictionary update
manufactures apparent emergence.

### The number that should change how you pitch

Simulated power for a two-sided Fisher test detecting a **10 percentage-point**
shift: **n=25 → 8.6%**, n=100 → 44.4%, n=200 → 76.8%, n=300 → 92.0%. Under BH
across 40 skills, power at n=25 is ~0.2%.

Our generator plants effects 3-5× larger than that (LLM runs 0.01 → 0.46, a
45pp shift), which is why the detector finds them at n=25. **The honest claim
is "at n=25 we can detect a 40-point shift; we cannot detect a 10-point shift"**
— and that is a stronger, more precise beat than the significance test alone.

### Front end rebuilt around a decision brief

Six equal cards became a first screen that fits 1366×768 without scrolling:
provenance banner, role and syllabus context, one featured review candidate,
its action, and a visible discarded comparison. Measured: hero bottom 629px,
discarded strip 758px.

**The most valuable single addition:** each finding now carries the composition
of the records that produced *its* number. The featured LLM finding reads
"Synthetic test finding — 0 real / 12 synthetic of the 12 counted". The
corpus-wide MIXED banner would otherwise have let a reader assume it was real.

Five destinations: Review findings · Location evidence · Syllabus coverage ·
Unmapped terms · Methods & data. The eight-line chart is gone from the default
view. The evidence drawer is now a calculation audit that exposes the
denominator, not just the supporting examples, and highlights the matched
sentence so a reader can judge whether a mention is a requirement or incidental
company description.

### What was deliberately NOT built

The review's December programme — employer survey panels, opt-in graduate
tracer cohorts, trade-specific evidence chains, adoption pilots — needs
institutional access this team does not have. Correct as direction, wrong as a
build. Recorded as roadmap, not attempted.

### One genuinely new data lead

**Maharashtra AITT July 2019 ITI graduates tracer study** (published July 2021):
trade- and district-level employment outcomes, first-employment timing, wages.
Real, official, Maharashtra-specific, and it covers *placement outcomes* — one
of the six PS inputs currently marked absent. Chase it.

The review did NOT find an openly licensed, dated, description-bearing corpus
of Indian job postings. Two independent searches have now failed. Treat that as
established.

---

## THE AUDITS -- FIRST-PASS NUMBERS (2026-09-16)

Both audits the reviews asked for now exist as DATA, not prose:
`data/classification_verdicts.json` and `data/extraction_verdicts.json`, scored
by `tools/score_classification.py` and `tools/score_extraction.py`. Change any
verdict letter and the numbers move.

**These are a MACHINE first pass.** Claude wrote the classifier and the
extractor and also wrote these verdicts, so this is marking its own homework,
and on extraction it shares the dictionary's blind spots. Quote them as
"first-pass, pending human confirmation" and get a teammate to spot-check.

### Role classifier: precision 31-50%, recall 13-42%

| | count |
|---|---|
| Unclassified, genuinely out of scope | 98 |
| Unclassified, MISSED (should have been caught) | 7 |
| Unclassified, ambiguous | 26 |
| Assigned, correct | 5 |
| Assigned, WRONG | 5 |
| Assigned, ambiguous | 6 |

**Half of all assignments are wrong.** The cause is `software engineer`,
which is far too broad: it captured a front-end role ("Client Platform"), a data
engineering role, a DevOps role and two engineering-management vacancies. The
classifier was described as "conservative". It is not conservative, it is
imprecise. Fixing it is a real task, not a tidy-up.

### Extraction on real text: recall 72-75%, precision 88-100%

Six real postings read in full. Twelve distinct missed terms, nine of them
simply absent from the 136-term dictionary: **Hibernate/JPA, ArgoCD, Istio,
Helm, Gradle, Maven, GitOps, Next.js, Crossplane**. Three more are alias gaps:
"test-driven development" spelled out (only `tdd` is listed), bare "API" (only
`rest api`), and bare "Go" (deliberately excluded to avoid false positives --
a defensible choice whose cost is now measured rather than hidden).

Construct validity showed up too: in one posting the only stated requirements
were "5+ years software engineering" and "bonus: TypeScript", yet AWS and Agent
Orchestration were matched from elsewhere in the advert. **A mention is not a
requirement**, and counting them alike inflates every share.

### Board expansion: a cautionary result

`tools/probe_boards.py` tried 41 candidate tokens. **Two were live** -- a ~5%
hit rate on guessing. Adding both took the corpus from 125 to 173 real
postings, but historically-eligible records went from 5 to 6 and the yield
FELL from 4.0% to 3.5%. More boards is not more evidence.

Worse: **`porter` on Lever is a US healthcare staffing firm**, not the Indian
logistics company. It contributed 26 nurse-practitioner vacancies in
Massachusetts and Florida before being caught and removed. Probing proved the
token was LIVE; it said nothing about whose board it was. `probe_boards.py` now
prints sample titles and locations so identity can be checked. Final corpus:
147 real postings from 4 verified boards.

---

## FRONTEND REBUILD: DONE (session 5)

`FRONTEND_PLAN.md` is executed. All five build steps are complete and the
analysis is untouched, exactly as the plan required.

What exists now:
- **`/`** -- landing page, no statistics and no p-values anywhere, not even in
  a tooltip. Carries the three-second image, the plain-language problem
  statement, live headline numbers, the role explorer (search + all four roles
  as example chips), how-it-works, the discarded-findings beat in plain words,
  and the limits box.
- **`/dashboard`** -- the previous single page, moved. Accepts `?role=`,
  verdicts now read "strong evidence" / "not enough data yet", p-values moved
  out of the table rows into the featured detail and the drawer.
- **`/method`** -- new. Every p-value (raw, BH-adjusted, Fisher) for all
  competencies, Wilson and Newcombe intervals, the threshold grid, both
  accuracy audits, the collection funnel, the 67 invariants and the full limits.

Defects found and fixed while building:
- the evidence quote rendered as `[object Object]` (`match_sentences` returns
  `{sentence, matched}`, not a string)
- the highlight used the canonical term, so a posting saying "GenAI" for the
  skill "LLM" highlighted nothing; it now highlights the alias that fired
- `/method` said "all 29 competencies tested" while the correction family is
  38 -- understating the correction burden. Now states both, and what the
  other 9 are
- the landing page called the sources "company hiring pages" and counted them
  as 2; greenhouse and lever are job-board SYSTEMS, not employers
- page responses were cacheable, so a rebuilt database could be read against
  stale HTML. `no-store` now applies to the pages as well as the API
- `run.py` printed "DEMO DATA: synthetic seed corpus" months after 147 real
  postings were ingested. The banner is now derived from the corpus

---

## THE SINGLE NEXT TASK

**Manually audit the 131 unclassified real postings.**

It is the only remaining item from the review that a person must do and code
cannot. At 107 records it is an afternoon, and it is more useful than any
classifier. Split genuine out-of-scope roles from ambiguous ones and missed
synonyms, then report precision among assigned records and recall among
genuinely in-scope ones. "18 of 125" currently measures neither.

After that, in order:
1. **Board token hunt — optimise YIELD, not board count.** `python -c
   "import pipeline,analysis;print(analysis.collection_yield(pipeline.connect()))"`
   or the Methods tab shows the funnel: 125 collected → 18 in a measured role →
   61 date-eligible → **5 usable (4.0%)**. Greenhouse contributes **0 usable**
   because it has no creation date. Forty more product-tech boards could leave
   the usable count unchanged. Prefer Lever, and employers whose roles a
   trainee could actually be hired into.
2. **Mark up `data/recall_review.md`.** 30 real postings await hand markup. No
   real recall number exists until someone does it.
3. **Start prospective collection now.** Freeze the first complete crawl of
   each board as a starting inventory, then record first-seen/last-seen per
   requisition. Existing open roles are pre-existing stock with unknown start
   dates, not newly opened roles — conflating those manufactures a hiring spike.

## SESSION LOG

**Session 5 - 2026-09-16.** Executed `FRONTEND_PLAN.md`: three routes, new
landing page, new method page, plain-language verdicts and `?role=` deep
links on the dashboard. Added one chart to the landing page built to the UK
Government Analysis Function conventions for statistical charts (headline
stating the message, statistical subtitle, source line, horizontal labels,
an accessible data table, and taught/not-taught spelled out in words so
colour never carries meaning alone). Fixed six defects, listed above. 67
invariants still hold; no external hosts on any page.

**Session 4 - 2026-09-16.** Implemented the external statistical and design
review. Added BH correction, Fisher exact cross-check, Newcombe change
intervals, threshold sensitivity and open-vocabulary discovery (`phrases.py`).
Fixed three confirmed defects. Rebuilt the front end around a decision brief
with per-finding provenance. Corrected the Google Sheets framing in this file
and the README: it was a withheld sign reversal, not a caught false discovery.

**Session 3 - 2026-09-09 and 2026-09-15.** Git root fixed (the repo was rooted
at `C:\Users\ayaan`, so any `git add` would have staged AppData and
`.claude.json`); repo scoped to the project, pushed to
github.com/lexion1337/sihtest, **now private**. Chart.js vendored — the
dashboard loads zero external hosts. Multi-source loader plus a provenance
banner computed from the data. **125 real postings ingested from ATS APIs**,
with the Greenhouse/Lever date split enforced end to end. Extraction measured
on real text for the first time: 5.4 skills/posting on measured roles vs 11.8
synthetic.

Two bugs caught by doing the measurement rather than assuming:
- The provenance banner only flipped when the synthetic count hit exactly zero,
  so a **mixed** corpus would have kept displaying "DEMO DATA — synthetic"
  while serving 125 real postings. An honesty-rule violation that would have
  shipped silently.
- `clean_text()` stripped HTML tags **before** unescaping, but Greenhouse
  returns content HTML-escaped. The markup survived and was then unescaped into
  visible text, so the extractor was reading HTML soup and
  `data-renderer-mark` was topping the candidate-miss list.

**Session 2 - 2026-09-06.** Data acquisition session. **Zero real postings
obtained.** Goal A (live NCS scrape) stopped at the permission gate: NCS has no
robots.txt, no documented API, and is a client-rendered SPA whose job-search
routes 404 after a rebuild, so scraping it would mean calling an undocumented
internal API — escalated for a human decision rather than done unilaterally.
Goal B (historical data) tested two routes to destruction: Wayback has ~17,700
archived Naukri JD URLs for 2024-25 but they are **empty client-rendered
shells** (verified across 10 snapshots, 2022-2025, 0-54 chars of visible text),
and data.gov.in's NCS catalog is aggregate counts only. Best real corpus found
is Djinni (141,897 dated JDs, MIT) — real text, wrong country. Full detail in
"DATA SOURCE INVESTIGATION" above. No code was changed; `scraper.fetch()` still
raises. Nothing was fabricated or relabelled.

**Session 1 — 2026-09-06.** Built the whole vertical slice: `CLAUDE.md`,
`PROGRESS.md`, seed generator, 136-skill dictionary, SQLite pipeline, drift
analysis, curriculum gap, FastAPI dashboard, scraper stub. Verified in a real
browser: chart renders with dashed low-confidence segments, all three roles and
both ranking modes switch correctly, gap table matches the CLI output, and the
evidence drawer returns exactly the postings behind each number.

Four bugs found and fixed during the session, all worth remembering:
- UAT alias `"sit"` matched the English verb in "You will **sit** with the
  business team" — 42 false positives. Demoted to case-sensitive `SIT`.
- `BRD` missed "Business Requirement Document**s**" — the plural blocked the
  word boundary. 24 recall misses. Fixed in the dictionary, because real
  postings will hit this too.
- Two seed surface forms cross-contaminated other skills ("LLM Evaluation"
  also matched LLM; "Excel Macros" also matched Advanced Excel). Removed from
  the generator so the round-trip check stays a clean regression signal.
- The dashboard had a race condition: two overlapping `render()` calls could
  resolve out of order and paint stale data after a role switch. Fixed with a
  sequence guard.
