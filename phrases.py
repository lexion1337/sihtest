"""
phrases.py -- open-vocabulary candidate discovery.

WHY THIS EXISTS
---------------
skills.py matches a CLOSED dictionary of curated terms. A competency not in
that dictionary is UNMEASURED, and its prevalence is zero by construction --
not low, zero. That is a structural problem for any claim about *emerging*
skills: a detector that can only report terms someone already listed detects
the diffusion of known things, not emergence.

This module is the discovery half. It finds 1-4 word phrases in the
requirement-like sentences of real postings that are absent from the
dictionary, and ranks them for a human to adjudicate.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
  * It does not add anything to the dictionary. Discovery and confirmation are
    separate steps on purpose. A human decides whether a phrase is a
    competency, a task, a product name, an alias, a benefit or noise; approved
    terms then enter a VERSIONED dictionary and history is re-extracted with
    that same version. Skipping that turns every dictionary update into
    manufactured "emergence".
  * It does not claim these phrases are RISING. With five time-series-eligible
    real postings there is no series to measure a rise against. What can be
    demonstrated today is unknown-term discovery, not unknown-term growth.
  * It counts a phrase ONCE PER POSTING. Ten copied advertisements from one
    employer are one concentrated lead, not ten independent confirmations, so
    distinct-employer support is reported beside document frequency and is the
    column that should actually be trusted.

Run:  python phrases.py
"""

import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import skills as skills_mod

# Sentences that plausibly state a requirement rather than describe the
# company. Restricting discovery to these removes a lot of marketing prose
# before ranking rather than after.
REQUIREMENT_CUE = re.compile(
    r"(experience|proficien|knowledge of|familiar|hands[- ]on|expertise|"
    r"skills?|must have|required|requirement|working with|ability to|"
    r"exposure to|background in|comfortable with|strong|proven|degree in|"
    r"responsib|you will|develop|build|design|manage|own)", re.I)

STOP = set("""
a an the and or but if then than that this these those of in on at to for with
from by as is are was were be been being have has had do does did will would
can could should may might must shall not no nor so such very too more most
other others some any each both all we you they it he she our your their its
who whom whose what which when where why how here there
work working works job role team teams company companies business businesses
years year experience experiences skill skills required requirements
responsibilities responsible qualifications preferred plus strong good great
excellent ability able help build building develop developing design designing
support supporting manage managing lead leading drive driving own owning
ensure ensuring deliver delivering create creating maintain maintaining
customer customers client clients product products project projects process
processes solution solutions service services platform platforms partner
partners stakeholder stakeholders opportunity opportunities new best high low
large small global india office remote hybrid full time part senior junior
principal staff associate manager director head engineer engineering developer
analyst scientist specialist consultant intern internship equal opportunity
employer benefits salary compensation apply application please note candidate
candidates hiring recruiter interview offer join joining looking seeking
across within including etc via using use used well also may our us
while through closely into them like one someone people goals define serve
entire relevant requires translate making scale scalable ecosystem strategy
strategic growth roadmap engagement passionate relationships partnerships
ll ve re don doesn isn aren won cant cannot let lets make makes made take
takes taken get gets got give gives given go goes going come comes came
know knows known think thinks see sees seen want wants need needs
world class leading fast paced growing mission driven impact culture values
diverse inclusive belonging wellbeing flexible competitive package equity
stock bonus insurance leave policy holidays perks snacks
every day days week weeks month months quarter quarters year annual
first second third next last previous current future past present
many much several few lot lots bit around about over under between
really quite pretty highly deeply truly simply just only even still
anyone everyone nobody something anything everything nothing
account development management operations security finance marketing sales
success science data team user users member members
""".split())

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./&-]{0,28}")
MIN_LEN = 2
MAX_NGRAM = 4

ACRONYM = re.compile(r"^[A-Z]{2,}[A-Z0-9+#/]*$")              # SQL, CI/CD, GCP, AI
CAMEL = re.compile(r"^[A-Z][a-z0-9]+[A-Z]")                   # DevOps, GraphQL
INTERNAL_PUNCT = re.compile(r"[A-Za-z0-9][+#./][A-Za-z0-9]")  # node.js, ci/cd
CAPWORD = re.compile(r"^[A-Z][a-z0-9]")
TRAILING = re.compile(r"[.,;:!?)\]]+$")


def _known_surface_forms():
    """Every canonical name and alias already in the dictionary, lowercased."""
    known = set()
    for canonical in skills_mod.all_skills():
        known.add(canonical.lower())
        for a in skills_mod.aliases_for(canonical):
            known.add(str(a).lower())
    return known


def _clean(tok):
    """Strip sentence punctuation.

    A trailing full stop is not a dot in a package name. Treating it as one is
    how "execution." and "managers." reached the top of an earlier ranking.
    """
    return TRAILING.sub("", tok).strip()


def _is_technical(tok, position, ngram_len):
    """Does this token look like a technology or competency term?

    For a SINGLE-word candidate the bar is high: an all-caps acronym, internal
    CamelCase, or internal technical punctuation. Plain capitalisation is not
    enough, because job adverts are full of title-case headings -- which is how
    "Account", "Development" and "Security" scored well before this rule.

    Inside a MULTI-word phrase plain capitalisation is allowed, because the
    neighbouring words supply context.
    """
    if len(tok) < 2:
        return False
    if ACRONYM.match(tok) or CAMEL.match(tok) or INTERNAL_PUNCT.search(tok):
        return True
    if ngram_len > 1 and position > 0 and CAPWORD.match(tok):
        return True
    return False


def _candidate_phrases(text):
    """1..MAX_NGRAM phrases from requirement-like sentences.

    Kept only if the phrase CONTAINS a technical-looking token. Without that
    constraint the ranking fills with ordinary English, because common words
    are common.
    """
    out = set()
    for raw in re.split(r"(?<=[.!?])\s+|\n+|(?<=[;:])\s+", text or ""):
        sent = raw.strip()
        if len(sent) < 12 or not REQUIREMENT_CUE.search(sent):
            continue
        toks = [t for t in (_clean(x) for x in TOKEN.findall(sent)) if t]
        if not toks:
            continue
        low = [t.lower() for t in toks]
        for i in range(len(toks)):
            for n in range(1, MAX_NGRAM + 1):
                if i + n > len(toks):
                    break
                grams_l = low[i:i + n]
                if grams_l[0] in STOP or grams_l[-1] in STOP:
                    continue
                if all(g in STOP for g in grams_l):
                    continue
                if not any(_is_technical(toks[i + j], i + j, n) for j in range(n)):
                    continue
                phrase = " ".join(grams_l)
                if len(phrase) < MIN_LEN or phrase.isdigit():
                    continue
                out.add((phrase, " ".join(toks[i:i + n]), sent[:400]))
    return out


def discover(records, min_postings=3, min_employers=2, limit=60, real_only=True):
    """Rank dictionary-absent phrases as candidates for human adjudication."""
    known = _known_surface_forms()
    corpus = [r for r in records
              if (not real_only) or r.get("source") != "synthetic"]

    df = collections.Counter()
    employers = collections.defaultdict(set)
    months = collections.defaultdict(set)
    surface, example = {}, {}

    for rec in corpus:
        seen = set()
        for phrase, shown, sent in _candidate_phrases(rec.get("description_text", "")):
            if phrase in known or phrase in seen:
                continue
            seen.add(phrase)            # once per posting, never per mention
            df[phrase] += 1
            employers[phrase].add(rec.get("company", "?"))
            m = str(rec.get("posted_date", ""))[:7]
            if m:
                months[phrase].add(m)
            surface.setdefault(phrase, shown)
            example.setdefault(phrase, sent)

    rows = []
    for phrase, n in df.items():
        if n < min_postings:
            continue
        emp = len(employers[phrase])
        if emp < min_employers:
            continue
        rows.append({
            "phrase": surface.get(phrase, phrase),
            "key": phrase,
            "postings": n,
            "employers": emp,
            "months_seen": len(months[phrase]),
            "single_employer": emp == 1,
            "example": example.get(phrase, ""),
        })

    # Distinct-employer support first: it is the column that survives
    # boilerplate. Document frequency only breaks ties.
    rows.sort(key=lambda r: (-r["employers"], -r["postings"]))
    return {
        "n_postings_scanned": len(corpus),
        "real_only": real_only,
        "min_postings": min_postings,
        "min_employers": min_employers,
        "dictionary_size": skills_mod.skill_count(),
        "n_candidates": len(rows),
        "candidates": rows[:limit],
        "note": ("Discovery only. These are NOT in the dictionary, are NOT counted "
                 "anywhere else on this site, and are NOT claimed to be rising -- "
                 "with the current corpus there is no series to measure a rise "
                 "against. Each needs a human to decide whether it is a competency, "
                 "a task, a product name, an alias, a benefit or noise."),
    }


if __name__ == "__main__":
    import pipeline
    res = discover(pipeline.read_postings())
    print("scanned %d real postings against a %d-term dictionary"
          % (res["n_postings_scanned"], res["dictionary_size"]))
    print("%d candidates in >= %d postings from >= %d employers\n"
          % (res["n_candidates"], res["min_postings"], res["min_employers"]))
    print("%-36s %9s %10s" % ("PHRASE", "POSTINGS", "EMPLOYERS"))
    for r in res["candidates"][:28]:
        print("%-36s %9d %10d" % (r["phrase"][:36], r["postings"], r["employers"]))
