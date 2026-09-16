# Skill Drift Analyzer

**Smart India Hackathon 2026 · Problem Statement SIH26134 · Government of Maharashtra**

*Read this before you talk to a judge. It takes about ten minutes and it will
stop you saying something we cannot back up.*

---

## 1. The one-sentence version

> Job requirements change every few months. College syllabi and government
> skilling courses change every few **years**. Nobody measures the gap between
> the two — so we built the thing that measures it.

That's it. Everything below is detail.

---

## 1b. The two-minute demo — follow this order

If you are the one driving the laptop, this is the run. Do not improvise it.

**1. Open `/` and say nothing for three seconds.** Let them look at the picture:
a job ad on the left, the syllabus on the right, the missing skill between them.
Then one line:

> "Employers asked for LLM in 12 of 25 Data Analyst job ads last quarter. This
> syllabus teaches it in none of its 22 subjects. That gap is what we measure."

**2. Point at the note at the top before they ask.**

> "Most of this is test data we generated — 600 of 747. 147 are real job ads.
> It says so on every page."

Saying it first is worth more than any finding on the screen. If they catch it
and you didn't say it, everything after is downhill.

**3. Scroll to the two numbers: 14 findings supported, 65 thrown out.**

> "We test every candidate finding and publish the ones that failed, next to
> the ones that passed."

**4. Click into `/dashboard`, click any percentage.** The actual job ads appear.
Click one — the real text, with the sentence that triggered the match.

> "Every number on this site opens into the job ads it was computed from."

**5. Only if they push — open `/method`.**

> "Every p-value, both accuracy audits including the one where we score badly,
> and everything the system still cannot do."

**What to do when you do not know the answer:** say so, and say where it would
be checked. "I don't know, it'd be in the method page / the funnel table" beats
a guess every single time. This project's whole pitch is that we don't guess.

---

## 2. The problem, in plain language

A Data Analyst job posting today asks for things that didn't exist in 2023 —
LLMs, prompt engineering, dbt, Snowflake. A BTech syllabus written in 2022 is
still teaching what was current in 2022, and it cannot legally be revised
without going through a board that meets rarely.

So there is a **gap**. Everyone assumes it exists. Nobody has a number for it.

That's the actual failure: **not a shortage of training, a shortage of
information.** A state skills department cannot fix a mismatch it has never
measured.

---

## 3. WHO WE ARE BUILDING THIS FOR — read this twice

**The customer is the Government of Maharashtra. It is NOT the student.**

This is the single most common way our team could lose points. The emotional
story — *"3,000 people applied and nobody told them which skill they were
missing"* — is good for one sentence at the start. It is **not** the pitch.

Every output must be phrased as something an **administrator** does:

| ❌ Don't say this | ✅ Say this |
|---|---|
| "You're missing dbt" | "dbt appears in 32% of Data Analyst postings (n=25, p=0.002) and in no subject in this curriculum. This syllabus needs revision." |

Same number. Same evidence. Completely different buyer.

The problem statement's own phrase is **"a continuous, evidence-based
mechanism"**, and one of its stated outcomes is **"timely course revision."**
Use their words. When a judge asks *"what decision does your system change?"*,
the answer is: **which courses Maharashtra revises, and when.**

---

## 4. What we actually built

A pipeline. Data goes in one end, a checkable finding comes out the other.

```
  Job postings              Skill dictionary          Database
  (real + synthetic)  --->  136 skills + aliases -->  SQLite
                            regex, offline             |
                                                       v
                            Curriculum  <--------  Quarterly analysis
                            22 subjects            (shares, trends,
                            38 skills               significance)
                                 |
                                 v
                            THE FINDING:
                    "this skill is in X% of postings
                     and in zero subjects"
```

Five things it produces:

1. **Demand by role** — what Data Analysts / Backend Devs / Business Analysts are asked for
2. **Demand by skill, over time** — what's rising, what's dying
3. **Demand by location** — Pune vs Mumbai vs Bengaluru
4. **Curriculum gap** — demanded, rising, and taught by nobody → *add this*
5. **Course obsolescence** — taught, but nobody asks for it → *stop funding this*

Numbers 4 and 5 are the two halves of a real decision. Most teams will only
ever show you number 4.

---

## 5. ⚠️ WHAT IS REAL AND WHAT IS NOT — the section that matters most

Our corpus is **747 job postings**. They are **not all real**, and if you blur
this on stage we are finished.

| | Count | What it is |
|---|---|---|
| **Real** | **147** | Genuinely fetched from live company job boards |
| **Synthetic** | **600** | Generated by us to test the pipeline |
| **Total** | 747 | |

The real 147 came from public, documented, **unauthenticated** APIs that
companies publish so their careers pages can be embedded on other sites:

| Company | Via | Postings |
|---|---|---|
| Postman | Greenhouse | 67 |
| Meesho | Lever | 50 |
| Mindtickle | Lever | 19 |
| CRED | Lever | 11 |

**We did not scrape.** These endpoints are documented and unauthenticated, and
we did not bypass a login, ignore a `robots.txt`, or hammer anyone's server.

**But reading is not the same as republishing.** A public endpoint does not by
itself grant permission to redistribute the full descriptions it returns. We
keep the job text in the **private** repo and the local demo environment with
its source and fetch date recorded; check each provider's terms before putting
any of it in a public repository or dataset. If you ever make this repo public,
`git rm --cached` is not enough — the text is in git history from commit
`41e3c29` and would need a history rewrite.

### The rule you must follow

Every page carries an **"About this data"** note at the top saying the split in
plain words. It is computed from the data itself, not hardcoded — it cannot lie
about this. If the corpus ever became all-real, that sentence would rewrite
itself.

✅ **You may say:** *"Our pipeline detects real skill drift and correctly
rejects statistical noise."*

❌ **You may NOT say:** *"We found that LLM skills are rising in the Indian job
market."*

Why? Because the time-series chart is mostly **synthetic** data. It proves our
**detector works**. It does not prove anything about India's actual job market.
Those are different claims, and a sharp judge will separate them for you if you
don't do it yourself.

---

## 6. The numbers you can quote

All of these are computed live. Run `python analysis.py` and watch them appear.

**Corpus:** 747 postings · 147 real · 136 skills tracked · 22 curriculum
subjects teaching 38 skills.

**Findings across all four roles:** **14 supported, 65 discarded.** We show
both counts on the front page, because the second number is the point.

**Curriculum gap, Data Analyst, 2026-Q3 (n=25):** 17 candidates, of which 9
survive an uncorrected test and **only 4 survive once corrected for testing ~40
competencies at once**. Examples:

| Skill | Share | Sample | p-value | Verdict |
|---|---|---|---|---|
| LLM | 48.0% | 12 of 25 | 0.0001 | Supported (adjusted 0.0038) |
| dbt | 32.0% | 8 of 25 | 0.002 | Supported (adjusted 0.0253) |
| Power BI | 76.0% | 19 of 25 | 0.355 | **Not supported — we show it anyway** |

Those p-values are **raw**. We also correct for testing ~40 competencies at
once (Benjamini-Hochberg), because at p<0.05 across 40 tests you expect about
two false alerts by chance. After correction the Data Analyst list goes from
**9 to 4**. We report both numbers. Never quote the uncorrected one alone.

**Demand by location (India, 686 postings, 20 cities):** Bengaluru 118 ·
**Pune 83 · Mumbai 62 · Nagpur 27** (the three Maharashtra cities).

**Extraction accuracy (first-pass audit, 6 real postings):** recall
**72-75%**, precision **88-100%**. Twelve terms were missed; nine of them are
simply not in our dictionary (Hibernate/JPA, ArgoCD, Istio, Helm, Gradle,
Maven, GitOps, Next.js, Crossplane). Reproduce with
`python tools/score_extraction.py`.

**Role classification accuracy (first-pass audit, 16 assigned postings):**
precision **31-50%**, recall **13-42%**. This one is bad and we publish it
anyway — see §8. Reproduce with `python tools/score_classification.py`.

Both audits were scored by the same person who wrote the code being scored, so
treat them as a **machine first pass pending human confirmation**, and the
missed lists as a lower bound.

**Threshold robustness:** re-running the decision across nine threshold
combinations, the same four competencies (LLM, Prompt Engineering, Agent
Orchestration, dbt) pass in **every** cell. Say this narrowly: the cells reuse
the same postings, so they are **not nine independent confirmations**, and a
large change naturally survives nearby thresholds. It rules out one way of
being wrong — a threshold picked to flatter the result. It is not validity.

**Unmapped terms:** our dictionary has 136 terms, so anything outside it is
*unmeasured*, not absent. Scanning real postings surfaced **API, AI, DevOps,
SRE** as candidates. They are **candidates awaiting human review, not confirmed
competencies** — "AI" may describe a company's product, "SRE" may be a role
title. The number that will matter is how many reviewed candidates turn out to
be valid distinct competencies, not how many the script finds. And 65 adverts
from 2 employers is narrow support, however large the posting count looks.

---

## 7. Our two strongest moves (know these cold)

### A. We show you the findings we threw away

Most projects show you their best numbers. We run a **statistical significance
test** on every single one and mark the ones that fail.

Real example from our own data: the system once reported *"Google Sheets:
rising +12 percentage points"* when that skill was actually **falling**. The
decision rule withheld it (p=0.221).

Be precise about what that shows, because a sharp judge will be: nothing was
ever "discovered" — a p of 0.221 means no rejection happened at all. It is a
**noisy wrong-direction estimate that the rule correctly kept off the alert
list.** That is a real and useful property. It is not "we caught a false
positive."

When a judge asks *"how do you know that's not just noise?"* — most teams have
no answer. Ours is: **p=0.0001 versus p=0.221 — and the rejected one is still
on screen, labelled, rather than quietly dropped.**

> Be accurate about this: statistical testing is **routine** in professional
> labour analytics. It is rare *in a hackathon*, not novel in the field. Pitch
> it as **rigour, not invention.**

### B. Every number is clickable

Click any percentage on the dashboard → it lists the **exact postings** counted
in it → click one → you read the **full original job description**.

The `dbt` cell says "8 of 25". Click it, and exactly 8 postings appear.

This is the answer to *"did you just make these numbers up?"* We don't argue.
We show the evidence.

---

## 8. What's wrong with it — say these BEFORE a judge finds them

Volunteering a weakness reads as confidence. Getting caught reads as sloppiness.

1. **Only 16 of our 147 real postings are in a role we measure.** These company
   boards are mostly sales, marketing and finance jobs. Our coverage is thin
   and we know it.

2. **Only 6 real postings can go in the time chart.** Greenhouse only tells us
   when a posting was *last edited*, not when it was *created* — so we
   deliberately exclude all 67 of those from the quarterly view. The site says
   so on screen. Our design decision, stated up front.

   We added two more boards and it did **not** help: collected went from 125 to
   147, historically eligible went from 5 to 6, and the yield percentage barely
   moved (4.1%). The constraint is not how many boards we query.

3. **We cover companies like Meesho and CRED, not TCS or Infosys** — where most
   Indian CS graduates actually go. Those firms use Workday and in-house
   systems with no public API. A real limitation.

4. **Our curriculum is a BTech CSE syllabus; the problem statement is really
   about ITIs and NSQF trades.** We own this: the curriculum layer is
   **pluggable**. The identical comparison runs against an NSQF qualification
   pack. We demonstrate on the syllabus we could actually obtain and verify.

5. **A supported change in advertised wording is not evidence that changing a
   course would improve employment.** Those are different claims. Our
   instrument can test the first; it does not identify the second. An absent
   syllabus keyword may be covered by a broader learning outcome, and a present
   one may be taught badly. This is the strongest argument against us and we
   state it before anyone else does.

6. **Our role classifier is bad, and we publish the number.** On a hand-checked
   sample of 16 assigned postings: precision **31-50%**, recall **13-42%**. The
   cause is known — our title rule for "software engineer" is too broad. We have
   deliberately **not** fixed it yet, because tuning it against verdicts written
   by its own author would fit it to our sample rather than improve it. Extraction
   is better (recall 72-75%) but rests on only 6 postings.

   If a judge presses on one weakness, it will probably be this one. The answer
   is: *"we measured it, we published it unflattering, and we know why it fails."*

7. **Sample sizes are small, and we can quantify how small.** Simulated power
   to detect a 10-percentage-point shift is about **9% at n=25**, 44% at n=100,
   77% at n=200. Our synthetic test data plants much larger shifts (LLM moves
   45 points), which is why the detector finds them. The honest sentence is:
   *"at this sample size we can detect a 40-point shift, not a 10-point one."*
   Every percentage on screen carries its sample size, and anything under 20
   postings is flagged.

---

## 9. How to run it

```bash
python run.py
```

Open http://127.0.0.1:8000. That's all — no npm, no Docker, no API keys.
You need Python 3 and one install: `pip install fastapi uvicorn`.

**There are three pages, and which one you show depends on who is asking:**

| Page | Show it to | What is on it |
|---|---|---|
| `/` | anyone, including someone who knows nothing about the project | The problem, the one picture, the headline numbers, the role search. **No statistics at all.** |
| `/dashboard` | a judge who is interested and leaning in | The evidence: every finding with its sample size, and click-through to the actual job ads |
| `/method` | a teacher, a statistician, anyone who says "prove it" | Every p-value, both accuracy audits, the collection funnel, the full list of limits |

Start every demo on `/`. Do **not** open on `/method` — it is dense on purpose
and it will lose a non-technical listener in ten seconds. Its job is to be
there when someone asks *"did you just make this up?"*

| Command | What it does |
|---|---|
| `python run.py` | Start the dashboard |
| `python analysis.py` | Print all the findings to your terminal |
| `python ingest_ats.py` | Fetch fresh real postings from the job boards |
| `python skills.py` | Show the skill dictionary |
| `python verify.py` | Check all 67 numerical invariants still hold |
| `python tools/score_extraction.py` | Re-run the extraction accuracy audit |
| `python tools/score_classification.py` | Re-run the classifier accuracy audit |

**It works with the Wi-Fi off.** We deliberately downloaded the chart library
into the project instead of loading it from the internet, because the venue
Wi-Fi will be shared by ~50 teams.

---

## 10. What you can do to help — no coding required

**The single most valuable job, and it needs zero programming:**

> **Find more company job-board tokens — but the RIGHT ones.** We have 4 boards.
> More boards is not automatically more evidence: of 147 real postings only
> **6 are usable** (in a measured role AND carrying a true creation date). All
> 67 Greenhouse postings contribute **zero**, because Greenhouse gives no
> creation date. We already proved this the hard way — adding two boards raised
> collected by 22 and usable by 1. Prefer **Lever** (usable dates) and employers
> whose roles a trainee could actually be hired into.
> Google `site:jobs.lever.co` or `site:boards.greenhouse.io`, find Indian tech
> companies, and note the short name in the URL.
> `jobs.lever.co/meesho` → the token is `meesho`.
> Add it to `data/boards.json`. That's the whole job.
> **Prefer Lever** — its dates are usable and Greenhouse's are not.

This is the one thing that fixes our weakest number (sample size). It's pure
legwork and it parallelises across all six of us.

**Second most valuable:** open `data/recall_review.md`, read a few real job
postings, and write down any skill our system *should* have spotted but didn't.
That gives us a real accuracy figure — which is currently our biggest gap.

---

## 11. The five questions judges will ask

**Q: Where did your data come from?**
Public ATS APIs — Greenhouse and Lever. 147 real postings from Postman, Meesho,
Mindtickle and CRED, plus 600 synthetic records for testing, labelled as such
throughout. *Never say "we scraped job websites."*

**Q: How do you know your skill extraction works on real text?**
We hand-checked a sample: recall 72-75%, precision 88-100%. It is a small
sample (6 postings) and the same author wrote both the extractor and the
verdicts, so it is a first pass, not a final figure. *Say the limitation
plainly, then show the click-through evidence.*

**Q: Isn't most of your data fake?**
Yes — 600 of 747, and we say so on every page before anyone asks. The synthetic
records exist to prove the pipeline detects a drift curve we planted. The 147
real ones prove it runs on real text. *We never mix the two claims.*

**Q: What about TCS, Infosys and Wipro?**
They don't use public ATS boards. We scoped to companies we can access
legitimately, and the dashboard states that scope.

**Q: How is this better than LinkedIn or Lightcast?**
It isn't "better" — it's **different**. They sell commercial labour-market
intelligence. We are the **government decision layer**: observed demand
connected to Maharashtra's own training supply, open and auditable.
*Never claim nobody has built labour analytics — Lightcast has, and Maharashtra
already runs Mahaswayam.*

**Q: What decision does your system actually change?**
**Timely course revision** — their phrase. Which courses to update, where, and
which to stop funding.

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Drift** | A skill's demand changing over time |
| **Share** | % of postings mentioning a skill. Always shown with its sample size |
| **n** | Sample size — how many postings a percentage was computed from |
| **p-value** | Chance the result is random noise. Below 0.05 = probably real |
| **Low confidence** | Fewer than 20 postings — not enough to claim anything |
| **ATS** | Applicant Tracking System — Greenhouse, Lever, Ashby |
| **Synthetic** | Data we generated ourselves to test the pipeline |
| **NSQF** | National Skills Qualifications Framework — government course standards |

---

## 13. The five honesty rules we enforce in code

1. Every number traces to real records you can click through to
2. Never invent a statistic for a slide
3. Synthetic data is labelled everywhere it appears
4. Every percentage shows its sample size
5. Samples too small to support a claim are flagged, not smoothed over

These aren't style preferences. **One invented number caught by a judge ends
our run.** When in doubt, show the smaller, uglier, true number.

---

*Detailed technical state: `PROGRESS.md`. Architecture and conventions:
`CLAUDE.md`.*
