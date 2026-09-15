# FRONTEND REBUILD PLAN

**Decided 2026-09-16. Written to disk deliberately so it survives a context
compact — a session starting cold should be able to execute this without the
conversation that produced it.**

Current state when this was written: commit `28aa389`, `python run.py` serves a
single-page dashboard at `/`. Everything below replaces that page's ROLE, not
its analysis. No backend maths changes.

---

## THE PROBLEM WITH THE CURRENT PAGE

It was built to an external reviewer's spec that said, in as many words, *"no
decorative illustrations, gauges, icons, a second chart or animated counters."*
That spec optimised for ONE moment: a judge leaning in and asking *"how do you
know that?"* Under that pressure, austerity reads as rigour and the page is
good.

It fails the other moment. A judge sees forty projects in a day. In the first
ten seconds they need to know **what this is**, and the page opens with
`benjamini-hochberg-adjusted p = 0.0225`. Someone who does not already know the
project cannot get in.

**Both audiences are real. The fix is not to decorate the evidence page — that
would destroy the thing that is actually good. The fix is to build the missing
half and route each audience to the right one.**

---

## THE DECISION: THREE LAYERS, PROGRESSIVE DISCLOSURE

| Route | Audience | Assumes | Statistics shown |
|---|---|---|---|
| `/` **Landing** | Anyone, zero context | nothing at all | **NONE** |
| `/dashboard` | Interested judge, teammate | the basic idea | counts and sample sizes; plain-language verdicts |
| `/method` | Teacher, statistician, sceptic | technical fluency | **everything** — p-values, BH, Fisher, power, audits |

**Rule: a reader should never meet a term the previous layer did not teach
them.**

### Where p-values go

**Nowhere on `/`. Not in a tooltip, not in small print.**

On `/dashboard` they are available but never the headline: the badge says
*"strong evidence"*, and the p-value sits in the expanded row or the drawer.

`/method` is where the statistics live, and it is framed as the answer to
*"did you just make this up?"* — the research and calculation we did, shown to
someone qualified to check it. That page can be as dense as it likes.

---

## LAYER 1 — `/` LANDING PAGE

No jargon. If a term needs explaining, either explain it in the same sentence
or do not use it.

### Vocabulary translation (use the right column on `/`)

| Do not say | Say |
|---|---|
| prevalence | how many job ads asked for it |
| 61.5% | **16 of 26 job ads** (percentage second, if at all) |
| competency | skill |
| corpus | our data / the job ads we collected |
| BH-adjusted p = 0.0225 | *(not on this page)* |
| supported | strong evidence |
| not supported at this precision | not enough data yet |
| time-series eligible | has a real posting date |
| drift | how demand changed over time |
| curriculum gap | skills employers want that the syllabus does not teach |

### Sections, in order

1. **Title + one sentence.**
   *"Job requirements change every few months. Syllabi change every few years.
   We measure the gap."*

2. **THE THREE-SECOND IMAGE.** The thing §12 of PROJECT_CONTEXT has asked for
   since the beginning and that has never been built. Two panels side by side:
   a real job ad on the left, the syllabus on the right, the missing skill lit
   up between them. Understandable with no narration. This is the single most
   important element on the page.

3. **The problem, three sentences.** Plain language, no statistics.

4. **Who this is for.** *"Built for a state skills department deciding which
   courses to update — not as career advice for students."* States the customer
   plainly, which is the framing point PROJECT_CONTEXT §4 keeps making.

5. **Live headline numbers**, pulled from `/api/overview` and `/api/findings`,
   never hardcoded. Job ads collected · skills tracked · findings with strong
   evidence · findings we threw out.

6. **Role explorer.** A search box over the roles, with all four shown as
   clickable example chips (Data Analyst, Backend Developer, Business Analyst,
   Other). Honest line beneath: *"Four roles measured so far. The pipeline
   works for any role with enough job ads."* Selecting one opens
   `/dashboard?role=…`.

7. **How it works** — four steps as a simple diagram: collect job ads → find
   the skills mentioned → compare against the syllabus → show what is missing.

8. **The rigour beat, in plain words.** *"We also show the findings we threw
   away: 5 had strong evidence, 26 did not."* No p-values. Link: *"See how we
   checked →"* to `/method`.

9. **Honest limits box.** Short, plain, visible. A judge who finds the caveat
   themselves scores it worse than one who is handed it.

10. **Two buttons:** *"See the evidence →"* (`/dashboard`) and *"How we checked
    →"* (`/method`).

---

## LAYER 2 — `/dashboard`

Essentially today's page, moved. Changes:

- Accept `?role=` so the landing page can deep-link.
- Decision badges become plain language: **"strong evidence"** /
  **"not enough data yet"**. The exact wording currently on screen
  (*"not supported at this precision"*) is correct but is expert register.
- p-values move out of the row and into the expanded detail and the drawer.
- Keep the evidence drawer exactly as it is. It is the best thing in the build.
- Keep every sample size. Keep the provenance banner.

---

## LAYER 3 — `/method`

New page. Everything technical, in one place, framed as *how we checked*.

- The decision rule, stated once: pooled two-proportion z-test,
  Benjamini-Hochberg across the whole per-role family, p < 0.05.
- Raw vs adjusted p-values and why correcting matters (13 → 8 for Data Analyst).
- Fisher exact as the sensitivity check, and the caveat that it gates nothing.
- Newcombe intervals for the change.
- Threshold sensitivity, with the "robust across the tested grid, not validity"
  wording kept intact.
- **The audits**: classifier precision 31–50% / recall 13–42%, extraction
  recall 72–75%. State that these are a machine first pass pending human
  confirmation.
- **The collection funnel**: 147 collected → 6 historically eligible.
- **`verify.py`**: 67 numerical invariants, and what they protect.
- **Limits**, in full: non-identification, coverage skew, calibration not yet
  demonstrated, closed vocabulary.

Move the current "Statistics" charts here or keep them on `/dashboard` —
either is fine, but they belong with the method, not the landing page.

---

## NON-NEGOTIABLE — SIMPLIFYING MUST NOT BECOME OVERCLAIMING

Plain language is a presentation choice. It is not permission to drop the
honesty rules. On every layer, including `/`:

1. **Every number keeps its sample size.** "16 of 26 job ads", never a bare 61.5%.
2. **The real/generated split is stated on every page.** In plain words on `/`:
   *"Most of this data is test data we generated to check the system works.
   147 job ads are real."*
3. **Thin samples are still flagged**, in plain words: *"only 8 job ads — too
   few to draw a conclusion."*
4. **Discarded findings stay visible.** They are the selling point, not an
   embarrassment.
5. **No synthetic finding is presented as a real market fact**, in any
   simplification.

If a plain-language rewrite would breach one of these, keep the longer sentence.

---

## CONSTRAINTS THAT DO NOT CHANGE

- **No webfonts, no CDN, no external host.** The page must render with the
  network off — venue Wi-Fi is shared by ~50 teams. Chart.js stays vendored at
  `static/chart.umd.min.js`.
- No npm, no bundler, no framework. Plain HTML/CSS/JS served by FastAPI.
- Warm brown/cream palette and the system serif headings introduced in
  `28aa389` carry over.
- **Charts must never be drawn into a hidden container** (0×0 canvas), and
  must not be scheduled with `requestAnimationFrame` (does not fire when the
  pane is not painting). Both bugs were hit and fixed; use `setTimeout` and
  draw lazily on first show.

## WHAT NOT TO BUILD

Animated counters, parallax, gradient heroes, icon sets, a second colour
system. They read as a template, and a government audience discounts them. The
landing page should feel like a well-set document, not a SaaS marketing site.

---

## BUILD ORDER

1. `app.py`: routes for `/`, `/dashboard`, `/method`; move current page to
   `static/dashboard.html`.
2. `static/index.html`: new landing page, including the three-second image and
   the role explorer.
3. `static/method.html`: the technical page.
4. `/dashboard`: `?role=` support and plain-language badges.
5. Run `python verify.py` (67 invariants) and check every route returns 200
   with zero external hosts.
