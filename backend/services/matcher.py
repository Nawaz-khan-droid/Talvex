"""
Job-resume matching engine for TALVEX.
Implements keyword-based skill matching, phrase-level matching,
match score calculation, skill gap analysis, and text-based skill extraction.

Enhanced features:
- Phrase extraction (2-word and 3-word key phrases)
- Section-aware JD comparison
- Weighted scoring (60% keywords + 40% phrases)
- Detailed match reports with recommendations
"""

import json
import re
from typing import Any

# ============================================================
# Predefined skill list (100+ technical skills)
# ============================================================

TECHNICAL_SKILLS: list[str] = [
    # Languages
    "python", "javascript", "typescript", "java", "go", "rust", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl",
    "shell scripting", "bash", "powershell", "sql",
    # Frontend
    "react", "angular", "vue.js", "vue", "svelte", "next.js", "nuxt.js",
    "html", "css", "sass", "scss", "less", "tailwindcss", "tailwind",
    "bootstrap", "material ui", "antd", "chakra ui", "storybook",
    "webpack", "vite", "rollup", "babel", "redux", "graphql", "rest api",
    # Backend
    "node.js", "express", "fastapi", "django", "flask", "spring boot",
    "spring", "rails", "laravel", "asp.net", "gin", "fiber",
    "microservices", "api design", "restful", "grpc",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "dynamodb", "sqlite", "cassandra", "neo4j", "firestore",
    "supabase", "prisma", "typeorm", "sqlalchemy",
    # DevOps & Cloud
    "docker", "kubernetes", "aws", "azure", "gcp", "google cloud",
    "terraform", "ansible", "jenkins", "github actions", "gitlab ci",
    "circleci", "argocd", "nginx", "apache", "cloudflare",
    # Data & ML
    "machine learning", "deep learning", "tensorflow", "pytorch",
    "scikit-learn", "sklearn", "pandas", "numpy", "spark", "hadoop",
    "nlp", "computer vision", "llm", "openai", "langchain",
    "data engineering", "etl", "airflow", "dbt",
    "data analysis", "data modeling", "data visualization",
    "statistical analysis", "power bi", "tableau", "seaborn",
    "google analytics", "jupyter", "pycharm",
    "ms sql server", "power query", "power pivot",
    # Data Analyst — expanded
    "excel", "vba", "google sheets", "spreadsheet", "pivot table",
    "vlookup", "xlookup", "index match", "macros",
    "sas", "spss", "stata", "minitab",
    "sql server", "ssis", "ssrs", "ssas",
    "redshift", "bigquery", "snowflake", "databricks", "data warehouse",
    "looker", "qlik", "spotfire", "thoughtspot", "metabase",
    "python data analysis", "r language", "data analysis",
    "ab testing", "a/b testing", "hypothesis testing",
    "regression analysis", "predictive modeling", "forecasting",
    "data mining", "text mining", "sentiment analysis",
    "descriptive analytics", "prescriptive analytics",
    "dashboards", "kpi", "metrics", "data governance",
    "data quality", "master data management", "data lineage",
    "cobol", "data lakes", "delta lake", "iceberg",
    "stitch", "fivetran", "matillion", "talend", "informatica",
    "alteryx", "knime", "rapidminer",
    "excel dashboard", "financial modeling", "dax",
    # Testing
    "jest", "pytest", "cypress", "selenium", "playwright",
    "unit testing", "integration testing", "tdd", "bdd",
    # Other
    "git", "github", "gitlab", "bitbucket", "jira", "confluence",
    "linux", "agile", "scrum", "ci/cd", "devops",
    "figma", "design systems", "ui/ux", "accessibility", "a11y",
    "cybersecurity", "oauth", "jwt", "websocket", "oauth2",
    "three.js", "d3.js", "chart.js", "matplotlib", "uat",
    "protobuf", "kafka", "rabbitmq", "message queue",
    "caching", "load balancing", "cdn", "serverless",
    "lambda", "cloud functions", "firebase", "auth0",
    "storybook", "monorepo", "turborepo", "nx",
]

SKILL_CATEGORIES: dict[str, list[str]] = {
    "Languages": ["python", "javascript", "typescript", "java", "go", "rust", "c++", "c#", "ruby", "php", "swift", "kotlin", "scala", "r", "sql"],
    "Frontend": ["react", "angular", "vue.js", "vue", "svelte", "next.js", "html", "css", "tailwindcss", "bootstrap", "redux", "graphql"],
    "Backend": ["node.js", "express", "fastapi", "django", "flask", "spring boot", "microservices", "rest api", "grpc"],
    "Databases": ["postgresql", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "sqlite"],
    "DevOps & Cloud": ["docker", "kubernetes", "aws", "azure", "gcp", "terraform", "jenkins", "github actions", "ci/cd", "devops"],
    "Data & ML": ["machine learning", "deep learning", "tensorflow", "pytorch", "pandas", "numpy", "spark", "nlp", "llm"],
    "Data Analysis": ["data analysis", "data visualization", "power bi", "tableau", "excel", "sql server", "bigquery", "snowflake", "redshift", "data warehouse", "ab testing", "hypothesis testing", "regression analysis", "predictive modeling", "forecasting", "data mining", "sas", "spss", "stata"],
    "Testing": ["jest", "pytest", "cypress", "selenium", "playwright", "unit testing", "tdd"],
}

STOP_WORDS: set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "could", "did", "do", "does", "doing", "don", "down", "during", "each",
    "few", "for", "from", "further", "get", "got", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "just", "ll", "m", "ma", "me", "might", "more", "most", "must", "my",
    "myself", "need", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
    "per", "re", "s", "same", "she", "should", "so", "some", "such", "t",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "us", "ve", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "would",
    "you", "your", "yours", "yourself", "yourselves", "also", "about", "above",
    "after", "again", "all", "am", "any", "because", "before", "below",
    "between", "both", "dear", "either", "else", "ever", "every",
    "however", "keep", "know", "last", "like", "long", "look", "make",
    "many", "may", "much", "must", "name", "never", "new", "next", "one",
    "part", "people", "put", "right", "said", "say", "see", "set",
    "show", "since", "something", "still", "take", "tell", "thing", "think",
    "three", "time", "turn", "two", "use", "used", "using", "want", "way",
    "well", "went", "come", "day", "even", "give", "find", "here", "just",
    "let", "live", "man", "number", "old", "place", "point",
    "small", "sound", "study", "their", "there", "these", "they", "thing",
    "those", "thought", "understand", "upon", "water", "whether", "without",
    "work", "world", "would", "write", "year", "ability", "able",
    "experience", "strong", "looking", "working", "required", "including",
    "responsibilities", "requirements", "qualifications", "preferred",
    "benefits", "opportunity", "team", "company", "role", "position",
    "candidate", "join", "based", "using", "building", "developing",
    "help", "ensure", "support", "provide", "create", "manage", "lead",
}

# Multilingual aliases are normalized to canonical English tokens before scoring.
SKILL_ALIASES: dict[str, str] = {
    "python数据分析": "python data analysis",
    "r语言": "r language",
    "数据分析": "data analysis",
}


# ============================================================
# Phrase Extraction (2-word and 3-word key phrases)
# ============================================================

def extract_phrases(text: str, n: int = 2) -> list[str]:
    """
    Extract n-word key phrases from text, filtering out phrases
    where all words are stop words or words are too short.

    Args:
        text: Input text
        n: Phrase length (2 or 3)

    Returns:
        Sorted list of unique key phrases
    """
    cleaned = re.sub(r"[^a-z0-9+#.\-\/\s]", " ", text.lower())
    words = cleaned.split()
    words = [w for w in words if len(w) > 1]

    phrases: set[str] = set()
    for i in range(len(words) - n + 1):
        chunk = words[i : i + n]
        # Accept phrase if at least one word is NOT a stop word
        non_stop = [w for w in chunk if w not in STOP_WORDS]
        if non_stop:
            phrase = " ".join(chunk)
            # Only keep phrases that have a non-stop-word component
            phrases.add(phrase)

    return sorted(phrases)


def extract_key_phrases(text: str) -> list[str]:
    """
    Extract all key phrases (2-word and 3-word) from text.
    Returns a sorted list of unique phrases, filtering stop words.
    """
    phrases_2 = extract_phrases(text, 2)
    phrases_3 = extract_phrases(text, 3)

    # Deduplicate: remove any 3-word phrase whose 2-word sub-phrases
    # don't contain at least one non-stop word pair
    all_phrases = set(phrases_2) | set(phrases_3)
    return sorted(all_phrases)


# ============================================================
# Section Detection
# ============================================================

RESUME_SECTIONS: list[str] = [
    "experience", "education", "skills", "summary", "objective",
    "projects", "certifications", "contact", "references",
    "languages", "achievements", "professional experience",
    "work experience", "technical skills", "education background",
    "personal projects", "professional summary", "career objective",
    "publications", "volunteer", "honors", "awards", "training",
    "professional development", "additional information",
]

def detect_sections(text: str) -> list[str]:
    """
    Detect standard resume sections present in the text.
    Returns a list of matched section names.
    """
    lower = text.lower()
    found: list[str] = []
    for section in RESUME_SECTIONS:
        if section in lower:
            found.append(section)
    return sorted(set(found))


# ============================================================
# Core Extraction Functions (unchanged API)
# ============================================================

def extract_keywords(text: str) -> list[str]:
    """
    Extract keywords from text, filtering stop words and short words.
    """
    normalized_text = _normalize_skill_aliases(text.lower())
    cleaned = re.sub(r"[^a-z0-9+#.\-\/\s]", " ", normalized_text)
    words = cleaned.split()
    words = [w for w in words if len(w) > 1 and w not in STOP_WORDS]
    return sorted(set(words))


def extract_skills_from_text(text: str) -> list[str]:
    """
    Extract known technical skills from text using the predefined skill list.
    Returns a sorted list of matched skill names.
    """
    text_lower = _normalize_skill_aliases(text.lower())
    found: list[str] = []

    for skill in TECHNICAL_SKILLS:
        # Use word boundary matching for shorter skills
        if len(skill) <= 3:
            pattern = r"\b" + re.escape(skill) + r"\b"
        else:
            pattern = re.escape(skill)

        if re.search(pattern, text_lower):
            found.append(skill)

    return sorted(set(found))


def _normalize_skill_aliases(text: str) -> str:
    normalized = text
    for alias, canonical in SKILL_ALIASES.items():
        normalized = normalized.replace(alias.lower(), canonical)
    return normalized


# ============================================================
# Match Score (unchanged API)
# ============================================================

def calculate_match_score(
    job_description: str,
    persona_skills: list[str],
) -> dict[str, Any]:
    """
    Calculate match score between job description and persona skills.

    Args:
        job_description: The raw job description text
        persona_skills: List of skills from the persona (strings)

    Returns:
        dict with score (0-100), matched (list), missing (list)
    """
    jd_keywords = extract_keywords(job_description)
    skills = [
        _normalize_skill_aliases(s.lower().strip())
        for s in persona_skills
        if s and s.strip()
    ]

    if not jd_keywords:
        return {"score": 0, "matched": [], "missing": []}

    skill_set = set(skills)
    jd_set = set(jd_keywords)

    matched: list[str] = []
    missing: list[str] = []

    for keyword in jd_keywords:
        is_match = False
        for skill in skills:
            if keyword == skill or keyword in skill or skill in keyword:
                is_match = True
                break
        if is_match:
            matched.append(keyword)
        else:
            missing.append(keyword)

    score = min(100, round((len(matched) / max(1, len(jd_keywords))) * 100))

    return {
        "score": score,
        "matched": sorted(set(matched)),
        "missing": sorted(set(missing))[:20],
    }


# ============================================================
# ATS Score (enhanced, backward-compatible)
# ============================================================

def calculate_ats_score(text: str, job_description: str | None = None) -> int:
    """
    Calculate an ATS compatibility score (0-100) based on text structure.

    When only `text` (resume) is provided: basic structure check (backward compatible).
    When `job_description` is also provided: section-aware JD comparison
    with keyword matching and phrase matching bonus.

    Args:
        text: The resume text
        job_description: Optional JD text for section-aware comparison

    Returns:
        Integer score from 0 to 100
    """
    score = 0
    lower = text.lower()

    # --- Part 1: Resume structure scoring (original logic) ---
    standard_sections = [
        "experience", "education", "skills", "summary",
        "objective", "projects", "certifications", "contact",
        "references", "languages", "achievements",
    ]

    for section in standard_sections:
        if section in lower:
            score += 2
    score = min(score, 30)

    # Penalize tables/columns (ATS unfriendly)
    if "table" not in lower and "column" not in lower:
        score += 20

    words = lower.split()
    if len(words) > 100:
        score += 10
    if len(words) > 200:
        score += 5
    score = min(score, 35)

    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 5:
        score += 10
    if len(sentences) > 10:
        score += 5

    bullet_points = len(re.findall(r"[-•*]", text))
    if bullet_points > 3:
        score += 10
    if bullet_points > 8:
        score += 5

    if re.search(r"\d+", text):
        score += 5

    # --- Part 2: JD-aware bonus (only when JD provided) ---
    if job_description:
        # Section detection bonus: resume has key sections aligned with JD
        detected = detect_sections(text)
        section_bonus = min(10, len(detected) * 2)
        score += section_bonus

        # Keyword overlap bonus with JD
        resume_keywords = set(extract_keywords(text))
        jd_keywords = set(extract_keywords(job_description))
        if jd_keywords:
            overlap = resume_keywords & jd_keywords
            keyword_pct = len(overlap) / len(jd_keywords)
            jd_keyword_bonus = min(10, round(keyword_pct * 10))
            score += jd_keyword_bonus

        # Phrase overlap bonus
        resume_phrases = set(extract_key_phrases(text))
        jd_phrases = set(extract_key_phrases(job_description))
        if jd_phrases:
            phrase_overlap = resume_phrases & jd_phrases
            phrase_pct = len(phrase_overlap) / len(jd_phrases)
            jd_phrase_bonus = min(5, round(phrase_pct * 5))
            score += jd_phrase_bonus

    return min(100, score)


# ============================================================
# Enhanced Match Score (new API)
# ============================================================

def calculate_match_score_enhanced(
    resume_text: str,
    jd_text: str,
) -> dict[str, Any]:
    """
    Calculate an enhanced match report between a resume and a job description.

    Uses:
    - Single-word keyword matching (weighted 60%)
    - Phrase-level matching (2-3 word phrases, weighted 40%)
    - Section detection bonus
    - Recommendations based on score thresholds

    Args:
        resume_text: The resume text
        jd_text: The job description text

    Returns:
        Detailed match report dict with:
        - keywordMatchPct: Keyword match percentage (0-100)
        - phraseMatchPct: Phrase match percentage (0-100)
        - sectionBonus: Bonus points from section detection
        - overallScore: Weighted overall score (60% keywords + 40% phrases + bonus)
        - matchedKeywords: List of matched single-word keywords
        - matchedPhrases: List of matched phrases
        - missingKeywords: Top 15 missing JD keywords not in resume
        - missingPhrases: Top 10 missing JD phrases not in resume
        - detectedSections: Sections detected in resume
        - recommendations: List of improvement recommendations
    """
    # --- Keyword matching ---
    resume_keywords = set(extract_keywords(resume_text))
    jd_keywords = set(extract_keywords(jd_text))

    if not jd_keywords:
        return {
            "keywordMatchPct": 0,
            "phraseMatchPct": 0,
            "sectionBonus": 0,
            "overallScore": 0,
            "matchedKeywords": [],
            "matchedPhrases": [],
            "missingKeywords": [],
            "missingPhrases": [],
            "detectedSections": [],
            "recommendations": ["Job description is too short or empty. Please provide a more detailed JD."],
        }

    matched_kw = resume_keywords & jd_keywords
    missing_kw = jd_keywords - resume_keywords
    keyword_pct = round((len(matched_kw) / len(jd_keywords)) * 100)

    # --- Phrase matching ---
    resume_phrases = set(extract_key_phrases(resume_text))
    jd_phrases = set(extract_key_phrases(jd_text))

    if jd_phrases:
        matched_phr = resume_phrases & jd_phrases
        missing_phr = jd_phrases - resume_phrases
        phrase_pct = round((len(matched_phr) / len(jd_phrases)) * 100)
    else:
        matched_phr = set()
        missing_phr = set()
        phrase_pct = 0

    # --- Section detection bonus ---
    sections = detect_sections(resume_text)
    section_bonus = min(10, len(sections) * 2)

    # --- Weighted overall score ---
    base_score = round(keyword_pct * 0.6 + phrase_pct * 0.4)
    overall_score = min(100, base_score + section_bonus)

    # --- Missing keywords (top 15, prioritized by importance) ---
    missing_kw_sorted = _prioritize_keywords(missing_kw, jd_text)[:15]

    # --- Missing phrases (top 10) ---
    missing_phr_sorted = sorted(missing_phr)[:10]

    # --- Recommendations ---
    recommendations = _generate_recommendations(
        overall_score, keyword_pct, phrase_pct, sections, len(missing_kw_sorted)
    )

    return {
        "keywordMatchPct": keyword_pct,
        "phraseMatchPct": phrase_pct,
        "sectionBonus": section_bonus,
        "overallScore": overall_score,
        "matchedKeywords": sorted(matched_kw),
        "matchedPhrases": sorted(matched_phr),
        "missingKeywords": missing_kw_sorted,
        "missingPhrases": missing_phr_sorted,
        "detectedSections": sections,
        "recommendations": recommendations,
    }


def _prioritize_keywords(missing_keywords: set[str], jd_text: str) -> list[str]:
    """
    Prioritize missing keywords by frequency in JD and technical relevance.
    Keywords that are technical skills get higher priority.
    """
    jd_lower = jd_text.lower()
    skill_set = {s.lower() for s in TECHNICAL_SKILLS}

    scored: list[tuple[str, int]] = []
    for kw in missing_keywords:
        priority = 0
        # Count occurrences in JD
        count = jd_lower.count(kw)
        priority += min(count, 5)

        # Boost technical skills
        if kw in skill_set:
            priority += 10

        # Boost longer, more specific keywords
        priority += min(len(kw), 5)

        scored.append((kw, priority))

    # Sort by priority descending, then alphabetically
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [kw for kw, _ in scored]


def _generate_recommendations(
    overall_score: int,
    keyword_pct: int,
    phrase_pct: int,
    sections: list[str],
    missing_count: int,
) -> list[str]:
    """
    Generate actionable recommendations based on score analysis.
    """
    recs: list[str] = []

    # Overall score guidance
    if overall_score >= 80:
        recs.append("Excellent match! Your resume aligns strongly with this job description.")
    elif overall_score >= 60:
        recs.append("Good match overall. A few targeted improvements could push this higher.")
    elif overall_score >= 40:
        recs.append("Fair match. Consider adding relevant keywords and phrases from the JD to strengthen alignment.")
    else:
        recs.append("Low match score. Significant gaps exist between your resume and the job requirements.")

    # Keyword-specific guidance
    if keyword_pct < 50:
        recs.append("Add more technical keywords from the job description to improve ATS keyword matching.")

    # Phrase-specific guidance
    if phrase_pct < 40:
        recs.append("Include key phrases (e.g., 'data analysis', 'machine learning') exactly as they appear in the JD.")

    # Section guidance
    essential_sections = ["experience", "education", "skills"]
    for section in essential_sections:
        if section not in sections:
            recs.append(f"Add a clear '{section.title()}' section to your resume for better ATS parsing.")

    if len(sections) < 4:
        recs.append("Consider adding more standard sections (Projects, Certifications, Summary) to improve structure score.")

    # Missing keywords guidance
    if missing_count > 10:
        recs.append(f"There are {missing_count} keywords missing from your resume. Focus on the top 5-7 most relevant ones first.")
    elif missing_count > 0:
        recs.append(f"A few targeted keywords are missing. Adding them could improve your match score.")

    # Keyword-phrase imbalance
    if keyword_pct > phrase_pct + 25:
        recs.append("Your resume has good keyword coverage but low phrase matching. Try using the exact phrases from the JD.")

    return recs


# ============================================================
# Skill Gap Analysis (unchanged API)
# ============================================================

def analyze_skill_gap(
    persona_skills: list[str],
    market_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Analyze skill gaps between persona skills and market demand.

    Args:
        persona_skills: Current skills from the persona
        market_skills: Skills demanded by the market (optional; defaults to TECHNICAL_SKILLS)

    Returns:
        List of gap items with skill, category, priority, etc.
    """
    persona_lower = {s.lower().strip() for s in persona_skills if s and s.strip()}
    target_skills = set(market_skills) if market_skills else set(TECHNICAL_SKILLS)
    target_lower = {s.lower() for s in target_skills}

    missing_skills = target_lower - persona_lower

    gaps: list[dict[str, Any]] = []
    for i, skill in enumerate(sorted(missing_skills)):
        # Determine category
        category = "General"
        for cat, skills in SKILL_CATEGORIES.items():
            if skill in [s.lower() for s in skills]:
                category = cat
                break

        # Determine priority based on market demand heuristic
        high_demand = ["python", "react", "typescript", "aws", "docker", "kubernetes",
                       "machine learning", "llm", "node.js", "go", "power bi", "tableau",
                       "excel", "sql", "data analysis"]
        if skill in high_demand:
            priority = "high"
            market_demand = 90
            estimated_weeks = 8
        elif skill in [s.lower() for s in TECHNICAL_SKILLS[:40]]:
            priority = "medium"
            market_demand = 70
            estimated_weeks = 6
        else:
            priority = "low"
            market_demand = 50
            estimated_weeks = 4

        gaps.append({
            "skill": skill.title(),
            "category": category,
            "priority": priority,
            "marketDemand": market_demand,
            "learningPath": f"Start with fundamentals of {skill.title()}, then build projects.",
            "estimatedWeeks": estimated_weeks,
        })

    return gaps


# ============================================================
# Persona Skills JSON Parser (unchanged API)
# ============================================================

def get_personas_skills_json(skills_json: str) -> list[str]:
    """
    Parse the persona's skillsJson field into a list of skill strings.
    The field can be a JSON array string or a comma-separated string.
    """
    if not skills_json:
        return []

    try:
        parsed = json.loads(skills_json)
        if isinstance(parsed, list):
            return [str(s).strip() for s in parsed if s]
        return []
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat as comma-separated
        return [s.strip() for s in skills_json.split(",") if s.strip()]
