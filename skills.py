"""
skills.py -- curated skill dictionary + offline extraction.

Design rules (see CLAUDE.md):
  * No network calls. No model downloads. Runs instantly, offline.
  * Matching is regex + alias based, deliberately conservative: we would
    rather miss a mention than invent one. Every count on the dashboard
    traces back to a literal string match in a posting description.
  * Aliases are lowercase; matching is case-insensitive EXCEPT for entries
    in `strict` (used for dangerously short surface forms like "R").

Public API:
    extract_skills(text)  -> sorted list of canonical skill names
    all_skills()          -> sorted list of every canonical name
    skill_category(name)  -> category string
    aliases_for(name)     -> tuple of surface forms (for the seed generator)
"""

import re

# (canonical, category, aliases, strict_aliases)
# `aliases` are matched case-insensitively; `strict_aliases` case-sensitively.
SKILL_DEFS = [
    # ---------------- Data & BI ----------------
    ("SQL", "data", ("sql", "ansi sql", "sql queries"), ()),
    ("Advanced Excel", "data",
     ("excel", "ms excel", "microsoft excel", "advanced excel", "vlookup",
      "pivot table", "pivot tables"), ()),
    ("Power BI", "data", ("power bi", "powerbi", "power-bi", "ms power bi"), ()),
    ("Tableau", "data", ("tableau",), ()),
    ("Looker", "data", ("looker",), ()),
    ("Google Data Studio", "data", ("google data studio", "looker studio", "data studio"), ()),
    ("Qlik", "data", ("qlik", "qlikview", "qlik sense", "qliksense"), ()),
    ("Metabase", "data", ("metabase",), ()),
    ("Apache Superset", "data", ("apache superset", "superset"), ()),
    ("Google Sheets", "data", ("google sheets", "gsheets", "g-sheets"), ()),
    ("VBA", "data", ("vba", "excel macros", "excel macro"), ()),
    ("SAS", "data", ("sas",), ()),
    ("SPSS", "data", ("spss",), ()),
    ("Alteryx", "data", ("alteryx",), ()),
    ("Data Cleaning", "data",
     ("data cleaning", "data cleansing", "data wrangling", "data munging"), ()),
    ("Data Visualization", "data",
     ("data visualization", "data visualisation", "dataviz", "data viz"), ()),
    ("Data Storytelling", "data",
     ("data storytelling", "storytelling with data", "insight storytelling"), ()),
    ("Data Modeling", "data",
     ("data modeling", "data modelling", "dimensional modeling", "star schema"), ()),
    ("Data Warehousing", "data",
     ("data warehouse", "data warehousing", "dwh"), ()),
    ("ETL", "data", ("etl", "elt", "etl pipelines", "etl pipeline"), ()),
    ("dbt", "data", ("dbt", "data build tool"), ()),
    ("Apache Airflow", "data", ("airflow", "apache airflow"), ()),
    ("Snowflake", "data", ("snowflake",), ()),
    ("BigQuery", "data", ("bigquery", "big query"), ()),
    ("Redshift", "data", ("redshift", "amazon redshift"), ()),
    ("Databricks", "data", ("databricks",), ()),
    ("Apache Spark", "data", ("apache spark", "pyspark", "spark"), ()),
    ("Hadoop", "data", ("hadoop", "hdfs", "mapreduce"), ()),
    ("Statistics", "data",
     ("statistics", "statistical analysis", "descriptive statistics",
      "inferential statistics"), ()),
    ("Hypothesis Testing", "data",
     ("hypothesis testing", "a/b testing", "ab testing", "significance testing"), ()),
    ("Time Series Analysis", "data",
     ("time series", "time-series", "demand forecasting", "forecasting"), ()),
    ("Pandas", "data", ("pandas",), ()),
    ("NumPy", "data", ("numpy",), ()),
    ("Matplotlib", "data", ("matplotlib", "seaborn"), ()),
    ("R", "data", (), ("R",)),

    # ---------------- ML / AI ----------------
    ("Machine Learning", "ai",
     ("machine learning", "ml models", "predictive modeling", "predictive modelling"), ()),
    ("scikit-learn", "ai", ("scikit-learn", "scikit learn", "sklearn"), ()),
    ("TensorFlow", "ai", ("tensorflow",), ()),
    ("PyTorch", "ai", ("pytorch",), ()),
    ("Deep Learning", "ai", ("deep learning", "neural networks", "neural network"), ()),
    ("NLP", "ai", ("nlp", "natural language processing", "text mining"), ()),
    ("Computer Vision", "ai", ("computer vision", "opencv", "image processing"), ()),
    ("Feature Engineering", "ai", ("feature engineering",), ()),
    ("Recommendation Systems", "ai",
     ("recommendation system", "recommendation systems", "recommender system",
      "recommender systems"), ()),
    ("MLOps", "ai", ("mlops", "ml ops"), ()),
    ("MLflow", "ai", ("mlflow",), ()),
    ("LLM", "ai",
     ("llm", "llms", "large language model", "large language models",
      "generative ai", "gen ai", "genai"), ()),
    ("Prompt Engineering", "ai",
     ("prompt engineering", "prompt design", "prompting techniques"), ()),
    ("RAG", "ai",
     ("rag", "retrieval augmented generation", "retrieval-augmented generation",
      "rag pipeline", "rag pipelines"), ()),
    ("Vector Databases", "ai",
     ("vector database", "vector databases", "vector db", "pinecone",
      "weaviate", "chromadb", "faiss", "vector search"), ()),
    ("LangChain", "ai", ("langchain", "lang chain"), ()),
    ("LlamaIndex", "ai", ("llamaindex", "llama index"), ()),
    ("Agent Orchestration", "ai",
     ("agent orchestration", "agentic workflow", "agentic workflows",
      "ai agents", "multi-agent", "multi agent", "agentic ai"), ()),
    ("Fine-tuning", "ai",
     ("fine-tuning", "fine tuning", "finetuning", "lora", "peft"), ()),
    ("Embeddings", "ai", ("embeddings", "text embeddings", "embedding models"), ()),
    ("OpenAI API", "ai",
     ("openai api", "openai", "gpt-4", "gpt4", "anthropic api", "claude api"), ()),
    ("Hugging Face", "ai", ("hugging face", "huggingface", "transformers library"), ()),
    ("Model Evaluation", "ai",
     ("model evaluation", "model evals", "llm evaluation", "eval harness",
      "hallucination testing"), ()),
    ("AI Governance", "ai",
     ("ai governance", "responsible ai", "ai ethics", "model risk", "ai policy"), ()),

    # ---------------- Backend / Platform ----------------
    ("Java", "backend", ("java", "core java", "java 8", "java 17"), ()),
    ("Spring Boot", "backend", ("spring boot", "springboot", "spring framework", "spring mvc"), ()),
    ("Node.js", "backend", ("node.js", "nodejs", "node js"), ()),
    ("Express.js", "backend", ("express.js", "expressjs", "express framework"), ()),
    ("Python", "backend", ("python", "python3"), ()),
    ("Django", "backend", ("django",), ()),
    ("Flask", "backend", ("flask",), ()),
    ("FastAPI", "backend", ("fastapi", "fast api"), ()),
    ("Golang", "backend", ("golang", "go lang"), ()),
    ("Rust", "backend", ("rust",), ()),
    ("C++", "backend", ("c++", "cpp"), ()),
    ("C#", "backend", ("c#", "csharp"), ()),
    (".NET", "backend", (".net", "dotnet", "asp.net", "asp .net"), ()),
    ("TypeScript", "backend", ("typescript",), ()),
    ("JavaScript", "backend", ("javascript",), ()),
    ("React", "backend", ("react", "react.js", "reactjs"), ()),
    ("REST API", "backend",
     ("rest api", "rest apis", "restful", "restful api", "rest services"), ()),
    ("GraphQL", "backend", ("graphql",), ()),
    ("gRPC", "backend", ("grpc",), ()),
    ("Microservices", "backend",
     ("microservices", "microservice architecture", "micro-services"), ()),
    ("Docker", "backend", ("docker", "containerization", "containerisation"), ()),
    ("Kubernetes", "backend", ("kubernetes", "k8s", "eks", "aks"), ()),
    ("AWS", "backend", ("aws", "amazon web services"), ()),
    ("Azure", "backend", ("azure", "microsoft azure"), ()),
    ("GCP", "backend", ("gcp", "google cloud", "google cloud platform"), ()),
    ("Terraform", "backend", ("terraform", "infrastructure as code", "iac"), ()),
    ("CI/CD", "backend",
     ("ci/cd", "cicd", "ci cd", "continuous integration", "continuous delivery"), ()),
    ("Jenkins", "backend", ("jenkins",), ()),
    ("GitHub Actions", "backend", ("github actions", "gitlab ci"), ()),
    ("Git", "backend", ("git", "version control"), ()),
    ("Linux", "backend", ("linux", "unix", "shell scripting", "bash scripting"), ()),
    ("Nginx", "backend", ("nginx",), ()),
    ("Redis", "backend", ("redis",), ()),
    ("PostgreSQL", "backend", ("postgresql", "postgres"), ()),
    ("MySQL", "backend", ("mysql",), ()),
    ("MongoDB", "backend", ("mongodb", "mongo db"), ()),
    ("Elasticsearch", "backend", ("elasticsearch", "elastic search", "opensearch"), ()),
    ("Apache Kafka", "backend", ("kafka", "apache kafka"), ()),
    ("RabbitMQ", "backend", ("rabbitmq", "rabbit mq"), ()),
    ("Message Queues", "backend", ("message queue", "message queues", "pub/sub", "pubsub"), ()),
    ("Caching", "backend", ("caching", "cache invalidation", "in-memory cache"), ()),
    ("Load Balancing", "backend", ("load balancing", "load balancer"), ()),
    ("System Design", "backend",
     ("system design", "distributed systems", "high level design", "hld"), ()),
    ("Unit Testing", "backend",
     ("unit testing", "unit tests", "pytest", "junit", "jest", "tdd"), ()),
    ("Serverless", "backend", ("serverless", "aws lambda", "azure functions"), ()),
    ("OAuth", "backend", ("oauth", "oauth2", "jwt", "sso"), ()),
    ("Observability", "backend",
     ("observability", "prometheus", "grafana", "datadog", "distributed tracing"), ()),

    # ---------------- Business analysis ----------------
    ("Requirement Gathering", "business",
     ("requirement gathering", "requirements gathering", "requirement elicitation",
      "requirements elicitation", "requirement analysis"), ()),
    ("BRD", "business",
     ("brd", "business requirement document", "business requirements document",
      "business requirement documents", "business requirements documents",
      "frd", "functional specification", "functional specifications"), ()),
    ("User Stories", "business",
     ("user story", "user stories", "acceptance criteria", "epics"), ()),
    ("Agile", "business", ("agile", "scrum", "kanban", "sprint planning"), ()),
    ("JIRA", "business", ("jira",), ()),
    ("Confluence", "business", ("confluence",), ()),
    ("Stakeholder Management", "business",
     ("stakeholder management", "stakeholder communication", "client interaction"), ()),
    ("Process Mapping", "business",
     ("process mapping", "process flow", "bpmn", "as-is to-be", "swimlane"), ()),
    ("UAT", "business", ("uat", "user acceptance testing"), ("SIT",)),
    ("Gap Analysis", "business", ("gap analysis", "gap assessment"), ()),
    ("Wireframing", "business",
     ("wireframing", "wireframes", "wireframe", "figma", "mockups", "balsamiq"), ()),
    ("KPI Definition", "business",
     ("kpi", "kpis", "key performance indicator", "key performance indicators",
      "metric definition"), ()),
    ("Root Cause Analysis", "business",
     ("root cause analysis", "rca", "5 whys"), ()),
    ("BFSI Domain", "business",
     ("bfsi", "banking domain", "insurance domain", "capital markets domain"), ()),
    ("Six Sigma", "business", ("six sigma", "lean six sigma"), ()),
    ("Business Case", "business", ("business case", "business justification"), ()),
    ("Cost Benefit Analysis", "business",
     ("cost benefit analysis", "cost-benefit analysis", "roi analysis"), ()),
    ("Salesforce", "business", ("salesforce", "sfdc"), ()),
    ("SAP", "business", ("sap", "sap fico", "sap mm"), ()),
    ("UML", "business", ("uml", "use case diagram", "sequence diagram"), ()),

    # ---------------- CS fundamentals ----------------
    # These are curriculum-side terms. They also appear in real postings, so
    # they belong in the dictionary rather than in a separate mapping file --
    # that keeps the curriculum diff a comparison of like with like.
    ("Data Structures & Algorithms", "fundamentals",
     ("data structures", "dsa", "algorithms", "data structures and algorithms"), ()),
    ("Object Oriented Programming", "fundamentals",
     ("object oriented programming", "object-oriented programming", "oops concepts", "oop"), ()),
    ("Operating Systems", "fundamentals",
     ("operating systems", "operating system concepts", "os concepts"), ()),
    ("Computer Networks", "fundamentals",
     ("computer networks", "networking fundamentals", "tcp/ip", "osi model"), ()),
    ("Software Engineering", "fundamentals",
     ("software engineering", "sdlc", "software development life cycle"), ()),
    ("Discrete Mathematics", "fundamentals",
     ("discrete mathematics", "discrete maths", "graph theory"), ()),
    ("Compiler Design", "fundamentals", ("compiler design", "theory of computation"), ()),
    ("HTML/CSS", "fundamentals", ("html", "css", "html5", "html/css"), ()),
    ("Cloud Computing", "fundamentals", ("cloud computing", "cloud fundamentals"), ()),
    ("Cybersecurity", "fundamentals",
     ("cybersecurity", "cyber security", "information security", "network security"), ()),
]

# ---------------------------------------------------------------- matching

# Loose boundary: allows "Node.js-based", "Docker/Kubernetes", "(AWS)".
_PRE = r"(?<![A-Za-z0-9_+#])"
_SUF = r"(?![A-Za-z0-9_+#])"
# Strict boundary for single-letter / high-collision forms ("R" must not fire
# on "R&D" or "R-Studio").
_PRE_STRICT = r"(?<![A-Za-z0-9_+#&\-])"
_SUF_STRICT = r"(?![A-Za-z0-9_+#&\-])"


def _build(defs):
    compiled = []
    for canonical, category, aliases, strict in defs:
        pats = []
        if aliases:
            # Longest alias first so "power bi" wins over any shorter overlap.
            alts = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
            pats.append(re.compile(_PRE + "(?:" + alts + ")" + _SUF, re.IGNORECASE))
        if strict:
            alts = "|".join(re.escape(a) for a in sorted(strict, key=len, reverse=True))
            pats.append(re.compile(_PRE_STRICT + "(?:" + alts + ")" + _SUF_STRICT))
        compiled.append((canonical, category, tuple(pats)))
    return compiled


_COMPILED = _build(SKILL_DEFS)
_CATEGORY = {c: cat for c, cat, _a, _s in SKILL_DEFS}
_ALIASES = {c: tuple(a) + tuple(s) for c, _cat, a, s in SKILL_DEFS}

if len(_CATEGORY) != len(SKILL_DEFS):
    raise RuntimeError("duplicate canonical skill name in SKILL_DEFS")


def extract_skills(text):
    """Return the sorted, de-duplicated canonical skills mentioned in `text`."""
    if not text:
        return []
    found = set()
    for canonical, _cat, pats in _COMPILED:
        for p in pats:
            if p.search(text):
                found.add(canonical)
                break
    return sorted(found)


def all_skills():
    return sorted(_CATEGORY)


def skill_category(name):
    return _CATEGORY.get(name, "other")


def aliases_for(name):
    return _ALIASES[name]


def match_sentences(text, canonical, max_hits=6):
    """Sentences in `text` that caused `canonical` to be extracted.

    The drawer must show WHY a posting was counted, not just that it was.
    Showing the sentence lets a reader judge whether the mention is a real
    requirement or incidental company description -- a distinction the count
    itself cannot make.
    """
    if not text or canonical not in _CATEGORY:
        return []
    pats = dict((c, p) for c, _cat, p in
                ((x[0], x[1], x[2]) for x in _COMPILED)).get(canonical)
    if not pats:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    hits = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        for pat in pats:
            m = pat.search(chunk)
            if m:
                hits.append({"sentence": chunk[:400],
                             "matched": m.group(0)})
                break
        if len(hits) >= max_hits:
            break
    return hits


def skill_count():
    return len(SKILL_DEFS)


if __name__ == "__main__":
    sample = (
        "Looking for a Data Analyst with strong SQL and Advanced Excel skills. "
        "Exposure to Power BI dashboards, Python (pandas), and R is preferred. "
        "Familiarity with dbt, Snowflake and RAG pipelines is a plus. "
        "Our R&D team uses C++ and ASP.NET on the side."
    )
    print("dictionary size:", skill_count(), "canonical skills")
    print("categories:", sorted(set(_CATEGORY.values())))
    print("sample extraction:", extract_skills(sample))
