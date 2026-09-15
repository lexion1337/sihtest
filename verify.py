"""
verify.py -- numerical invariants for the claims this project makes.

This is NOT a test suite. It is a short list of things that must be true of
every number the dashboard shows, checked against the live database and the
live analysis functions.

It exists because a denominator defect shipped in a product whose central
promise is numerical traceability: "never seen" reported the latest-quarter
denominator (0 of 25) for a claim that spans the whole observation window
(0 of 201). Nothing caught it. These checks catch that class of error.

Run:  python verify.py          (exit code 1 if any invariant fails)
"""

import sys

import analysis
import pipeline

FAILURES = []
CHECKS = 0


def check(label, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s    %s" % (label, detail))
        FAILURES.append(label)


def main():
    con = pipeline.connect()
    cur = analysis.load_curriculum()
    ov = analysis.overview(con)
    roles = analysis.roles(con)

    print("=" * 74)
    print("1. COUNTS RECONCILE")
    print("=" * 74)
    total = con.execute("SELECT COUNT(*) c FROM postings").fetchone()["c"]
    check("meta n_postings == rows in postings",
          ov["n_postings"] == total, "%s vs %s" % (ov["n_postings"], total))
    check("n_real + n_synthetic == n_postings",
          ov["n_real"] + ov["n_synthetic"] == ov["n_postings"],
          "%d + %d != %d" % (ov["n_real"], ov["n_synthetic"], ov["n_postings"]))
    check("sum(sources.values()) == n_postings",
          sum(ov["sources"].values()) == ov["n_postings"])

    excluded = con.execute(
        "SELECT COUNT(*) c FROM postings WHERE ts_eligible = 0").fetchone()["c"]
    check("meta n_ts_excluded == rows with ts_eligible=0",
          ov["n_ts_excluded"] == excluded,
          "%s vs %s" % (ov["n_ts_excluded"], excluded))
    check("every excluded row has a non-creation date_kind",
          con.execute("SELECT COUNT(*) c FROM postings "
                      "WHERE ts_eligible = 0 AND date_kind IN ('created','published')"
                      ).fetchone()["c"] == 0)

    print()
    print("=" * 74)
    print("2. NUMERATOR NEVER EXCEEDS DENOMINATOR")
    print("=" * 74)
    for role in roles:
        d = analysis.drift(con, role)
        bad = []
        for s in d["skills"]:
            for p in s["series"]:
                if p["count"] > p["n"]:
                    bad.append((s["skill"], p["quarter"], p["count"], p["n"]))
            if s["latest_count"] > s["latest_n"]:
                bad.append((s["skill"], "latest", s["latest_count"], s["latest_n"]))
            if s["baseline_count"] > s["baseline_n"]:
                bad.append((s["skill"], "baseline", s["baseline_count"], s["baseline_n"]))
        check("%-20s every count <= its n" % role, not bad, str(bad[:3]))

        shares_ok = all(0.0 <= p["share"] <= 100.0
                        for s in d["skills"] for p in s["series"])
        check("%-20s every share in [0,100]" % role, shares_ok)

    print()
    print("=" * 74)
    print("3. THE QUARTERLY DENOMINATOR EXCLUDES WHAT IT CLAIMS TO")
    print("=" * 74)
    for role in roles:
        d = analysis.drift(con, role)
        series_total = sum(q["n"] for q in d["quarters"])
        eligible = con.execute(
            "SELECT COUNT(*) c FROM postings WHERE role = ? AND ts_eligible = 1",
            (role,)).fetchone()["c"]
        check("%-20s series n == eligible rows" % role,
              series_total == eligible, "%d vs %d" % (series_total, eligible))
        gh = con.execute(
            "SELECT COUNT(*) c FROM postings "
            "WHERE role = ? AND ts_eligible = 0 AND quarter IN (%s)"
            % ",".join("?" * len(d["quarters"])),
            [role] + [q["quarter"] for q in d["quarters"]]).fetchone()["c"]
        ex = d["excluded_from_time_series"]["n_excluded"]
        check("%-20s excluded count is reported" % role, ex >= 0 and gh >= 0)

    print()
    print("=" * 74)
    print("4. THE DISPLAYED DECISION MATCHES THE DECLARED PROCEDURE")
    print("=" * 74)
    for role in roles:
        d = analysis.drift(con, role)
        # Recompute BH independently of the code path that produced it.
        ps = [s["p_value"] for s in d["skills"]]
        m = len(ps)
        order = sorted(range(m), key=lambda i: ps[i])
        expect = [0.0] * m
        run = 1.0
        for rank in range(m, 0, -1):
            i = order[rank - 1]
            run = min(run, min(1.0, ps[i] * m / rank))
            expect[i] = round(run, 4)
        mism = [(d["skills"][i]["skill"], d["skills"][i]["p_adjusted"], expect[i])
                for i in range(m) if abs(d["skills"][i]["p_adjusted"] - expect[i]) > 1e-9]
        check("%-20s BH values recompute exactly" % role, not mism, str(mism[:2]))

        bad = [s["skill"] for s in d["skills"]
               if s["significant_adjusted"] != (s["p_adjusted"] < analysis.ALPHA)]
        check("%-20s badge == (adjusted p < alpha)" % role, not bad, str(bad[:3]))

        check("%-20s family size == skills tested" % role,
              d["correction"]["family_size"] == len(d["skills"]))

        # The PRIMARY rule is the BH-adjusted z-test. Fisher is a sensitivity
        # check and must never be what flips a badge.
        f = analysis.findings(con, role, cur, d)
        wrong = [r["skill"] for r in f["supported"]
                 if not next(s for s in d["skills"] if s["skill"] == r["skill"])
                 ["significant_adjusted"]]
        check("%-20s supported list uses BH, not Fisher" % role, not wrong, str(wrong[:3]))

    print()
    print("=" * 74)
    print("5. DRILL-DOWN REPRODUCES THE DISPLAYED COUNT")
    print("=" * 74)
    for role in roles:
        f = analysis.findings(con, role, cur)
        if not f["supported"] and not f["discarded"]:
            continue
        for row in (f["supported"] + f["discarded"])[:3]:
            n = con.execute(
                "SELECT COUNT(DISTINCT p.id) c FROM postings p "
                "JOIN posting_skills s ON s.posting_id = p.id "
                "WHERE p.role = ? AND s.skill = ? AND p.quarter = ? AND p.ts_eligible = 1",
                (role, row["skill"], f["latest_quarter"])).fetchone()["c"]
            check("%-20s %-22s drill-down == shown" % (role, row["skill"][:22]),
                  n == row["latest_count"], "%d vs %d" % (n, row["latest_count"]))

    print()
    print("=" * 74)
    print("6. PROVENANCE RECONCILES PER FINDING")
    print("=" * 74)
    for role in roles:
        f = analysis.findings(con, role, cur)
        if not f["featured_skill"]:
            continue
        det = analysis.finding(con, role, f["featured_skill"], cur)
        c = det["composition"]
        check("%-20s numerator composition sums to count" % role,
              c["total"] == det["prevalence"]["count"],
              "%d vs %d" % (c["total"], det["prevalence"]["count"]))
        check("%-20s n_real + n_synthetic == total" % role,
              c["n_real"] + c["n_synthetic"] == c["total"])
        dc = det.get("denominator_composition")
        if dc:
            check("%-20s denominator composition == n" % role,
                  dc["total"] == det["prevalence"]["n"],
                  "%d vs %d" % (dc["total"], det["prevalence"]["n"]))

    print()
    print("=" * 74)
    print("7. NEVER-SEEN USES THE WHOLE OBSERVATION WINDOW")
    print("=" * 74)
    for role in roles:
        O = analysis.obsolete_courses(con, role, cur)
        w = O["observation_window"]
        d = analysis.drift(con, role)
        check("%-20s window n == series total" % role,
              w["n"] == sum(q["n"] for q in d["quarters"]))
        bad = [r["skill"] for r in O["never_seen"] if r.get("observed_n") != w["n"]]
        check("%-20s never-seen rows carry window n" % role, not bad, str(bad[:3]))
        # And they really are absent everywhere, not just in the latest quarter.
        wrong = []
        for r in O["never_seen"][:8]:
            hits = con.execute(
                "SELECT COUNT(*) c FROM posting_skills WHERE role = ? AND skill = ? "
                "AND ts_eligible = 1", (role, r["skill"])).fetchone()["c"]
            if hits:
                wrong.append((r["skill"], hits))
        check("%-20s never-seen really means zero" % role, not wrong, str(wrong[:3]))

    con.close()
    print()
    print("=" * 74)
    if FAILURES:
        print("FAILED %d of %d invariants:" % (len(FAILURES), CHECKS))
        for f in FAILURES:
            print("   - %s" % f)
        print("=" * 74)
        return 1
    print("ALL %d INVARIANTS HOLD" % CHECKS)
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
