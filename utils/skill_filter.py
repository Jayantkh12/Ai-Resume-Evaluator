import re

from utils.parser import SKILL_CATEGORIES, normalize_skill_name

KNOWN_SKILLS = {
    normalize_skill_name(skill).lower()
    for skills in SKILL_CATEGORIES.values()
    for skill in skills
}

EXTRA_VALID_SKILLS = {
    "ci/cd",
    "rest APIs".lower(),
    "system design",
    "oop",
    "object oriented programming",
    "spring boot",
    "mern stack",
    "mean stack",
    "prompt engineering",
    "data analysis",
    "data visualization",
    "cloud deployment",
    "software testing",
    "debugging",
}

NOISY_SKILL_LABELS = {
    "eng",
    "engineer",
    "engineering",
    "software",
    "software eng",
    "software engineer",
    "software engineering",
    "developer",
    "development",
    "candidate",
    "role",
    "job",
    "position",
    "profile",
    "responsibility",
    "responsibilities",
    "requirement",
    "requirements",
    "experience",
    "years",
    "year",
    "team",
    "teams",
    "requires",
    "required",
    "require",
    "preferred",
    "needed",
    "seeking",
    "looking",
    "qualification",
    "qualifications",
    "rest",
    "good",
    "strong",
    "knowledge",
    "understanding",
    "familiarity",
    "excellent",
    "ability",
    "build",
    "built",
    "write",
    "create",
    "document",
    "product",
    "business",
    "client",
    "customer",
}

NOISY_PATTERNS = [
    r"\b\d+\+?\s*years?\b",
    r"\b(years?|months?)\s+of\b",
    r"\b(software|data|backend|frontend|full stack)\s+eng\b",
    r"\b(engineer|developer|candidate|role|position)\b",
    r"\b(good|strong|excellent)\s+(knowledge|understanding|skills?)\b",
    r"\b(requires|required|require|preferred|needed|seeking|looking)\b",
]


def filter_skill_terms(items):
    return unique_terms(item for item in items if is_valid_skill_term(item))


def filter_keyword_terms(items):
    return unique_terms(item for item in items if is_valid_keyword_term(item))


def is_valid_skill_term(value):
    term = normalize_term(value)
    if not term:
        return False
    if term.lower() in KNOWN_SKILLS or term.lower() in EXTRA_VALID_SKILLS:
        return True
    return is_valid_keyword_term(term) and has_skill_signal(term)


def is_valid_keyword_term(value):
    term = normalize_term(value)
    lowered = term.lower()
    if lowered in KNOWN_SKILLS or lowered in EXTRA_VALID_SKILLS:
        return True
    if not term or lowered in NOISY_SKILL_LABELS:
        return False
    if re.search(r"[!?]", term) or re.search(r"\w\.\s+\w", term):
        return False
    if len(lowered) < 3 and lowered not in {"ai", "ml", "go", "r", "c"}:
        return False
    if any(re.search(pattern, lowered) for pattern in NOISY_PATTERNS):
        return False
    tokens = re.findall(r"[a-z0-9+#./-]+", lowered)
    if any(token in NOISY_SKILL_LABELS for token in tokens):
        return False
    if tokens and all(token in NOISY_SKILL_LABELS for token in tokens):
        return False
    if is_accidental_skill_pair(tokens, lowered):
        return False
    return True


def has_skill_signal(term):
    lowered = term.lower()
    if lowered in EXTRA_VALID_SKILLS:
        return True
    if re.search(r"[+#/.]", term):
        return True
    skill_markers = [
        "api",
        "cloud",
        "database",
        "testing",
        "design",
        "deployment",
        "automation",
        "analysis",
        "visualization",
        "security",
        "architecture",
    ]
    return any(marker in lowered for marker in skill_markers)


def normalize_term(value):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" .,:;()[]{}")
    return text


def is_accidental_skill_pair(tokens, lowered):
    if len(tokens) != 2:
        return False
    if lowered in KNOWN_SKILLS or lowered in EXTRA_VALID_SKILLS:
        return False
    return all(token in KNOWN_SKILLS or token in EXTRA_VALID_SKILLS for token in tokens)


def unique_terms(items):
    seen = set()
    output = []
    for item in items:
        text = normalize_term(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output
