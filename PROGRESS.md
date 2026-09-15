# PROGRESS.md

**Update this file at the end of every session.** Read `CLAUDE.md` first — it
holds the problem statement, the honesty rules, and the architecture.

Last updated: **2026-09-15** (session 3)
Deadline: **SIH internal hackathon, 16 September 2026 — TOMORROW.**
Venue: REVA Rangasthala / Amphi Theatre, 8:30 AM - 4:30 PM.
Bar for internal: **30% of the project ready**, measured against the problem
statement's 15 required elements, not against lines of code.

---

## TL;DR

`python run.py` serves the dashboard on http://127.0.0.1:8000. It works.

**The corpus is now MIXED: 725 postings = 600 synthetic + 125 REAL.** The real
ones come from public ATS job-board APIs (Greenhouse, Lever), ingested by
`ingest_ats.py` on 9 September. The provenance banner reads "MIXED DATA" and is
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

**9. Scraper — stub only, as specified.** `scraper.py` fixes the `fetch(role,
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
alone. During this session the analysis labelled Google Sheets "rising +12 pp"
for Data Analyst when the generator's own curve for it is *declining*
(0.30 → 0.18). That is a false finding produced purely by small buckets.

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

## THE SINGLE NEXT TASK

**It is the day before the hackathon. Stop building infrastructure.**

The bar is 30% of the problem statement's 15 elements. We cover roughly 4:
demand by role, demand by skill, real job-posting signals, and drift as an
emerging-technology proxy. Two more are cheap and both are named explicitly in
the PS:

1. **Demand by LOCATION.** The data is already ingested and currently
   discarded. 31 distinct location strings across the real corpus, **66
   postings in India**, concentrated in Bangalore (46). Needs a normaliser —
   `Bangalore, Karnataka` / `bengaluru` / `Bengaluru, Karnataka, India` are one
   city written three ways. This is the first step toward the PS's
   "district-level training plans".

2. **Flag obsolete or oversupplied courses.** Reverse the existing diff: skills
   the curriculum teaches that demand does not want. Tells an administrator
   what to **stop** doing, which is a better slide than the gap table.

Then **reframe every UI string from student-facing to administrator-facing**
(copy only), and **rehearse the demo sequence out loud, twice**.

**Explicitly dropped: the pytest suite (T5).** Tests protect a codebase over
weeks of change. There is one day left and then a demo. Wrong investment now;
revisit before the Grand Finale.

### If you find 20 spare minutes

Mark up 10 of the 30 postings in `data/recall_review.md` by hand. A real recall
number is the answer to the second-hardest judge question, and right now that
answer is "we measured a proxy".

## SESSION LOG

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
