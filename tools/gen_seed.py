"""
tools/gen_seed.py -- regenerates data/postings.jsonl.

THIS PRODUCES SYNTHETIC DATA. Every emitted record carries source="synthetic"
and the dashboard must label it as such. It exists so the measurement pipeline
has something to chew on before the real National Career Service / Naukri
scrape lands (see scraper.py).

How the drift is produced
-------------------------
Each role has a set of skills with a linear probability ramp from 2024-Q1 to
2026-Q3, e.g. Advanced Excel 0.88 -> 0.42 (declining) and LLM 0.01 -> 0.46
(rising). For each posting we draw each skill independently as a Bernoulli
trial at that quarter's probability, then render the drawn skills into
Naukri-style prose.

Deliberately, we add NO extra noise on top. All quarter-to-quarter wiggle you
see in the dashboard is genuine binomial sampling noise from small buckets
(n is 12-25 per role-quarter). That is exactly the thing the low-confidence
flag exists to warn about, so it should be visible rather than smoothed away.

Posting volume ramps mildly over the window (12/quarter -> 25/quarter per
role), which mirrors both real hiring volume and better recent scrape
coverage. Consequence: the 2024 and early-2025 buckets land under the n=20
low-confidence threshold and get flagged. That is intended and honest --
600 records is genuinely not enough to make quarterly claims on, and the UI
should say so.

Run:  python tools/gen_seed.py
"""

import datetime as dt
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import skills as skills_mod

SEED = 20260910
TOTAL_PER_ROLE = 200
OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "postings.jsonl"
)

ROLES = ["Data Analyst", "Backend Developer", "Business Analyst"]

# ------------------------------------------------------------------ quarters


def quarters(start=(2024, 1), end=(2026, 3)):
    out = []
    y, q = start
    while (y, q) <= end:
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


QUARTERS = quarters()
N_Q = len(QUARTERS)

# Mild volume ramp: weights 0.65 -> 1.35, mean 1.0.
_WEIGHTS = [0.65 + 0.70 * i / (N_Q - 1) for i in range(N_Q)]


def quarter_counts(total):
    scale = total / sum(_WEIGHTS)
    counts = [int(round(w * scale)) for w in _WEIGHTS]
    # Fix rounding drift on the most recent quarters.
    i = N_Q - 1
    while sum(counts) > total:
        counts[i] -= 1
        i = (i - 1) % N_Q
    while sum(counts) < total:
        counts[i] += 1
        i = (i - 1) % N_Q
    return counts


def quarter_span(y, q):
    start = dt.date(y, 3 * (q - 1) + 1, 1)
    if q == 4:
        end = dt.date(y, 12, 31)
    else:
        end = dt.date(y, 3 * q + 1, 1) - dt.timedelta(days=1)
    return start, end


# ------------------------------------------------------- skill drift curves
# canonical skill -> (probability in 2024-Q1, probability in 2026-Q3)

ROLE_CURVES = {
    "Data Analyst": {
        "SQL": (0.92, 0.94),
        "Advanced Excel": (0.88, 0.42),
        "VBA": (0.34, 0.06),
        "Power BI": (0.55, 0.68),
        "Tableau": (0.42, 0.30),
        "Python": (0.45, 0.82),
        "Pandas": (0.22, 0.55),
        "NumPy": (0.14, 0.26),
        "Statistics": (0.48, 0.44),
        "Data Cleaning": (0.52, 0.50),
        "Data Visualization": (0.60, 0.58),
        "Google Sheets": (0.30, 0.18),
        "SAS": (0.16, 0.03),
        "SPSS": (0.12, 0.02),
        "Alteryx": (0.10, 0.05),
        "ETL": (0.35, 0.40),
        "dbt": (0.02, 0.34),
        "Snowflake": (0.06, 0.38),
        "Apache Airflow": (0.05, 0.26),
        "BigQuery": (0.10, 0.24),
        "Databricks": (0.04, 0.22),
        "Data Warehousing": (0.24, 0.30),
        "Data Modeling": (0.20, 0.28),
        "LLM": (0.01, 0.46),
        "Prompt Engineering": (0.00, 0.38),
        "RAG": (0.00, 0.24),
        "Agent Orchestration": (0.00, 0.19),
        "Vector Databases": (0.00, 0.14),
        "Model Evaluation": (0.02, 0.20),
        "OpenAI API": (0.00, 0.22),
        "Data Storytelling": (0.14, 0.30),
        "Machine Learning": (0.20, 0.28),
        "Time Series Analysis": (0.14, 0.16),
        "KPI Definition": (0.30, 0.32),
        "Hypothesis Testing": (0.18, 0.22),
        "Looker": (0.08, 0.16),
        "Git": (0.15, 0.30),
        "R": (0.20, 0.10),
    },
    "Backend Developer": {
        "Java": (0.62, 0.52),
        "Spring Boot": (0.55, 0.48),
        "Node.js": (0.40, 0.42),
        "Python": (0.38, 0.52),
        "FastAPI": (0.08, 0.30),
        "Django": (0.18, 0.14),
        "REST API": (0.80, 0.72),
        "Microservices": (0.52, 0.58),
        "Docker": (0.48, 0.72),
        "Kubernetes": (0.30, 0.58),
        "AWS": (0.55, 0.70),
        "Azure": (0.20, 0.28),
        "GCP": (0.14, 0.22),
        "PostgreSQL": (0.35, 0.46),
        "MySQL": (0.45, 0.34),
        "MongoDB": (0.32, 0.30),
        "Redis": (0.22, 0.36),
        "Apache Kafka": (0.24, 0.40),
        "CI/CD": (0.40, 0.62),
        "Jenkins": (0.30, 0.18),
        "GitHub Actions": (0.06, 0.30),
        "Terraform": (0.08, 0.28),
        "System Design": (0.35, 0.44),
        "Unit Testing": (0.40, 0.44),
        "Git": (0.60, 0.62),
        "Linux": (0.34, 0.32),
        "GraphQL": (0.12, 0.20),
        "gRPC": (0.06, 0.18),
        "Serverless": (0.14, 0.28),
        "Observability": (0.10, 0.34),
        "TypeScript": (0.18, 0.34),
        "Elasticsearch": (0.14, 0.16),
        "OAuth": (0.20, 0.30),
        "Caching": (0.22, 0.30),
        ".NET": (0.16, 0.12),
        "Golang": (0.10, 0.22),
        "Rust": (0.02, 0.08),
        "MLOps": (0.02, 0.14),
        "LLM": (0.00, 0.38),
        "RAG": (0.00, 0.22),
        "LangChain": (0.00, 0.18),
        "Vector Databases": (0.00, 0.20),
        "Prompt Engineering": (0.00, 0.26),
        "Agent Orchestration": (0.00, 0.20),
        "OpenAI API": (0.00, 0.26),
    },
    "Business Analyst": {
        "Requirement Gathering": (0.82, 0.76),
        "BRD": (0.60, 0.48),
        "User Stories": (0.55, 0.62),
        "Agile": (0.70, 0.72),
        "JIRA": (0.55, 0.58),
        "Confluence": (0.30, 0.32),
        "SQL": (0.42, 0.60),
        "Advanced Excel": (0.80, 0.52),
        "Power BI": (0.35, 0.55),
        "Tableau": (0.22, 0.20),
        "Stakeholder Management": (0.58, 0.60),
        "Process Mapping": (0.44, 0.40),
        "UAT": (0.48, 0.42),
        "Gap Analysis": (0.30, 0.32),
        "Wireframing": (0.26, 0.30),
        "KPI Definition": (0.34, 0.44),
        "Root Cause Analysis": (0.22, 0.24),
        "BFSI Domain": (0.25, 0.26),
        "Six Sigma": (0.12, 0.07),
        "Business Case": (0.24, 0.26),
        "Cost Benefit Analysis": (0.16, 0.14),
        "Data Storytelling": (0.16, 0.34),
        "Python": (0.10, 0.26),
        "Data Visualization": (0.40, 0.46),
        "UML": (0.20, 0.14),
        "Salesforce": (0.18, 0.16),
        "SAP": (0.20, 0.17),
        "VBA": (0.22, 0.06),
        "Google Sheets": (0.26, 0.20),
        "LLM": (0.00, 0.34),
        "Prompt Engineering": (0.00, 0.30),
        "AI Governance": (0.00, 0.16),
        "Agent Orchestration": (0.00, 0.14),
        "Model Evaluation": (0.00, 0.12),
    },
}

# Alternate surface forms, used ~35% of the time so the extractor's alias
# handling is actually exercised by the seed corpus.
ALT_FORMS = {
    "Power BI": ["PowerBI", "Power-BI", "MS Power BI"],
    "LLM": ["Large Language Models", "GenAI", "Generative AI", "LLMs"],
    "RAG": ["Retrieval Augmented Generation", "RAG pipelines"],
    "Advanced Excel": ["MS Excel", "Excel", "Advanced Excel (VLOOKUP, Pivot Tables)"],
    "Node.js": ["NodeJS", "Node JS"],
    "Kubernetes": ["K8s"],
    "CI/CD": ["CICD", "Continuous Integration"],
    "Vector Databases": ["Vector DB (Pinecone / FAISS)", "vector search", "Weaviate"],
    "Agent Orchestration": ["Agentic Workflows", "AI Agents", "Multi-Agent systems"],
    "Prompt Engineering": ["Prompt Design"],
    "OpenAI API": ["GPT-4 APIs", "OpenAI API"],
    "Apache Airflow": ["Airflow"],
    "Apache Kafka": ["Kafka"],
    "Apache Spark": ["PySpark", "Spark"],
    "Machine Learning": ["ML models", "Predictive Modeling"],
    "Requirement Gathering": ["Requirements Gathering", "Requirement Elicitation"],
    "BRD": ["BRD/FRD", "Business Requirement Documents"],
    "Agile": ["Agile/Scrum", "Scrum", "Kanban"],
    "Unit Testing": ["Unit Testing (JUnit)", "TDD", "PyTest"],
    "Observability": ["Observability (Prometheus/Grafana)", "Distributed Tracing"],
    "Data Visualization": ["Data Visualisation"],
    "Time Series Analysis": ["Time Series Forecasting", "Demand Forecasting"],
    "Hypothesis Testing": ["A/B Testing"],
    "Golang": ["Golang", "Go Lang"],
    "Statistics": ["Statistical Analysis"],
    ".NET": [".NET", "ASP.NET"],
    "Serverless": ["AWS Lambda", "Serverless"],
    "Terraform": ["Terraform (IaC)"],
    "Data Warehousing": ["Data Warehousing", "DWH"],
    "Model Evaluation": ["Model Evaluation", "Model Evals"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "VBA": ["VBA"],
    "Data Cleaning": ["Data Cleaning", "Data Wrangling"],
    "Linux": ["Linux", "Shell Scripting"],
    "Git": ["Git", "Version Control"],
    "KPI Definition": ["KPI definition", "KPIs"],
    "Root Cause Analysis": ["Root Cause Analysis", "RCA"],
    "UAT": ["UAT", "User Acceptance Testing"],
    "GCP": ["GCP", "Google Cloud"],
    "Wireframing": ["Wireframing", "Wireframes", "Figma"],
}

# ------------------------------------------------------------------ prose

COMPANIES = [
    "Infosys", "TCS", "Wipro", "HCLTech", "Tech Mahindra", "LTIMindtree",
    "Mphasis", "Cognizant", "Capgemini India", "Accenture India", "Genpact",
    "WNS Global Services", "Hexaware", "Persistent Systems", "Coforge",
    "Birlasoft", "Zensar", "Happiest Minds", "Sonata Software", "Cyient",
    "Fractal Analytics", "Mu Sigma", "Tiger Analytics", "LatentView Analytics",
    "Course5 Intelligence", "Zoho", "Freshworks", "Razorpay", "Zerodha",
    "PhonePe", "CRED", "Meesho", "Groww", "Nykaa", "Delhivery", "Flipkart",
    "Myntra", "Paytm", "Swiggy", "Zomato", "Dream11", "Lenskart",
    "Urban Company", "PolicyBazaar", "upGrad", "Axis Bank", "HDFC Bank",
    "Kotak Mahindra Bank", "Bajaj Finserv", "ICICI Lombard", "Deloitte India",
    "EY GDS", "PwC India", "KPMG India", "Quest Global", "Sutherland",
    "Jio Platforms", "Ather Energy", "Zepto", "Porter",
]

LOCATIONS = [
    "Bengaluru, Karnataka", "Bengaluru, Karnataka", "Hyderabad, Telangana",
    "Pune, Maharashtra", "Pune, Maharashtra", "Mumbai, Maharashtra",
    "Navi Mumbai, Maharashtra", "Thane, Maharashtra", "Nagpur, Maharashtra",
    "Chennai, Tamil Nadu", "Coimbatore, Tamil Nadu", "Gurugram, Haryana",
    "Noida, Uttar Pradesh", "New Delhi, Delhi", "Kolkata, West Bengal",
    "Ahmedabad, Gujarat", "Indore, Madhya Pradesh", "Jaipur, Rajasthan",
    "Kochi, Kerala", "Bhubaneswar, Odisha", "Chandigarh", "Remote - India",
    "Hybrid - Bengaluru", "Hybrid - Pune",
]

TITLES = {
    "Data Analyst": [
        "Data Analyst", "Data Analyst - Business Insights", "Junior Data Analyst",
        "Analyst - Data and Reporting", "Senior Data Analyst",
        "Data Analyst - Growth", "MIS and Data Analyst", "Product Data Analyst",
        "Data Analyst - Supply Chain", "Associate Data Analyst",
        "Data Analyst - Risk and Fraud",
    ],
    "Backend Developer": [
        "Backend Developer", "Software Engineer - Backend", "Backend Engineer",
        "Senior Backend Developer", "SDE-1 Backend", "SDE-2 Backend",
        "Backend Developer - Microservices", "Backend Engineer - Platform",
        "Software Development Engineer - Server Side",
        "Associate Backend Engineer",
    ],
    "Business Analyst": [
        "Business Analyst", "Senior Business Analyst", "Junior Business Analyst",
        "Business Analyst - Digital Transformation", "Analyst - Business Systems",
        "Business Analyst - BFSI", "Product Business Analyst",
        "Business Analyst - Operations", "Associate Business Analyst",
        "Business Analyst - Process Excellence",
    ],
}

TEAMS = {
    "Data Analyst": [
        "Business Intelligence", "Growth Analytics", "Central Analytics",
        "Revenue Operations", "Data and Insights", "Customer Analytics",
    ],
    "Backend Developer": [
        "Core Platform", "Payments Engineering", "Order Management",
        "Identity and Access", "Merchant Systems", "Infrastructure Services",
    ],
    "Business Analyst": [
        "Digital Transformation", "Process Excellence", "Product Management",
        "Operations Strategy", "Client Solutions", "Programme Delivery",
    ],
}

INTROS = {
    "Data Analyst": [
        "You will sit with the business team and turn messy operational data into decisions people actually act on.",
        "This role owns the numbers that leadership reviews every Monday morning.",
        "We need someone who can go from a vague question to a defensible answer without three rounds of hand-holding.",
        "The role is a mix of recurring reporting and one-off deep dives into where the business is leaking money.",
        "You will be the first analyst embedded in this vertical, so expect to build the reporting layer from scratch.",
    ],
    "Backend Developer": [
        "You will own services that stay up when traffic goes 10x during a sale event.",
        "This is a hands-on coding role on systems that process a few million requests a day.",
        "We are re-platforming a monolith and need engineers comfortable carving out services without breaking callers.",
        "The team runs what it builds, so you will be on the design, the deploy and the pager.",
        "Expect to spend most of your week writing production code, not slide decks.",
    ],
    "Business Analyst": [
        "You will be the bridge between operations teams who know the problem and engineers who will build the fix.",
        "This role is for someone who can write a specification precise enough that nobody has to guess.",
        "You will map current processes end to end, find where they break, and make the case for changing them.",
        "The role sits with the client, so clarity in writing and in a room both matter.",
        "You will run discovery, document it properly, and stay involved through delivery and sign-off.",
    ],
}

RESP = {
    "Data Analyst": [
        "Build and maintain recurring dashboards and reports using {s} for business stakeholders.",
        "Write, optimise and document {s} logic against large transactional datasets.",
        "Partner with product and operations teams to define metrics and track them using {s}.",
        "Own end-to-end delivery of the reporting pipeline, including {s}.",
        "Investigate anomalies in business metrics and present findings, using {s} where relevant.",
        "Translate open-ended business questions into a concrete analysis plan built on {s}.",
        "Automate manual reporting workflows that currently take analysts several hours a week.",
        "Maintain data quality checks and document known caveats for every published metric.",
    ],
    "Backend Developer": [
        "Design, build and ship backend services using {s}.",
        "Own the reliability, latency and cost of services built on {s}.",
        "Write clean, tested, reviewable code with {s} as part of the standard toolchain.",
        "Participate in design reviews and produce written designs covering {s}.",
        "Debug and resolve production incidents, including the {s} layer.",
        "Improve deployment and release workflows, particularly around {s}.",
        "Break down existing monolithic modules into independently deployable services.",
        "Review peers' pull requests and hold the bar on correctness and readability.",
    ],
    "Business Analyst": [
        "Run requirement discovery workshops and document outcomes, including {s}.",
        "Produce clear specifications and supporting artefacts such as {s}.",
        "Work with engineering to groom the backlog and clarify scope using {s}.",
        "Analyse existing processes and quantify the impact of proposed changes using {s}.",
        "Coordinate testing and sign-off cycles, covering {s}.",
        "Present findings and recommendations to stakeholders, supported by {s}.",
        "Track delivery against agreed scope and escalate deviations early.",
        "Maintain traceability between business requirements and delivered functionality.",
    ],
}

EXPERIENCE = [
    "0-2 years", "1-3 years", "2-4 years", "2-5 years", "3-6 years",
    "4-7 years", "1-2 years", "0-1 years",
]
NOTICE = [
    "Immediate to 15 days", "Immediate joiners preferred", "Up to 30 days",
    "Up to 60 days", "Serving notice period preferred", "30-45 days",
]
MODE = ["Work from office", "Hybrid (3 days from office)", "Remote", "Hybrid (2 days from office)"]
CLOSERS = [
    "Interested candidates may apply through the portal with an updated resume.",
    "Shortlisted candidates will be contacted for a telephonic screening round.",
    "This is a full-time position. Salary is competitive and based on experience.",
    "Please apply only if you meet the minimum experience criteria mentioned above.",
    "We are an equal opportunity employer.",
]


def surface(rng, canonical):
    """Pick a surface form for a skill; ~35% of the time use an alias."""
    alts = ALT_FORMS.get(canonical)
    if alts and rng.random() < 0.35:
        return rng.choice(alts)
    return canonical


def prob_at(curve, i):
    p0, p1 = curve
    t = i / (N_Q - 1)
    return p0 + (p1 - p0) * t


def pick_skills(rng, role, qi):
    """Independent Bernoulli draw per skill at this quarter's probability."""
    curves = ROLE_CURVES[role]
    for _attempt in range(6):
        chosen = [(s, prob_at(c, qi)) for s, c in curves.items() if rng.random() < prob_at(c, qi)]
        if len(chosen) >= 4:
            chosen.sort(key=lambda x: -x[1])
            return [s for s, _p in chosen]
    chosen.sort(key=lambda x: -x[1])
    return [s for s, _p in chosen]


def render(rng, role, chosen, company, city, team):
    forms = [surface(rng, s) for s in chosen]
    split = max(2, int(len(forms) * 0.6))
    must, nice = forms[:split], forms[split:]

    resp_pool = list(RESP[role])
    rng.shuffle(resp_pool)
    bullets = []
    for tmpl in resp_pool[:4]:
        if "{s}" in tmpl:
            bullets.append(tmpl.format(s=rng.choice(must)))
        else:
            bullets.append(tmpl)

    lines = []
    lines.append(
        "%s is hiring a %s to join the %s team in %s."
        % (company, role, team, city.split(",")[0])
    )
    lines.append("")
    lines.append(rng.choice(INTROS[role]))
    lines.append("")
    lines.append("Key Responsibilities:")
    for b in bullets:
        lines.append("- " + b)
    lines.append("")
    lines.append("Must Have:")
    lines.append("- " + ", ".join(must) + ".")
    if nice:
        lines.append("")
        lines.append("Good to Have:")
        lines.append("- " + ", ".join(nice) + ".")
    lines.append("")
    lines.append(
        "Experience: %s | Notice Period: %s | Work Mode: %s"
        % (rng.choice(EXPERIENCE), rng.choice(NOTICE), rng.choice(MODE))
    )
    lines.append(rng.choice(CLOSERS))
    return "\n".join(lines)


ROLE_CODE = {"Data Analyst": "DA", "Backend Developer": "BE", "Business Analyst": "BA"}


def generate():
    rng = random.Random(SEED)
    counts = quarter_counts(TOTAL_PER_ROLE)
    records = []
    for role in ROLES:
        n = 0
        for qi, (y, q) in enumerate(QUARTERS):
            start, end = quarter_span(y, q)
            span = (end - start).days
            for _ in range(counts[qi]):
                n += 1
                chosen = pick_skills(rng, role, qi)
                company = rng.choice(COMPANIES)
                city = rng.choice(LOCATIONS)
                team = rng.choice(TEAMS[role])
                posted = start + dt.timedelta(days=rng.randint(0, span))
                records.append({
                    "id": "SYN-%s-%04d" % (ROLE_CODE[role], n),
                    "title": rng.choice(TITLES[role]),
                    "company": company,
                    "location": city,
                    "posted_date": posted.isoformat(),
                    "role": role,
                    "description_text": render(rng, role, chosen, company, city, team),
                    "source": "synthetic",
                })
    records.sort(key=lambda r: (r["posted_date"], r["id"]))
    return records, counts


def main():
    records, counts = generate()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("wrote %d postings -> %s" % (len(records), OUT_PATH))
    print("per-role postings per quarter:")
    for (y, q), c in zip(QUARTERS, counts):
        flag = "  <-- below n=20, will be flagged low-confidence" if c < 20 else ""
        print("  %d-Q%d: %2d%s" % (y, q, c, flag))

    # Round-trip check: what we wrote must be recoverable by the extractor.
    total_hits = 0
    thin = 0
    for r in records:
        found = skills_mod.extract_skills(r["description_text"])
        total_hits += len(found)
        if len(found) < 4:
            thin += 1
    print("extractor round-trip: %.1f skills/posting average, %d postings under 4 skills"
          % (total_hits / len(records), thin))


if __name__ == "__main__":
    main()
