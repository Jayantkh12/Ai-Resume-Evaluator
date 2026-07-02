import re
from collections import Counter

from utils.parser import find_skills, flatten_skills
from utils.skill_filter import filter_keyword_terms

STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "also",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "but",
    "by",
    "can",
    "company",
    "candidate",
    "description",
    "for",
    "from",
    "has",
    "have",
    "help",
    "here",
    "his",
    "her",
    "in",
    "into",
    "is",
    "it",
    "job",
    "must",
    "of",
    "on",
    "or",
    "our",
    "role",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "using",
    "we",
    "with",
    "work",
    "you",
    "your",
}


def calculate_match(resume_text, jd_text):
    resume_skills = flatten_skills(find_skills(resume_text))
    jd_skills = flatten_skills(find_skills(jd_text))
    resume_tokens = set(tokenize(resume_text))
    jd_keywords = extract_keywords(jd_text, limit=24)

    matched_skills = []
    missing_skills = []
    for skill in jd_skills:
        if skill.lower() in {resume_skill.lower() for resume_skill in resume_skills}:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    matched_keywords = []
    missing_keywords = []
    for term in jd_keywords:
        term_lower = term.lower()
        if term_lower in {skill.lower() for skill in resume_skills} or all(
            token in resume_tokens for token in tokenize(term)
        ):
            matched_keywords.append(term)
        else:
            missing_keywords.append(term)

    skill_score = round((len(matched_skills) / len(jd_skills)) * 100) if jd_skills else 0
    keyword_score = round((len(matched_keywords) / len(jd_keywords)) * 100) if jd_keywords else 0

    if jd_skills and jd_keywords:
        score = round(skill_score * 0.7 + keyword_score * 0.3)
    elif jd_skills:
        score = skill_score
    elif jd_keywords:
        score = keyword_score
    else:
        score = 0

    return {
        "required_terms": unique_preserve_order(jd_skills + jd_keywords),
        "matched_keywords": unique_preserve_order(matched_skills + matched_keywords)[:16],
        "missing_keywords": missing_keywords[:16],
        "matched_skills": matched_skills[:16],
        "missing_skills": missing_skills[:16],
        "keyword_match_score": score,
        "skill_match_score": skill_score,
        "keyword_coverage_score": keyword_score,
        "resume_skills": resume_skills,
        "jd_skills": jd_skills,
    }


def extract_keywords(text, limit=20):
    tokens = tokenize(text)
    bigrams = [" ".join(pair) for pair in zip(tokens, tokens[1:])]
    counts = Counter(token for token in tokens if token not in STOPWORDS and len(token) > 2)
    counts.update(
        bigram
        for bigram in bigrams
        if all(token not in STOPWORDS and len(token) > 2 for token in bigram.split())
    )
    candidates = [keyword for keyword, _count in counts.most_common(limit * 3)]
    return filter_keyword_terms(candidates)[:limit]


def extract_job_trends(jd_text):
    skills = flatten_skills(find_skills(jd_text))
    if skills:
        return skills[:10]
    return extract_keywords(jd_text, limit=10)


def tokenize(text):
    return re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]*", text.lower())


def unique_preserve_order(items):
    seen = set()
    unique = []
    for item in items:
        normalized = item.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return unique
