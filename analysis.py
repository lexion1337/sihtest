"""
analysis.py -- quarterly skill drift + curriculum gap. Pure reads over SQLite.

Every number this module emits is a count or a ratio of counts over rows in
data/skills.db. Nothing is smoothed, imputed, extrapolated or hand-tuned. If a
bucket is thin, we say so rather than hiding it (see LOW_CONFIDENCE_N).

Definitions used throughout
---------------------------
share(skill, role, quarter)
    postings in that (role, quarter) bucket whose description mentioned the
    skill, divided by ALL postings in that same bucket. Expressed in percent.
    The denominator is always postings, never skill mentions.

latest_share
    share in the most recent quarter that has any postings for the role. This
    is the number quoted in the gap table, so it is reported raw.

baseline_share
    POOLED share over the first two quarters that have postings: postings
    mentioning the skill across both quarters, divided by all postings across
    both quarters. Pooling cuts sampling noise on the baseline, which matters
    because buckets here are n=12-25. The latest quarter is deliberately NOT
    pooled -- we quote it, so we show it as measured.

change_pp
    latest_share - baseline_share, in percentage points.

trend
    rising    if change_pp >= +TREND_DELTA_PP
    declining if change_pp <= -TREND_DELTA_PP
    stable    otherwise

significant
    Two-proportion z-test, baseline window vs latest quarter, p < ALPHA.
    This matters more than it looks. At n=25 a skill can move 12 percentage
    points on sampling noise alone, so an unqualified "rising" label is not a
    finding. trend gives the DIRECTION; significant says whether the sample
    can actually support the claim. The UI must not present a non-significant
    trend as established -- see the honesty rules in CLAUDE.md.

Confidence interval
    95% Wilson score interval on the latest quarter's share. Wilson rather
    than the normal approximation because it stays sane at p near 0 or 1,
    which is exactly where the interesting emerging skills sit.

Run:  python analysis.py
"""

import json
import math
import os

import pipeline
import skills as skills_mod

HERE = os.path.dirname(os.path.abspath(__file__))
CURRICULUM_PATH = os.path.join(HERE, "data", "curriculum.json")

# A quarter with fewer than this many postings cannot support a percentage
# claim. Computed anyway, but flagged, and the UI must render the flag.
LOW_CONFIDENCE_N = 20

# Minimum movement in percentage points before we call a skill rising/declining.
TREND_DELTA_PP = 5.0

# A skill must be asked for in at least this share of the latest quarter's
# postings before its absence from the curriculum is worth reporting.
GAP_MIN_SHARE_PCT = 15.0

Z95 = 1.959963984540054


def wilson95(count, n):
    """95% Wilson score interval for a proportion, returned in percent."""
    if n <= 0:
        return (0.0, 0.0)
    p = count / n
    z2 = Z95 * Z95
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (round(max(0.0, centre - half) * 100, 1),
            round(min(1.0, centre + half) * 100, 1))


def two_proportion_p(c1, n1, c2, n2):
    """Two-sided two-proportion z-test. Returns (z, p_value).

    Null hypothesis: the baseline window and the latest quarter were drawn
    from the same underlying rate. A small p means the movement is unlikely
    to be sampling noise at this sample size.
    """
    if n1 <= 0 or n2 <= 0:
        return (0.0, 1.0)
    p1, p2 = c1 / n1, c2 / n2
    pool = (c1 + c2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p2 - p1) / se
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))
    return (round(z, 3), round(p, 4))


def fisher_exact_2x2(a, b, c, d):
    """Two-sided Fisher's exact test on [[a,b],[c,d]]. Returns a p-value.

    Why this exists alongside the z-test. At n=25 with a skill sitting near 5%
    prevalence, expected cell counts fall to 1-3 and the normal approximation
    is a poor description of a discrete, skewed sampling distribution. Fisher
    conditions on the margins and is finite-sample valid under its assumptions.

    It is also SEVERELY conservative in this regime -- a simulated reference at
    nominal 5% put the pooled z-test near 1.98 / 4.87 / 5.49 percent actual
    rejection at true prevalence 5 / 10 / 20 percent, against Fisher at
    0.08 / 0.88 / 2.22 percent. So this is reported as a conservative cross-
    check, not as a replacement: if a finding survives Fisher it is not an
    artefact of the normal approximation.

    Neither test fixes employer clustering, selection bias or repeated
    observations of the same employer. "Exact" describes a calculation under a
    model, not validity for Maharashtra's labour market.
    """
    n = a + b + c + d
    if n == 0:
        return 1.0
    r1, r2, k = a + b, c + d, a + c
    if r1 == 0 or r2 == 0 or k == 0 or (b + d) == 0:
        return 1.0

    def prob(x):
        return (math.comb(r1, x) * math.comb(r2, k - x)) / math.comb(n, k)

    lo, hi = max(0, k - r2), min(r1, k)
    p_obs = prob(a)
    total = 0.0
    for x in range(lo, hi + 1):
        px = prob(x)
        if px <= p_obs * (1 + 1e-9):
            total += px
    return round(min(1.0, total), 4)


def newcombe_diff_ci(c_base, n_base, c_late, n_late):
    """95% Newcombe (Wilson-based) interval for the DIFFERENCE in proportions.

    The Wilson intervals already shown are for each PREVALENCE separately.
    Checking whether two such intervals overlap is not a test of the
    difference and is needlessly conservative. Newcombe's method builds an
    interval for the difference itself out of the two Wilson intervals, and
    behaves far better than a Wald difference interval at small n.

    Returned in percentage points, for latest minus baseline.
    """
    if n_base <= 0 or n_late <= 0:
        return (0.0, 0.0)
    p1, p2 = c_late / n_late, c_base / n_base
    l1, u1 = (v / 100.0 for v in wilson95(c_late, n_late))
    l2, u2 = (v / 100.0 for v in wilson95(c_base, n_base))
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (round(max(-1.0, lower) * 100, 1), round(min(1.0, upper) * 100, 1))


# Significance threshold for calling a trend a finding rather than a wiggle.
ALPHA = 0.05

# Multiple-comparison correction. Every measured skill for a role is tested, so
# at ALPHA=0.05 across ~40 skills roughly 2 false alerts are expected by chance
# alone. Benjamini-Hochberg rather than Bonferroni because this list SCREENS
# candidates for employer consultation: a false positive costs a wasted
# meeting, not a catastrophe, so false-discovery rate is the appropriate error
# rate rather than family-wise error.
#
# Recorded deliberately: BH assumes valid null p-values and independence (or
# positive dependence). Skills co-occur within postings and the same employers
# recur across periods, so neither condition is established here. This is an
# improvement over raw p, not a warranty.
CORRECTION_METHOD = "benjamini-hochberg"

# THE DECISION RULE, DECLARED IN ONE PLACE.
#
# Exactly one procedure controls the "supported" badge: a pooled two-sided
# two-proportion z-test, corrected with Benjamini-Hochberg across the complete
# family of every competency measured for that role. Fisher's exact test is
# computed and displayed as a SENSITIVITY CHECK and never gates anything.
#
# This matters because reporting two tests invites picking whichever one
# supports each finding. verify.py asserts that the supported list is a strict
# consequence of the BH-adjusted z-test, so the rule cannot drift.
PRIMARY_TEST = "pooled two-proportion z-test, two-sided"
PRIMARY_RULE = ("BH-adjusted p < alpha, corrected across every competency "
                "measured for the role")
SENSITIVITY_TEST = "Fisher exact, two-sided (reported only, gates nothing)"


def benjamini_hochberg(pvals):
    """Step-up BH adjusted p-values, returned in input order.

    adj(i) = min over k >= i of min(1, m/k * p(k)) on the ascending sort,
    which keeps the adjusted sequence monotone.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, min(1.0, pvals[i] * m / rank))
        adj[i] = round(running, 4)
    return adj

# ------------------------------------------------------------- provenance

# Sources that are generated rather than observed. Anything not listed here is
# treated as real data from a named origin (greenhouse, lever, ashby, ...).
SYNTHETIC_SOURCES = {"synthetic"}


def provenance(sources):
    """Classify a corpus from its {source: count} map.

    Returns one of "empty", "synthetic", "mixed", "real". The UI banner keys
    off this rather than any hardcoded flag, so a corpus that gains real
    records starts describing itself accurately the moment it is rebuilt --
    nobody has to remember to flip a switch. That is honesty rule 3 enforced
    in code rather than in intent.
    """
    total = sum(sources.values())
    if not total:
        return "empty"
    synth = sum(n for s, n in sources.items() if s in SYNTHETIC_SOURCES)
    if synth == total:
        return "synthetic"
    if synth == 0:
        return "real"
    return "mixed"


def split_counts(sources):
    """(synthetic_count, real_count) for a {source: count} map."""
    synth = sum(n for s, n in sources.items() if s in SYNTHETIC_SOURCES)
    return synth, sum(sources.values()) - synth


# ------------------------------------------------------------- curriculum

def load_curriculum(path=CURRICULUM_PATH):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    known = set(skills_mod.all_skills())
    taught, unknown = set(), []
    for sub in doc["subjects"]:
        for s in sub.get("skills", []):
            if s not in known:
                unknown.append((sub["code"], s))
            taught.add(s)
    if unknown:
        raise ValueError(
            "curriculum.json references skills absent from skills.py: %s" % unknown)
    doc["taught_skills"] = sorted(taught)
    doc["n_subjects"] = len(doc["subjects"])
    return doc


# ------------------------------------------------------------------ drift

def roles(con):
    return [r["role"] for r in con.execute(
        "SELECT role, COUNT(*) c FROM postings GROUP BY role ORDER BY role")]


def _quarter_totals(con, role):
    """Postings per quarter for a role, EXCLUDING rows whose date is only a
    last-modified timestamp (see ingest_ats.py). Those rows cannot be binned
    by quarter without asserting something the source never told us."""
    rows = con.execute(
        "SELECT quarter, COUNT(*) AS n FROM postings "
        "WHERE role = ? AND ts_eligible = 1 "
        "GROUP BY quarter ORDER BY quarter", (role,)).fetchall()
    return [(r["quarter"], r["n"]) for r in rows]


def ts_exclusions(con, role=None):
    """What the time series is leaving out, and why. Surfaced in the UI."""
    sql = ("SELECT source, date_kind, COUNT(*) AS n FROM postings "
           "WHERE ts_eligible = 0")
    args = []
    if role:
        sql += " AND role = ?"
        args.append(role)
    sql += " GROUP BY source, date_kind ORDER BY n DESC"
    rows = [{"source": r["source"], "date_kind": r["date_kind"], "n": r["n"]}
            for r in con.execute(sql, args)]
    return {"n_excluded": sum(r["n"] for r in rows), "by_source": rows}


def drift(con, role):
    """Full per-skill quarterly series and summary for one role."""
    totals = _quarter_totals(con, role)
    if not totals:
        return {"role": role, "quarters": [], "skills": [], "n_postings": 0,
                "excluded_from_time_series": ts_exclusions(con, role),
                "latest_quarter": None, "latest_n": 0, "baseline_quarters": [],
                "thresholds": {"low_confidence_n": LOW_CONFIDENCE_N,
                               "trend_delta_pp": TREND_DELTA_PP,
                               "gap_min_share_pct": GAP_MIN_SHARE_PCT,
                               "alpha": ALPHA}}
    qs = [q for q, _n in totals]
    n_by_q = dict(totals)

    counts = {}
    for r in con.execute(
            "SELECT skill, quarter, COUNT(DISTINCT posting_id) AS c "
            "FROM posting_skills WHERE role = ? AND ts_eligible = 1 "
            "GROUP BY skill, quarter", (role,)):
        counts.setdefault(r["skill"], {})[r["quarter"]] = r["c"]

    latest_q = qs[-1]
    latest_n = n_by_q[latest_q]
    baseline_qs = qs[:2]

    out = []
    for skill, by_q in counts.items():
        series = []
        for q in qs:
            n = n_by_q[q]
            c = by_q.get(q, 0)
            series.append({
                "quarter": q,
                "n": n,
                "count": c,
                "share": round(100.0 * c / n, 1) if n else 0.0,
                "low_confidence": n < LOW_CONFIDENCE_N,
            })

        first_seen = next((p["quarter"] for p in series if p["count"] > 0), None)
        latest_count = by_q.get(latest_q, 0)
        latest_share = round(100.0 * latest_count / latest_n, 1) if latest_n else 0.0
        base_pts = [p for p in series if p["quarter"] in baseline_qs]
        baseline_count = sum(p["count"] for p in base_pts)
        baseline_n = sum(p["n"] for p in base_pts)
        baseline_share = round(100.0 * baseline_count / baseline_n, 1) if baseline_n else 0.0
        change = round(latest_share - baseline_share, 1)
        if change >= TREND_DELTA_PP:
            trend = "rising"
        elif change <= -TREND_DELTA_PP:
            trend = "declining"
        else:
            trend = "stable"
        lo, hi = wilson95(latest_count, latest_n)
        z, pval = two_proportion_p(baseline_count, baseline_n, latest_count, latest_n)
        p_fisher = fisher_exact_2x2(baseline_count, baseline_n - baseline_count,
                                    latest_count, latest_n - latest_count)
        diff_lo, diff_hi = newcombe_diff_ci(baseline_count, baseline_n,
                                            latest_count, latest_n)

        out.append({
            "skill": skill,
            "category": skills_mod.skill_category(skill),
            "series": series,
            "first_seen": first_seen,
            "latest_quarter": latest_q,
            "latest_n": latest_n,
            "latest_count": latest_count,
            "latest_share": latest_share,
            "latest_ci95": [lo, hi],
            "baseline_quarters": baseline_qs,
            "baseline_count": baseline_count,
            "baseline_n": baseline_n,
            "baseline_share": baseline_share,
            "change_pp": change,
            "trend": trend,
            "z": z,
            "p_value": pval,
            "p_fisher": p_fisher,
            "significant_fisher": p_fisher < ALPHA,
            "diff_ci95": [diff_lo, diff_hi],
            "significant": pval < ALPHA,
            "total_postings_with_skill": sum(by_q.values()),
            "low_confidence_latest": latest_n < LOW_CONFIDENCE_N,
        })

    # Correct across every skill tested for this role. The family is ALL
    # measured skills, not just the ones that later pass the gap filters.
    adj = benjamini_hochberg([s["p_value"] for s in out])
    for s, a in zip(out, adj):
        s["p_adjusted"] = a
        s["significant_adjusted"] = a < ALPHA
        s["correction_family_size"] = len(out)
        s["correction_method"] = CORRECTION_METHOD

    out.sort(key=lambda s: -s["latest_share"])
    return {
        "role": role,
        "correction": {
            "method": CORRECTION_METHOD,
            "family_size": len(out),
            "alpha": ALPHA,
            "n_significant_raw": sum(1 for s in out if s["significant"]),
            "n_significant_adjusted": sum(1 for s in out if s["significant_adjusted"]),
            "n_significant_fisher": sum(1 for s in out if s["significant_fisher"]),
        },
        "excluded_from_time_series": ts_exclusions(con, role),
        "quarters": [{"quarter": q, "n": n, "low_confidence": n < LOW_CONFIDENCE_N}
                     for q, n in totals],
        "n_postings": sum(n for _q, n in totals),
        "latest_quarter": latest_q,
        "latest_n": latest_n,
        "baseline_quarters": baseline_qs,
        "skills": out,
        "thresholds": {
            "low_confidence_n": LOW_CONFIDENCE_N,
            "trend_delta_pp": TREND_DELTA_PP,
            "gap_min_share_pct": GAP_MIN_SHARE_PCT,
            "alpha": ALPHA,
        },
    }


def top_skills(drift_result, k=8, rank_by="latest"):
    """Skills for the chart. rank_by: 'latest' share, or 'change' (movers)."""
    rows = list(drift_result["skills"])
    if rank_by == "change":
        rows.sort(key=lambda s: -abs(s["change_pp"]))
    else:
        rows.sort(key=lambda s: -s["latest_share"])
    return rows[:k]


# ---------------------------------------------------------- finding detail

def observation_cutoff(con):
    """The latest posted_date actually in the corpus.

    A quarter LABEL does not mean the quarter was observed to its end. Saying
    "2026-Q3" when collection stopped on 8 September implies six weeks of data
    that do not exist, so every analysis surfaces this date.
    """
    r = con.execute("SELECT MAX(posted_date) AS d FROM postings").fetchone()
    return r["d"] if r else None


def cohort_composition(con, role, skill=None, quarter=None, eligible_only=True):
    """Who actually produced a number: real vs synthetic, by source.

    The corpus-wide banner says the CORPUS is mixed. It does not say whether
    THIS 48% came from real postings or generated ones. A judge is entitled to
    ask, so every headline figure carries its own composition.
    """
    where = ["p.role = ?"]
    args = [role]
    if eligible_only:
        where.append("p.ts_eligible = 1")
    if quarter:
        where.append("p.quarter = ?")
        args.append(quarter)
    if skill:
        sql = ("SELECT p.source, COUNT(DISTINCT p.id) AS c FROM postings p "
               "JOIN posting_skills s ON s.posting_id = p.id "
               "WHERE " + " AND ".join(where) + " AND s.skill = ? GROUP BY p.source")
        args = args + [skill]
    else:
        sql = ("SELECT p.source, COUNT(*) AS c FROM postings p WHERE "
               + " AND ".join(where) + " GROUP BY p.source")
    by_source = {r["source"]: r["c"] for r in con.execute(sql, args)}
    synth, real = split_counts(by_source)
    return {"by_source": by_source, "n_synthetic": synth, "n_real": real,
            "total": synth + real, "provenance": provenance(by_source)}


def _syllabus_mapping(cur, skill):
    """Subject-level evidence, not an inference from absence in an array."""
    subs = _subjects_teaching(cur, skill)
    return {
        "taught": bool(subs),
        "n_subjects_teaching": len(subs),
        "n_subjects_total": cur["n_subjects"],
        "subjects": subs,
        "syllabus_name": cur["name"],
        "syllabus_version": cur.get("version"),
        "syllabus_source": cur.get("source"),
    }


def _baseline_composition(con, role, quarters):
    """Composition of the pooled baseline window."""
    agg = {}
    for q in quarters or []:
        c = cohort_composition(con, role, None, q)
        for k, v in c["by_source"].items():
            agg[k] = agg.get(k, 0) + v
    synth, real = split_counts(agg)
    return {"by_source": agg, "n_synthetic": synth, "n_real": real,
            "total": synth + real, "provenance": provenance(agg)}


def _scenario_label(num, den, base):
    """One phrase for what kind of comparison this actually is.

    If numerator, denominator and baseline are all generated records, the
    finding is a SYNTHETIC VALIDATION SCENARIO -- it demonstrates that the
    detector works, and says nothing about any labour market. Making a reader
    infer that from three separate counts is worse than saying it.
    """
    provs = {num["provenance"], den["provenance"], base["provenance"]}
    provs.discard("empty")
    if provs == {"synthetic"}:
        return {"key": "synthetic",
                "label": "Synthetic validation scenario",
                "detail": ("Numerator, denominator and baseline are all generated "
                           "records. This demonstrates the detector; it is not a "
                           "measurement of any labour market.")}
    if provs == {"real"}:
        return {"key": "real", "label": "Real-posting finding",
                "detail": "Numerator, denominator and baseline are all observed records."}
    return {"key": "mixed", "label": "Mixed-source finding",
            "detail": ("Real and generated records are combined in this comparison. "
                       "Check the numerator, denominator and baseline composition "
                       "before quoting it.")}


def finding(con, role, skill, curriculum=None, drift_result=None):
    """Everything needed to state one finding honestly, in one payload."""
    cur = curriculum or load_curriculum()
    d = drift_result or drift(con, role)
    m = next((x for x in d["skills"] if x["skill"] == skill), None)
    if m is None:
        return None
    lq = d["latest_quarter"]
    return {
        "role": role,
        "skill": skill,
        "category": m["category"],
        "latest_quarter": lq,
        "observed_through": observation_cutoff(con),
        "prevalence": {
            "share": m["latest_share"], "count": m["latest_count"],
            "n": m["latest_n"], "ci95": m["latest_ci95"],
            "ci_is_for": "prevalence in the latest quarter, not for the change",
            "low_confidence": m["low_confidence_latest"],
        },
        "baseline": {
            "quarters": m["baseline_quarters"], "count": m["baseline_count"],
            "n": m["baseline_n"], "share": m["baseline_share"],
            "definition": "pooled across the first two observed quarters",
        },
        "change": {"change_pp": m["change_pp"], "trend": m["trend"]},
        "statistics": {
            "test": PRIMARY_TEST,
            "rule": PRIMARY_RULE,
            "sensitivity_test": SENSITIVITY_TEST,
            "p_raw": m["p_value"],
            "p_adjusted": m["p_adjusted"],
            "correction": m["correction_method"],
            "family_size": m["correction_family_size"],
            "alpha": ALPHA,
            "decision": ("supported" if m["significant_adjusted"]
                         else "not supported at this precision"),
            "p_fisher": m["p_fisher"],
            "fisher_note": ("survives a conservative Fisher exact cross-check"
                            if m["significant_fisher"]
                            else "does NOT survive a conservative Fisher exact cross-check"),
            "diff_ci95": m["diff_ci95"],
            "diff_ci_note": "95% Newcombe interval for the CHANGE, in percentage points",
        },
        "composition": cohort_composition(con, role, skill, lq),
        # The numerator's composition alone is not enough: a synthetic
        # numerator over a mixed denominator is a different claim from a
        # wholly synthetic comparison, and a reader should not have to
        # reconstruct which one they are looking at.
        "denominator_composition": cohort_composition(con, role, None, lq),
        "baseline_composition": _baseline_composition(con, role, m["baseline_quarters"]),
        "scenario": _scenario_label(
            cohort_composition(con, role, skill, lq),
            cohort_composition(con, role, None, lq),
            _baseline_composition(con, role, m["baseline_quarters"])),
        "syllabus": _syllabus_mapping(cur, skill),
        "cohort_definition": (
            "postings with role=%s, quarter=%s, excluding records whose only "
            "date is a last-modified timestamp" % (role, lq)),
    }


def findings(con, role, curriculum=None, drift_result=None):
    """Supported and discarded drift alerts, both returned in full.

    Discarded findings are returned as first-class data, not omitted. Showing
    what failed the decision rule is the point.
    """
    cur = curriculum or load_curriculum()
    d = drift_result or drift(con, role)
    taught = set(cur["taught_skills"])

    supported, discarded = [], []
    for m in d["skills"]:
        row = {
            "skill": m["skill"], "category": m["category"],
            "latest_share": m["latest_share"], "latest_count": m["latest_count"],
            "latest_n": m["latest_n"], "latest_ci95": m["latest_ci95"],
            "baseline_share": m["baseline_share"], "baseline_count": m["baseline_count"],
            "baseline_n": m["baseline_n"], "change_pp": m["change_pp"],
            "trend": m["trend"], "p_raw": m["p_value"], "p_adjusted": m["p_adjusted"],
            "p_fisher": m["p_fisher"], "diff_ci95": m["diff_ci95"],
            "taught": m["skill"] in taught,
            "n_subjects_teaching": len(_subjects_teaching(cur, m["skill"])),
            "low_confidence": m["low_confidence_latest"],
        }
        material = m["latest_share"] >= GAP_MIN_SHARE_PCT
        if m["significant_adjusted"] and m["trend"] != "stable" and material:
            row["decision"] = "supported"
            row["reason"] = "change supported after %s correction" % CORRECTION_METHOD
            supported.append(row)
        elif material and m["trend"] != "stable":
            row["decision"] = "not supported at this precision"
            row["reason"] = ("observed prevalence %.0f%%; insufficient evidence of change "
                             "(adjusted p=%.3f)" % (m["latest_share"], m["p_adjusted"]))
            discarded.append(row)

    supported.sort(key=lambda r: -r["latest_share"])
    discarded.sort(key=lambda r: -r["latest_share"])

    featured = None
    unmapped = [r for r in supported if not r["taught"]]
    if unmapped:
        featured = unmapped[0]["skill"]
    elif supported:
        featured = supported[0]["skill"]

    return {
        "role": role,
        "latest_quarter": d["latest_quarter"],
        "latest_n": d["latest_n"],
        "observed_through": observation_cutoff(con),
        "correction": d.get("correction"),
        "criteria": {
            "min_latest_share_pct": GAP_MIN_SHARE_PCT,
            "trend_delta_pp": TREND_DELTA_PP,
            "alpha": ALPHA,
            "correction": CORRECTION_METHOD,
        },
        "featured_skill": featured,
        "n_supported": len(supported),
        "n_discarded": len(discarded),
        "supported": supported,
        "discarded": discarded,
        "excluded_from_time_series": d["excluded_from_time_series"],
    }


# ----------------------------------------------------------- collection yield

def collection_yield(con, measured_roles=None):
    """What survives each filter, per source.

    "More boards" is not automatically "more evidence". Forty further
    product-tech boards could enlarge the corpus while leaving the number of
    eligible, target-relevant, properly dated observations unchanged. The
    number worth optimising is the LAST column, not the first -- so report the
    funnel rather than the headline count.
    """
    if measured_roles is None:
        measured_roles = [r for r in roles(con) if r != "Other (unclassified)"]
    qs = ",".join("?" * len(measured_roles)) or "''"

    rows = []
    for r in con.execute("SELECT DISTINCT source FROM postings ORDER BY source"):
        src = r["source"]
        collected = con.execute(
            "SELECT COUNT(*) c FROM postings WHERE source = ?", (src,)).fetchone()["c"]
        unique = con.execute(
            "SELECT COUNT(DISTINCT id) c FROM postings WHERE source = ?", (src,)).fetchone()["c"]
        in_role = con.execute(
            "SELECT COUNT(*) c FROM postings WHERE source = ? AND role IN (%s)" % qs,
            [src] + measured_roles).fetchone()["c"]
        dated = con.execute(
            "SELECT COUNT(*) c FROM postings WHERE source = ? AND ts_eligible = 1",
            (src,)).fetchone()["c"]
        usable = con.execute(
            "SELECT COUNT(*) c FROM postings WHERE source = ? AND ts_eligible = 1 "
            "AND role IN (%s)" % qs, [src] + measured_roles).fetchone()["c"]
        rows.append({"source": src, "collected": collected, "unique": unique,
                     "in_measured_role": in_role, "date_eligible": dated,
                     "usable": usable,
                     "yield_pct": round(100.0 * usable / collected, 1) if collected else 0.0})

    real = [r for r in rows if r["source"] not in SYNTHETIC_SOURCES]
    tot = {k: sum(r[k] for r in real)
           for k in ("collected", "unique", "in_measured_role", "date_eligible", "usable")}
    tot["yield_pct"] = (round(100.0 * tot["usable"] / tot["collected"], 1)
                        if tot["collected"] else 0.0)
    return {
        "measured_roles": measured_roles,
        "stages": ["collected", "unique", "in_measured_role", "date_eligible", "usable"],
        "by_source": rows,
        "real_total": tot,
        "note": ("usable = in a measured role AND carrying a true creation date. "
                 "Adding boards raises 'collected'; only boards whose postings are "
                 "target-relevant and properly dated raise 'usable'."),
    }


# -------------------------------------------------- threshold sensitivity

# The grid reported by threshold_sensitivity(). Prespecifying these prevents
# picking the combination that produces the most findings after the fact.
PREVALENCE_GRID = [10.0, 15.0, 20.0]
CHANGE_GRID = [5.0, 10.0, 15.0]


def threshold_sensitivity(con, role, curriculum=None, drift_result=None):
    """Which recommendations survive across plausible decision thresholds.

    15% prevalence and +5pp change are OUR rules, not facts about the labour
    market. Prespecification stops opportunism but does not make a threshold
    substantively correct, so the honest move is to show what changes when the
    rule changes -- and specifically WHICH actions persist, not merely how many
    pass.

    Read the result narrowly. Passing every cell means robust ACROSS THE
    TESTED GRID -- the cells reuse the same observations and neighbouring
    thresholds are not independent confirmations, so a large planted change
    will naturally survive all of them. It rules out one specific way of being
    wrong (a threshold chosen to flatter the result). It is not validity.
    """
    cur = curriculum or load_curriculum()
    d = drift_result or drift(con, role)
    taught = set(cur["taught_skills"])

    cells, persistence = [], {}
    for pmin in PREVALENCE_GRID:
        for cmin in CHANGE_GRID:
            hits = [m["skill"] for m in d["skills"]
                    if m["latest_share"] >= pmin
                    and m["change_pp"] >= cmin
                    and m["significant_adjusted"]
                    and m["skill"] not in taught]
            cells.append({"min_share_pct": pmin, "min_change_pp": cmin,
                          "n": len(hits), "skills": sorted(hits)})
            for h in hits:
                persistence[h] = persistence.get(h, 0) + 1

    n_cells = len(cells)
    rows = [{"skill": k, "cells": v, "of": n_cells,
             "robust": v == n_cells,
             "latest_share": next((m["latest_share"] for m in d["skills"]
                                   if m["skill"] == k), None)}
            for k, v in persistence.items()]
    rows.sort(key=lambda r: (-r["cells"], -(r["latest_share"] or 0)))
    return {
        "role": role,
        "latest_quarter": d["latest_quarter"],
        "latest_n": d["latest_n"],
        "current_rule": {"min_share_pct": GAP_MIN_SHARE_PCT,
                         "min_change_pp": TREND_DELTA_PP},
        "grid": {"prevalence": PREVALENCE_GRID, "change": CHANGE_GRID},
        "n_cells": n_cells,
        "cells": cells,
        "persistence": rows,
        "n_robust": sum(1 for r in rows if r["robust"]),
        "interpretation": ("Robust across the tested grid only. The cells reuse the "
                           "same observations, so they are not independent "
                           "confirmations."),
    }


# ------------------------------------------------------ demand by location

# A city with fewer postings than this cannot support a per-city percentage.
# Same principle as LOW_CONFIDENCE_N, applied to the location axis.
LOCATION_MIN_N = LOW_CONFIDENCE_N


def demand_by_location(con, role=None, country="India", top_skills=6, min_n=1):
    """Which skills are demanded WHERE.

    The problem statement asks for demand by location and for district-level
    training plans; this is the first step toward both. Every city carries its
    posting count, and any city under LOCATION_MIN_N is flagged exactly the way
    a thin quarter is -- a 100% share over 2 postings is not a finding.
    """
    where, args = ["city != 'Unknown'"], []
    if role:
        where.append("role = ?")
        args.append(role)
    if country:
        where.append("country = ?")
        args.append(country)
    w = " AND ".join(where)

    cities = [dict(city=r["city"], state=r["state"], n=r["n"],
                   low_confidence=r["n"] < LOCATION_MIN_N)
              for r in con.execute(
                  "SELECT city, state, COUNT(*) AS n FROM postings WHERE %s "
                  "GROUP BY city, state HAVING n >= ? ORDER BY n DESC" % w,
                  args + [min_n])]

    for c in cities:
        sargs = list(args) + [c["city"]]
        c["skills"] = [
            {"skill": r["skill"], "count": r["c"], "n": c["n"],
             "share": round(100.0 * r["c"] / c["n"], 1)}
            for r in con.execute(
                "SELECT s.skill, COUNT(DISTINCT s.posting_id) AS c "
                "FROM posting_skills s JOIN postings p ON p.id = s.posting_id "
                "WHERE %s AND p.city = ? GROUP BY s.skill "
                "ORDER BY c DESC LIMIT %d"
                % (w.replace("city !=", "p.city !=").replace("role =", "p.role =")
                     .replace("country =", "p.country ="), top_skills),
                sargs)]

    return {
        "role": role,
        "country": country,
        "n_cities": len(cities),
        "n_postings": sum(c["n"] for c in cities),
        "min_n": LOCATION_MIN_N,
        "cities": cities,
        "maharashtra": [c for c in cities if c["state"] == "Maharashtra"],
    }


# ------------------------------------------------- obsolete / oversupplied

# A taught skill asked for in fewer than this share of the latest quarter's
# postings is a candidate for retirement or reduced capacity.
OBSOLETE_MAX_SHARE_PCT = 10.0


def obsolete_courses(con, role, curriculum=None, drift_result=None):
    """The gap table, reversed: what the curriculum teaches that demand does
    not want.

    The problem statement asks to "flag obsolete or oversupplied courses".
    This answers what an administrator should STOP funding, which is a
    different and harder decision than what to add.

    Two categories, both requiring the skill to be taught:
      obsolete    -- asked for in < OBSOLETE_MAX_SHARE_PCT of latest postings
      declining   -- trend is declining AND the move is statistically
                     significant, so it is a real fall rather than noise
    """
    cur = curriculum or load_curriculum()
    d = drift_result or drift(con, role)
    taught = set(cur["taught_skills"])
    measured = {s["skill"]: s for s in d["skills"]}
    observed_n = sum(q["n"] for q in d["quarters"])
    observed_quarters = [q["quarter"] for q in d["quarters"]]

    obsolete, declining, never_seen = [], [], []
    for skill in sorted(taught):
        m = measured.get(skill)
        if m is None:
            # Taught, and not one posting for this role mentioned it.
            # "Never seen" is a claim about the WHOLE observation window, so it
            # must carry that window's denominator. Reporting latest_n here
            # understated the evidence by roughly 8x.
            never_seen.append({"skill": skill,
                               "category": skills_mod.skill_category(skill),
                               "observed_count": 0,
                               "observed_n": observed_n,
                               "observed_quarters": observed_quarters,
                               "latest_n": d["latest_n"], "taught": True,
                               "subjects": _subjects_teaching(cur, skill)})
            continue
        row = {
            "skill": skill,
            "category": m["category"],
            "latest_share": m["latest_share"],
            "latest_count": m["latest_count"],
            "latest_n": m["latest_n"],
            "latest_ci95": m["latest_ci95"],
            "baseline_share": m["baseline_share"],
            "change_pp": m["change_pp"],
            "trend": m["trend"],
            "p_value": m["p_value"],
            "significant": m["significant"],
            "low_confidence": m["low_confidence_latest"],
            "taught": True,
            "subjects": _subjects_teaching(cur, skill),
        }
        if m["latest_share"] < OBSOLETE_MAX_SHARE_PCT:
            obsolete.append(row)
        elif m["trend"] == "declining" and m["significant"]:
            declining.append(row)

    obsolete.sort(key=lambda r: r["latest_share"])
    declining.sort(key=lambda r: r["change_pp"])
    return {
        "role": role,
        "latest_quarter": d["latest_quarter"],
        "latest_n": d["latest_n"],
        "low_confidence": d["latest_n"] < LOW_CONFIDENCE_N,
        "criteria": {"max_latest_share_pct": OBSOLETE_MAX_SHARE_PCT,
                     "alpha": ALPHA},
        "obsolete": obsolete,
        "declining": declining,
        "never_seen": never_seen,
        "observation_window": {
            "n": observed_n,
            "quarters": observed_quarters,
            "first": observed_quarters[0] if observed_quarters else None,
            "last": observed_quarters[-1] if observed_quarters else None,
        },
        "n_taught": len(taught),
    }


def _subjects_teaching(cur, skill):
    """Which syllabus subjects teach this skill -- so a recommendation names
    the course to revise, not just the skill."""
    return [{"code": s["code"], "name": s["name"], "semester": s.get("semester")}
            for s in cur["subjects"] if skill in s.get("skills", [])]


# --------------------------------------------------------- curriculum gap

def curriculum_gap(con, role, curriculum=None, drift_result=None):
    """Rising + materially demanded + not in the curriculum. The centrepiece."""
    cur = curriculum or load_curriculum()
    d = drift_result or drift(con, role)
    taught = set(cur["taught_skills"])

    gaps, covered = [], []
    for s in d["skills"]:
        row = {
            "skill": s["skill"],
            "category": s["category"],
            "latest_quarter": s["latest_quarter"],
            "latest_share": s["latest_share"],
            "latest_count": s["latest_count"],
            "latest_n": s["latest_n"],
            "latest_ci95": s["latest_ci95"],
            "baseline_share": s["baseline_share"],
            "baseline_count": s["baseline_count"],
            "baseline_n": s["baseline_n"],
            "change_pp": s["change_pp"],
            "trend": s["trend"],
            "p_value": s["p_value"],
            "significant": s["significant"],
            "p_adjusted": s["p_adjusted"],
            "significant_adjusted": s["significant_adjusted"],
            "p_fisher": s["p_fisher"],
            "diff_ci95": s["diff_ci95"],
            "correction_family_size": s["correction_family_size"],
            "first_seen": s["first_seen"],
            "taught": s["skill"] in taught,
            "low_confidence": s["low_confidence_latest"],
        }
        qualifies = (s["trend"] == "rising"
                     and s["latest_share"] >= GAP_MIN_SHARE_PCT
                     and s["skill"] not in taught)
        if qualifies:
            gaps.append(row)
        elif s["skill"] in taught and s["latest_share"] >= GAP_MIN_SHARE_PCT:
            covered.append(row)

    gaps.sort(key=lambda r: -r["latest_share"])
    covered.sort(key=lambda r: -r["latest_share"])

    demanded = {s["skill"] for s in d["skills"] if s["latest_share"] >= GAP_MIN_SHARE_PCT}
    return {
        "role": role,
        "latest_quarter": d["latest_quarter"],
        "latest_n": d["latest_n"],
        "low_confidence": d["latest_n"] < LOW_CONFIDENCE_N,
        "criteria": {
            "trend": "rising",
            "min_latest_share_pct": GAP_MIN_SHARE_PCT,
            "trend_delta_pp": TREND_DELTA_PP,
            "alpha": ALPHA,
            "not_in": cur["name"],
        },
        "gaps": gaps,
        "n_gaps": len(gaps),
        "n_gaps_significant": sum(1 for r in gaps if r["significant"]),
        "n_gaps_significant_adjusted": sum(1 for r in gaps if r["significant_adjusted"]),
        "correction": d.get("correction"),
        "covered": covered,
        "curriculum": {
            "name": cur["name"],
            "version": cur.get("version"),
            "source": cur.get("source"),
            "source_note": cur.get("source_note"),
            "n_subjects": cur["n_subjects"],
            "n_skills_taught": len(taught),
            "n_taught_and_demanded": len(taught & demanded),
            "taught_skills": cur["taught_skills"],
        },
    }


# --------------------------------------------------------------- overview

def overview(con):
    meta = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
    src = json.loads(meta.get("sources", "{}"))
    by_role = [{"role": r["role"], "n": r["n"]} for r in con.execute(
        "SELECT role, COUNT(*) AS n FROM postings GROUP BY role ORDER BY role")]
    return {
        "n_postings": int(meta.get("n_postings", 0)),
        "n_skill_mentions": int(meta.get("n_skill_mentions", 0)),
        "skill_dict_size": int(meta.get("skill_dict_size", 0)),
        "date_min": meta.get("date_min"),
        "date_max": meta.get("date_max"),
        "built_at": meta.get("built_at"),
        "sources": src,
        "source_files": json.loads(meta.get("source_files", "[]")),
        "provenance": provenance(src),
        "observed_through": observation_cutoff(con),
        "n_ts_excluded": int(meta.get("n_ts_excluded", 0)),
        "ts_excluded_by_source": json.loads(meta.get("ts_excluded_by_source", "{}")),
        "n_synthetic": split_counts(src)[0],
        "n_real": split_counts(src)[1],
        # Kept for backward compatibility with anything reading the old field.
        "all_synthetic": provenance(src) == "synthetic",
        "by_role": by_role,
        "thresholds": {
            "low_confidence_n": LOW_CONFIDENCE_N,
            "trend_delta_pp": TREND_DELTA_PP,
            "gap_min_share_pct": GAP_MIN_SHARE_PCT,
            "alpha": ALPHA,
        },
    }


if __name__ == "__main__":
    con = pipeline.connect()
    ov = overview(con)
    print("=" * 78)
    print("CORPUS: %d postings | %s .. %s | sources=%s"
          % (ov["n_postings"], ov["date_min"], ov["date_max"], ov["sources"]))
    if ov["all_synthetic"]:
        print("*** ALL RECORDS ARE SYNTHETIC SEED DATA -- NOT A REAL MARKET MEASUREMENT ***")
    cur = load_curriculum()
    print("CURRICULUM: %s (%d subjects, %d distinct skills, source=%s)"
          % (cur["name"], cur["n_subjects"], len(cur["taught_skills"]), cur["source"]))

    for role in roles(con):
        d = drift(con, role)
        print("=" * 78)
        print("ROLE: %s  (%d postings, latest quarter %s, n=%d)"
              % (role, d["n_postings"], d["latest_quarter"], d["latest_n"]))
        thin = [q["quarter"] for q in d["quarters"] if q["low_confidence"]]
        print("  quarters: %s" % ", ".join(
            "%s(n=%d)%s" % (q["quarter"], q["n"], "*" if q["low_confidence"] else "")
            for q in d["quarters"]))
        if thin:
            print("  * = n < %d, low confidence: %s" % (LOW_CONFIDENCE_N, ", ".join(thin)))

        print("  -- top 8 by latest share --")
        for s in top_skills(d, 8):
            print("     %-26s %5.1f%% (%d/%d)  base %5.1f%%  chg %+5.1fpp  %-9s p=%.3f%s"
                  % (s["skill"], s["latest_share"], s["latest_count"], s["latest_n"],
                     s["baseline_share"], s["change_pp"], s["trend"], s["p_value"],
                     "" if s["significant"] else "  (not significant)"))

        g = curriculum_gap(con, role, cur, d)
        print("  -- CURRICULUM GAP: rising, >=%.0f%% of %s postings, absent from syllabus --"
              % (GAP_MIN_SHARE_PCT, g["latest_quarter"]))
        print("     %d candidate gaps, of which %d survive a p<%.2f significance test"
              % (g["n_gaps"], g["n_gaps_significant"], ALPHA))
        if not g["gaps"]:
            print("     (none)")
        for r in g["gaps"]:
            print("     %-26s %5.1f%% (%d/%d)  95%% CI [%.1f, %.1f]  chg %+5.1fpp  p=%.3f  %s"
                  % (r["skill"], r["latest_share"], r["latest_count"], r["latest_n"],
                     r["latest_ci95"][0], r["latest_ci95"][1], r["change_pp"], r["p_value"],
                     "SIGNIFICANT" if r["significant"]
                     else "not significant - needs more data"))
    con.close()
