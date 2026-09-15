"""
tools/score_extraction.py -- turn extraction verdicts into a recall number.

Reads data/extraction_verdicts.json. Change any verdict and re-run.

This is the number the project has never had. Until now the honest answer to
"how do you know extraction works on real text?" was a proxy: 5.4 skills per
posting on real text versus 11.8 on synthetic. A proxy is not recall.

Run:  python tools/score_extraction.py
"""

import io
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERDICTS = os.path.join(HERE, "data", "extraction_verdicts.json")


def main():
    doc = json.load(io.open(VERDICTS, encoding="utf-8"))
    rows = doc["postings"]

    extracted = sum(len(r["extracted"]) for r in rows)
    missed = sum(len(r["missed"]) for r in rows)
    fp = sum(len(r["false_positive"]) for r in rows)
    unc = sum(len(r["uncertain_fp"]) for r in rows)

    print("=" * 74)
    print("EXTRACTION QUALITY on real text -- %d postings audited" % len(rows))
    print("=" * 74)
    print("  reviewed by : %s" % (doc.get("_reviewed_by") or
                                  "NOBODY YET (machine first pass)"))
    print()
    print("  terms extracted            %3d" % extracted)
    print("  terms MISSED               %3d" % missed)
    print("  confirmed false positives  %3d" % fp)
    print("  uncertain (boilerplate?)   %3d" % unc)
    print()

    # Best case: every uncertain match really was a requirement.
    correct_best = extracted - fp
    rec_best = 100.0 * correct_best / (correct_best + missed) if (correct_best + missed) else 0.0
    prec_best = 100.0 * correct_best / extracted if extracted else 0.0

    # Worst case: every uncertain match was boilerplate, not a requirement.
    correct_worst = extracted - fp - unc
    rec_worst = 100.0 * correct_worst / (correct_worst + missed) if (correct_worst + missed) else 0.0
    prec_worst = 100.0 * correct_worst / extracted if extracted else 0.0

    print("=" * 74)
    print("RECALL  = correct / (correct + missed)")
    print("=" * 74)
    print("  best case  (uncertain matches counted as real) : %.1f%%  (%d of %d)"
          % (rec_best, correct_best, correct_best + missed))
    print("  worst case (uncertain matches counted as noise): %.1f%%  (%d of %d)"
          % (rec_worst, correct_worst, correct_worst + missed))
    print()
    print("PRECISION = correct / extracted")
    print("  best case  : %.1f%%" % prec_best)
    print("  worst case : %.1f%%" % prec_worst)

    print()
    print("=" * 74)
    print("PER POSTING")
    print("=" * 74)
    for r in rows:
        print("  %-52s ext %2d  missed %2d  unc %d"
              % (r["title"][:52], len(r["extracted"]), len(r["missed"]),
                 len(r["uncertain_fp"])))

    print()
    print("=" * 74)
    print("WHAT WAS MISSED, and why it matters")
    print("=" * 74)
    seen = set()
    for r in rows:
        for m in r["missed"]:
            if m["term"] in seen:
                continue
            seen.add(m["term"])
            print("  %-18s %s" % (m["term"], m["why"][:90]))

    print()
    print("=" * 74)
    for p in doc.get("_patterns", []):
        print("  * %s" % p)
    print()
    print("  CAVEAT: the same author wrote skills.py and these verdicts, and")
    print("  shares its blind spots. Terms the dictionary never contained are")
    print("  exactly the ones its author is least likely to notice missing.")
    print("  Treat the missed list as a LOWER BOUND. %d postings is a small"
          % len(rows))
    print("  sample; widen it before quoting a single headline figure.")
    print("=" * 74)


if __name__ == "__main__":
    main()
