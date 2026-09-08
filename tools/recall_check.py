"""
tools/recall_check.py -- how does skills.py behave on text it did not generate?

WHAT THIS CAN AND CANNOT TELL YOU
---------------------------------
True recall needs ground truth: a human reading each posting and listing the
skills actually mentioned. This script does NOT invent that. What it produces:

  1. Extraction rates on real vs synthetic text, which are directly comparable
     because both run through the same extractor.
  2. CANDIDATE MISSES -- frequent capitalised/technical tokens in the real
     corpus that the dictionary does not match. These are leads, not proven
     misses; some will be company names or job-ad boilerplate.
  3. A review artifact: N real postings dumped as text alongside what was
     extracted, for a human to mark up. THAT is what yields a recall number.

Rule: do not tune SKILL_DEFS to make these numbers look better. A dictionary
fitted to the sample stops measuring the market and starts measuring itself.

Run:  python tools/recall_check.py [--n 30]
"""

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import pipeline
import skills as skills_mod

REVIEW_PATH = os.path.join(HERE, "data", "recall_review.md")

# Words that look like skills to a regex but are job-ad furniture.
STOP = set("""
the and for with you your our we us are is be to of in on at as by or from that
this it its will can may a an have has had who what when where why how all any
both each more most other some such no nor not only own same so than too very
just now then there here they them their he she his her him i me my mine
about across after against among around before behind below beneath beside
between beyond during except inside into near outside over since through
under until upon within without
job role team work working experience years year skills skill required
requirements responsibilities qualifications preferred plus strong good great
excellent ability able help build building develop developing design designing
support supporting manage managing lead leading drive driving own owning
ensure ensuring deliver delivering create creating maintain maintaining
company business customer customers client clients product products project
projects process processes solution solutions service services platform
partner partners stakeholder stakeholders opportunity opportunities
new best high low large small global india bengaluru bangalore mumbai pune
delhi hyderabad chennai remote hybrid office full time part senior junior
lead principal staff associate manager director head engineer engineering
developer analyst scientist specialist consultant intern internship
equal opportunity employer benefits salary compensation apply application
please note candidates candidate hiring recruiter interview offer
""".split())

TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9+#./\-]{1,24}\b")


def looks_technical(tok):
    """Cheap filter for things that might plausibly be a skill term."""
    if tok.lower() in STOP or len(tok) < 2:
        return False
    if tok.isupper() and len(tok) >= 2:          # SQL, AWS, ETL
        return True
    if any(c in tok for c in "+#./-"):           # C++, Node.js, CI/CD
        return True
    if tok[0].isupper() and any(c.islower() for c in tok[1:]):   # Kubernetes
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="postings in the review artifact")
    args = ap.parse_args()

    records = pipeline.read_postings()
    real = [r for r in records if r["source"] != "synthetic"]
    synth = [r for r in records if r["source"] == "synthetic"]
    if not real:
        raise SystemExit("no real postings found -- run: python ingest_ats.py")

    print("=" * 78)
    print("EXTRACTION ON REAL TEXT vs SYNTHETIC TEXT")
    print("=" * 78)

    rows = []
    for label, corpus in (("synthetic", synth), ("real", real)):
        hits, zero, lens = [], 0, []
        for r in corpus:
            found = skills_mod.extract_skills(r["description_text"])
            hits.append(len(found))
            lens.append(len(r["description_text"]))
            if not found:
                zero += 1
        hits.sort()
        rows.append((label, len(corpus), sum(hits) / len(hits),
                     hits[len(hits) // 2], zero,
                     sum(lens) / len(lens)))
    print("  %-10s %7s %10s %9s %14s %12s"
          % ("corpus", "n", "mean/post", "median", "zero-skill", "mean chars"))
    for label, n, mean, med, zero, ch in rows:
        print("  %-10s %7d %10.1f %9d %8d (%4.1f%%) %11.0f"
              % (label, n, mean, med, zero, 100.0 * zero / n, ch))

    print()
    print("  Same extractor, both corpora. The synthetic figure is ~100% by")
    print("  construction (generator and extractor share skills.py), so treat")
    print("  it as a ceiling artefact, not a benchmark.")

    # ---------------------------------------------------------- per source
    print()
    print("=" * 78)
    print("BY SOURCE")
    print("=" * 78)
    by_src = collections.defaultdict(list)
    for r in real:
        by_src[r["source"]].append(len(skills_mod.extract_skills(r["description_text"])))
    for src, hits in sorted(by_src.items()):
        hits.sort()
        print("  %-12s n=%-4d mean=%.1f median=%d zero=%d"
              % (src, len(hits), sum(hits) / len(hits), hits[len(hits) // 2],
                 sum(1 for h in hits if h == 0)))

    # ------------------------------------------------------ candidate misses
    print()
    print("=" * 78)
    print("CANDIDATE MISSES -- frequent technical-looking tokens we do NOT match")
    print("=" * 78)
    known = set()
    for canonical in skills_mod.all_skills():
        known.add(canonical.lower())
        for a in skills_mod.aliases_for(canonical):
            known.add(a.lower())

    df = collections.Counter()
    for r in real:
        seen = set()
        for tok in TOKEN.findall(r["description_text"]):
            if not looks_technical(tok):
                continue
            t = tok.lower().rstrip(".,;:")
            if t in known or t in STOP:
                continue
            seen.add(t)
        df.update(seen)

    print("  (document frequency across %d real postings; leads, not proven misses)" % len(real))
    for tok, n in df.most_common(40):
        print("     %-26s in %3d postings (%4.1f%%)" % (tok, n, 100.0 * n / len(real)))

    # ------------------------------------------------------ review artifact
    real_sorted = sorted(real, key=lambda r: -len(r["description_text"]))
    step = max(1, len(real_sorted) // args.n)
    sample = real_sorted[::step][:args.n]

    with open(REVIEW_PATH, "w", encoding="utf-8") as fh:
        fh.write("# Extraction recall review\n\n")
        fh.write("%d real postings, sampled across the corpus by description length.\n\n"
                 % len(sample))
        fh.write("**How to use this.** For each posting, read the text and list any skill "
                 "the extractor SHOULD have found but did not, under `MISSED:`. Also mark "
                 "anything in `EXTRACTED` that is not really being asked for, under "
                 "`FALSE POSITIVE:`. Recall = correct / (correct + missed).\n\n")
        fh.write("Do not edit skills.py to make this look better. Mark it first, "
                 "then decide deliberately what to change.\n\n---\n\n")
        for i, r in enumerate(sample, 1):
            found = skills_mod.extract_skills(r["description_text"])
            fh.write("## %d. %s\n\n" % (i, r["title"]))
            fh.write("- **company** %s · **location** %s · **posted** %s\n"
                     % (r["company"], r["location"], r["posted_date"]))
            fh.write("- **source** %s · **id** `%s`\n" % (r["source"], r["id"]))
            if r.get("url"):
                fh.write("- **url** %s\n" % r["url"])
            fh.write("- **role assigned** %s\n\n" % r["role"])
            fh.write("**EXTRACTED (%d):** %s\n\n" % (len(found), ", ".join(found) or "_none_"))
            fh.write("MISSED:\n\nFALSE POSITIVE:\n\n")
            fh.write("<details><summary>description text (%d chars)</summary>\n\n```\n%s\n```\n</details>\n\n---\n\n"
                     % (len(r["description_text"]), r["description_text"][:6000]))

    print()
    print("=" * 78)
    print("wrote review artifact: %s" % REVIEW_PATH)
    print("  %d postings, each with its text and what was extracted." % len(sample))
    print("  Mark MISSED / FALSE POSITIVE by hand -- that is what yields recall.")
    print("=" * 78)


if __name__ == "__main__":
    main()
