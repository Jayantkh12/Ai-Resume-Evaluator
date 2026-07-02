import re
from collections import Counter

from utils.jd_match import extract_keywords
from utils.parser import find_skills, flatten_skills, parse_resume_profile


def build_nlp_context(resume_text, jd_text):
    resume_profile = parse_resume_profile(resume_text)
    jd_skills = find_skills(jd_text)
    resume_skills = resume_profile["skills"]
    semantic_terms = extract_semantic_terms(jd_text)

    return {
        "resume_metadata": resume_profile["metadata"],
        "resume_word_count": resume_profile["word_count"],
        "resume_sections": {
            section: bool(content.strip())
            for section, content in resume_profile["sections"].items()
        },
        "resume_skills_by_category": resume_skills,
        "resume_skills_flat": flatten_skills(resume_skills),
        "jd_skills_by_category": jd_skills,
        "jd_skills_flat": flatten_skills(jd_skills),
        "jd_keywords": extract_keywords(jd_text, limit=35),
        "semantic_terms": semantic_terms,
        "nlp_engine": semantic_terms.get("engine", "regex"),
    }


def extract_semantic_terms(text):
    spacy_terms = extract_with_spacy(text)
    if spacy_terms:
        return {
            "engine": "spaCy",
            "noun_phrases": spacy_terms,
            "key_phrases": spacy_terms[:20],
        }

    phrases = extract_regex_phrases(text)
    return {
        "engine": "regex",
        "noun_phrases": phrases,
        "key_phrases": phrases[:20],
    }


def extract_with_spacy(text):
    try:
        import spacy

        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            nlp = spacy.blank("en")
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")

        doc = nlp(text[:12000])
        if not hasattr(doc, "noun_chunks"):
            return []

        terms = []
        for chunk in doc.noun_chunks:
            phrase = clean_phrase(chunk.text)
            if phrase and 2 <= len(phrase.split()) <= 5:
                terms.append(phrase)
        return most_common_terms(terms, limit=35)
    except Exception:
        return []


def extract_regex_phrases(text):
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]*", text.lower())
    grams = []
    for size in (2, 3):
        grams.extend(" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1))
    return most_common_terms([clean_phrase(item) for item in grams], limit=35)


def clean_phrase(value):
    value = re.sub(r"\s+", " ", value.lower()).strip(" .,:;()[]{}")
    if not value or len(value) < 4:
        return ""
    blocked = {
        "and the",
        "for the",
        "with the",
        "you will",
        "will be",
        "the candidate",
        "this role",
    }
    if value in blocked:
        return ""
    return value


def most_common_terms(items, limit):
    counter = Counter(item for item in items if item)
    return [term for term, _count in counter.most_common(limit)]
