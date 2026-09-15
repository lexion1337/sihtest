"""
tools/score_classification.py -- turn classification verdicts into numbers.

Reads data/classification_verdicts.json and reports precision and recall for
the role classifier. Change any single verdict letter in that file and re-run
this; the numbers move accordingly. That is the point -- the judgement is data,
not something buried in a script.

"18 of 125" measures neither precision nor recall. This does.

Run:  python tools/score_classification.py
"""

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

VERDICTS = os.path.join(HERE, "data", "classification_verdicts.json")


def main():
    import pipeline

    doc = json.load(io.open(VERDICTS, encoding="utf-8"))
    unc = {r["title"]: r for r in doc["unclassified"]}
    asg = {r["title"]: r for r in doc["assigned"]}

    records = [r for r in pipeline.read_postings() if r["source"] != "synthetic"]
    unclassified = [r for r in records if r["role"] == "Other (unclassified)"]
    assigned = [r for r in records if r["role"] != "Other (unclassified)"]

    missing = ([r["title"] for r in unclassified if r["title"] not in unc]
               + [r["title"] for r in assigned if r["title"] not in asg])
    if missing:
        print("WARNING: %d postings have no verdict yet:" % len(missing))
        for t in sorted(set(missing))[:8]:
            print("   - %s" % t)
        print()

    # Count per POSTING, not per distinct title: duplicates are separate
    # vacancies and each one is a separate classification decision.
    def tally(rows, lookup):
        out = {}
        for r in rows:
            v = lookup.get(r["title"], {}).get("v", "?")
            out[v] = out.get(v, 0) + 1
        return out

    tu = tally(unclassified, unc)
    ta = tally(assigned, asg)

    print("=" * 74)
    print("ROLE CLASSIFIER -- precision and recall")
    print("=" * 74)
    print("  reviewed by : %s" % (doc.get("_reviewed_by") or
                                  "NOBODY YET (machine first pass)"))
    print()
    print("  Unclassified postings (%d)" % len(unclassified))
    print("     O  genuinely out of scope   %3d" % tu.get("O", 0))
    print("     M  MISSED, should be in     %3d" % tu.get("M", 0))
    print("     A  ambiguous                %3d" % tu.get("A", 0))
    print()
    print("  Assigned postings (%d)" % len(assigned))
    print("     C  correctly assigned       %3d" % ta.get("C", 0))
    print("     W  WRONGLY assigned         %3d" % ta.get("W", 0))
    print("     A  ambiguous                %3d" % ta.get("A", 0))
    print()

    c, w, a_asg = ta.get("C", 0), ta.get("W", 0), ta.get("A", 0)
    m, a_unc = tu.get("M", 0), tu.get("A", 0)

    print("=" * 74)
    print("CLEAR-CUT ONLY (ambiguous excluded)")
    print("=" * 74)
    prec = 100.0 * c / (c + w) if (c + w) else 0.0
    rec = 100.0 * c / (c + m) if (c + m) else 0.0
    print("  precision = C / (C + W)  = %d / %d  = %.1f%%" % (c, c + w, prec))
    print("  recall    = C / (C + M)  = %d / %d  = %.1f%%" % (c, c + m, rec))
    if prec + rec:
        print("  F1                               = %.1f%%"
              % (2 * prec * rec / (prec + rec)))

    print()
    print("=" * 74)
    print("WORST CASE (every ambiguous call goes against us)")
    print("=" * 74)
    prec_w = 100.0 * c / (c + w + a_asg) if (c + w + a_asg) else 0.0
    rec_w = 100.0 * c / (c + m + a_unc) if (c + m + a_unc) else 0.0
    print("  precision = %d / %d = %.1f%%" % (c, c + w + a_asg, prec_w))
    print("  recall    = %d / %d = %.1f%%" % (c, c + m + a_unc, rec_w))

    print()
    print("=" * 74)
    print("  Report the range, not the flattering end. On this first pass the")
    print("  classifier's precision is %.0f%%-%.0f%% and recall %.0f%%-%.0f%%."
          % (prec_w, prec, rec_w, rec))
    print("  These are FIRST-PASS numbers pending human confirmation, and the")
    print("  same author wrote both the classifier and these verdicts.")
    print("=" * 74)


if __name__ == "__main__":
    main()
