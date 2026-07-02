import re

from utils.jd_match import calculate_match
from utils.parser import flatten_skills, parse_resume_profile


def score_resume(resume_text, jd_text):
    profile = parse_resume_profile(resume_text)
    match = calculate_match(resume_text, jd_text)
    sections = profile["section_presence"]

    skills_score = min(100, int(match["keyword_match_score"] * 0.75 + len(match["resume_skills"]) * 4))
    experience_score = section_score(
        sections.get("experience"),
        profile["word_count"],
        has_metrics=has_metrics(resume_text),
        action_verb_count=count_action_verbs(resume_text),
    )
    projects_score = project_score(profile)
    formatting_score = formatting_score_for(profile, resume_text)

    breakdown = {
        "Skills": clamp(skills_score),
        "Experience": clamp(experience_score),
        "Projects": clamp(projects_score),
        "Formatting": clamp(formatting_score),
    }
    overall = round(
        breakdown["Skills"] * 0.38
        + breakdown["Experience"] * 0.27
        + breakdown["Projects"] * 0.2
        + breakdown["Formatting"] * 0.15
    )

    return {
        "match_percentage": clamp(overall),
        "rank_label": rank_label(overall),
        "score_breakdown": breakdown,
        "profile": profile,
        "match": match,
        "ats_flags": ats_flags(profile, resume_text, match),
    }


def section_score(section_present, word_count, has_metrics=False, action_verb_count=0):
    score = 30 if section_present else 8
    if word_count >= 250:
        score += 18
    if word_count >= 450:
        score += 12
    if has_metrics:
        score += 22
    score += min(18, action_verb_count * 3)
    return score


def project_score(profile):
    score = 25 if profile["section_presence"].get("projects") else 8
    project_text = profile["sections"].get("projects", "")
    if len(project_text.split()) > 40:
        score += 25
    if profile["skills"]:
        score += min(25, len(flatten_skills(profile["skills"])) * 3)
    if re.search(r"\b(github|live|demo|deployed|api|dashboard|model)\b", project_text, re.I):
        score += 25
    return score


def formatting_score_for(profile, resume_text):
    score = 25
    metadata = profile["metadata"]
    if metadata.get("email"):
        score += 15
    if metadata.get("phone"):
        score += 10
    if profile["section_presence"].get("skills"):
        score += 12
    if profile["section_presence"].get("education"):
        score += 10
    if profile["bullet_count"] >= 4:
        score += 12
    if len(re.findall(r"\t| {5,}", resume_text)) < 5:
        score += 8
    if 250 <= profile["word_count"] <= 900:
        score += 8
    return score


def ats_flags(profile, resume_text, match):
    flags = []
    if not profile["metadata"].get("email"):
        flags.append("Add a professional email address in the header.")
    if not profile["metadata"].get("phone"):
        flags.append("Add a phone number in the header.")
    if not profile["section_presence"].get("skills"):
        flags.append("Create a dedicated Skills section grouped by category.")
    if not profile["section_presence"].get("projects"):
        flags.append("Add a Projects section with role-relevant outcomes.")
    if not has_metrics(resume_text):
        flags.append("Add measurable impact such as %, revenue, time saved, users, or scale.")
    if match["missing_keywords"]:
        flags.append("Mirror the most important missing job keywords naturally in skills and experience.")
    return flags[:8]


def has_metrics(text):
    return bool(re.search(r"\b\d+(\.\d+)?\s*(%|percent|users|clients|hours|days|months|x|k|m)\b", text, re.I))


def count_action_verbs(text):
    verbs = [
        "built",
        "created",
        "developed",
        "designed",
        "implemented",
        "improved",
        "optimized",
        "automated",
        "led",
        "managed",
        "delivered",
        "reduced",
        "increased",
    ]
    return sum(len(re.findall(rf"\b{verb}\b", text, re.I)) for verb in verbs)


def rank_label(score):
    if score >= 75:
        return "Best Match"
    if score >= 50:
        return "Medium Match"
    return "Weak Match"


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, int(value)))
