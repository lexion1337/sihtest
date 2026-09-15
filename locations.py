"""
locations.py -- normalise the free-text location strings that job boards emit.

The problem statement asks for demand by LOCATION and for district-level
training plans. Both ATS APIs return location, and until now we discarded it.

The raw strings are a mess. In the real corpus alone, one city appears as
"Bangalore, Karnataka", "bengaluru" and "Bengaluru, Karnataka, India" -- three
spellings that must collapse to one bucket or every per-city percentage is
wrong. This module does that collapse, and nothing else.

Deliberately a hand-written dictionary rather than a geocoding service:
  * it must run offline and instantly, like the rest of the pipeline
  * a wrong city silently mislabels a row; a dictionary is auditable, a
    fuzzy matcher is not
  * anything we do not recognise becomes "Unknown" rather than a guess, and
    the UI shows how many rows that is

Public API:
    normalise(raw) -> {"city", "state", "country", "is_maharashtra", "raw"}
"""

import re

# canonical city -> (state, country, aliases...)
# States matter because the customer is the Government of Maharashtra.
CITIES = [
    # ---- Maharashtra (the customer's own state) ----
    ("Mumbai",      "Maharashtra", "India", ("mumbai", "bombay", "navi mumbai", "thane")),
    ("Pune",        "Maharashtra", "India", ("pune", "pimpri", "chinchwad")),
    ("Nagpur",      "Maharashtra", "India", ("nagpur",)),
    ("Nashik",      "Maharashtra", "India", ("nashik", "nasik")),
    ("Aurangabad",  "Maharashtra", "India", ("aurangabad", "chhatrapati sambhajinagar")),

    # ---- rest of India ----
    ("Bengaluru",   "Karnataka",      "India", ("bengaluru", "bangalore", "bangaluru")),
    ("Hyderabad",   "Telangana",      "India", ("hyderabad", "secunderabad")),
    ("Chennai",     "Tamil Nadu",     "India", ("chennai", "madras")),
    ("Coimbatore",  "Tamil Nadu",     "India", ("coimbatore",)),
    ("Gurugram",    "Haryana",        "India", ("gurugram", "gurgaon")),
    ("Noida",       "Uttar Pradesh",  "India", ("noida", "greater noida")),
    ("New Delhi",   "Delhi",          "India", ("new delhi", "delhi", "delhi ncr", "ncr")),
    ("Kolkata",     "West Bengal",    "India", ("kolkata", "calcutta")),
    ("Ahmedabad",   "Gujarat",        "India", ("ahmedabad", "amdavad")),
    ("Surat",       "Gujarat",        "India", ("surat",)),
    ("Indore",      "Madhya Pradesh", "India", ("indore",)),
    ("Jaipur",      "Rajasthan",      "India", ("jaipur",)),
    ("Kochi",       "Kerala",         "India", ("kochi", "cochin", "ernakulam")),
    ("Bhubaneswar", "Odisha",         "India", ("bhubaneswar",)),
    ("Chandigarh",  "Chandigarh",     "India", ("chandigarh", "mohali")),
    ("Trivandrum",  "Kerala",         "India", ("trivandrum", "thiruvananthapuram")),

    # ---- outside India: kept separate so they never pollute an India claim ----
    ("San Francisco", "California",   "United States", ("san francisco", "bay area", "berkeley", "oakland")),
    ("Austin",        "Texas",        "United States", ("austin",)),
    ("Boston",        "Massachusetts","United States", ("boston", "cambridge, ma")),
    ("New York",      "New York",     "United States", ("new york", "nyc", "brooklyn")),
    ("Seattle",       "Washington",   "United States", ("seattle",)),
    ("London",        "England",      "United Kingdom", ("london",)),
    ("Calgary",       "Alberta",      "Canada",        ("calgary",)),
    ("Toronto",       "Ontario",      "Canada",        ("toronto",)),
    ("Tokyo",         "Tokyo",        "Japan",         ("tokyo",)),
    ("Singapore",     "Singapore",    "Singapore",     ("singapore",)),
    ("Sydney",        "New South Wales", "Australia",  ("sydney",)),
    ("Dublin",        "Leinster",     "Ireland",       ("dublin",)),
    ("Berlin",        "Berlin",       "Germany",       ("berlin",)),
]

# State-only strings ("tamil nadu") with no city we can pin down.
STATE_ONLY = {
    "maharashtra": ("Maharashtra", "India"),
    "karnataka": ("Karnataka", "India"),
    "tamil nadu": ("Tamil Nadu", "India"),
    "telangana": ("Telangana", "India"),
    "kerala": ("Kerala", "India"),
    "gujarat": ("Gujarat", "India"),
    "rajasthan": ("Rajasthan", "India"),
    "west bengal": ("West Bengal", "India"),
    "haryana": ("Haryana", "India"),
    "uttar pradesh": ("Uttar Pradesh", "India"),
    "madhya pradesh": ("Madhya Pradesh", "India"),
    "odisha": ("Odisha", "India"),
    "punjab": ("Punjab", "India"),
    "india": (None, "India"),
}

UNKNOWN = {"city": "Unknown", "state": None, "country": None,
           "is_maharashtra": False}

# Longest alias first so "navi mumbai" is tried before "mumbai".
_ALIAS_INDEX = []
for city, state, country, aliases in CITIES:
    for a in aliases:
        _ALIAS_INDEX.append((a, city, state, country))
_ALIAS_INDEX.sort(key=lambda t: -len(t[0]))

_REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)


def normalise(raw):
    """Map a free-text location to a canonical bucket.

    Returns a dict with city, state, country, is_maharashtra and the raw
    string. Unrecognised input becomes city "Unknown" -- never a guess.
    """
    out = dict(UNKNOWN)
    out["raw"] = raw
    if not raw:
        return out

    text = " " + re.sub(r"[/|;]", ",", str(raw)).lower().strip() + " "
    remote = bool(_REMOTE.search(text))

    # A named city wins over a "remote" marker: "Remote - Bengaluru" is a
    # Bengaluru row for demand purposes.
    for alias, city, state, country in _ALIAS_INDEX:
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", text):
            out.update(city=city, state=state, country=country,
                       is_maharashtra=(state == "Maharashtra"))
            return out

    for alias, (state, country) in STATE_ONLY.items():
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", text):
            out.update(city=("%s (state only)" % state) if state else "India (unspecified)",
                       state=state, country=country,
                       is_maharashtra=(state == "Maharashtra"))
            return out

    if remote:
        out.update(city="Remote (unspecified)", state=None, country=None)
        return out

    return out


def city_of(raw):
    return normalise(raw)["city"]


if __name__ == "__main__":
    samples = [
        "Bangalore, Karnataka", "bengaluru", "Bengaluru, Karnataka, India",
        "bengaluru, mumbai", "Pune, Maharashtra", "Navi Mumbai, Maharashtra",
        "tamil nadu", "Surat, Gujarat", "Remote - India", "Hybrid - Bengaluru",
        "Austin, Texas, United States", "London", "Unspecified", "",
    ]
    print("%-34s %-22s %-14s %-14s %s" % ("RAW", "CITY", "STATE", "COUNTRY", "MH?"))
    for s in samples:
        n = normalise(s)
        print("%-34s %-22s %-14s %-14s %s"
              % (repr(s)[:34], n["city"], n["state"] or "-", n["country"] or "-",
                 "YES" if n["is_maharashtra"] else ""))
