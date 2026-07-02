import json
import os
import re

from utils.ats import rank_label, score_resume
from utils.nlp_analysis import build_nlp_context
from utils.parser import flatten_skills, parse_resume_profile
from utils.skill_filter import filter_keyword_terms, filter_skill_terms


AI_SCHEMA = {
    "ats_score": 0,
    "resume_score": 0,
    "jd_match_score": 0,
    "recommendation_score": 0,
    "summary": "",
    "technical_skills": [],
    "soft_skills": [],
    "missing_skills": [],
    "recommended_skills": [],
    "matched_keywords": [],
    "missing_keywords": [],
    "important_missing_technologies": [],
    "strengths": [],
    "weaknesses": [],
    "strong_sections": [],
    "weak_sections": [],
    "projects_analysis": "",
    "experience_analysis": "",
    "grammar_issues": [],
    "summary_improvement": "",
    "industry_match": "",
    "job_role_fit": "",
    "recommended_job_roles": [],
    "keyword_optimization": [],
    "ai_recommendations": [],
    "project_suggestions": [],
    "ats_improvements": [],
    "score_breakdown": {
        "Skills": 0,
        "Experience": 0,
        "Projects": 0,
        "Formatting": 0,
        "ATS Compatibility": 0,
        "JD Match": 0,
    },
    "resume_heatmap": [
        {"section": "Skills", "score": 0, "status": "strong|average|weak", "feedback": ""},
        {"section": "Experience", "score": 0, "status": "strong|average|weak", "feedback": ""},
        {"section": "Projects", "score": 0, "status": "strong|average|weak", "feedback": ""},
        {"section": "Formatting", "score": 0, "status": "strong|average|weak", "feedback": ""},
    ],
    "internship_readiness_score": 0,
    "company_fit_score": 0,
    "target_company_fit": [{"company": "", "advice": ""}],
    "improved_resume": {
        "summary": "",
        "skills_section": [],
        "project_bullets": [],
        "experience_bullets": [],
    },
}


def analyze_resume(resume_text, jd_text, target_companies=None):
    target_companies = target_companies or []
    deterministic = score_resume(resume_text, jd_text)
    nlp_context = build_nlp_context(resume_text, jd_text)
    fallback = build_fallback_analysis(deterministic, nlp_context, target_companies)

    ai_result, provider_meta = request_ai_analysis(resume_text, jd_text, target_companies, nlp_context)
    if ai_result:
        result = merge_ai_with_fallback(ai_result, fallback, deterministic, nlp_context, provider_meta)
    else:
        result = fallback
        result["analysis_provider"] = provider_meta["provider"]
        result["analysis_model"] = provider_meta["model"]
        result["analysis_warning"] = provider_meta["warning"]

    result["match_percentage"] = result["jd_match_score"]
    result["rank_label"] = rank_label(result["match_percentage"])
    result["final_verdict"] = result.get("summary", "")[:260]
    return result


def request_ai_analysis(resume_text, jd_text, target_companies, nlp_context):
    prompt = build_analysis_prompt(resume_text, jd_text, target_companies, nlp_context)
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    providers = ["gemini", "openai"] if provider != "openai" else ["openai", "gemini"]

    errors = []
    for provider_name in providers:
        if provider_name == "gemini":
            text, model, error = call_gemini(prompt)
        else:
            text, model, error = call_openai(prompt)

        if text:
            parsed = parse_json_response(text)
            if parsed:
                return parsed, {"provider": provider_name, "model": model, "warning": ""}
            errors.append(f"{provider_name} returned non-JSON output")
        elif error:
            errors.append(error)

    warning = "AI API unavailable; using local analysis."
    return None, {"provider": "local-fallback", "model": "local-nlp-rules", "warning": warning}


def build_analysis_prompt(resume_text, jd_text, target_companies, nlp_context):
    companies = ", ".join(target_companies) if target_companies else "Not specified"
    schema = json.dumps(AI_SCHEMA, indent=2)
    context = json.dumps(nlp_context, indent=2)

    return f"""
You are an expert ATS system, senior technical recruiter, resume editor, and job matching analyst.

Your task:
Analyze the resume deeply against the job description. Use semantic understanding, not shallow keyword counting.
Detect real technical skills, soft skills, missing technologies, weak sections, project quality, experience quality,
ATS risks, grammar issues, industry fit, and best job-role fit.

Scoring rules:
- ats_score: ATS parseability, structure, section quality, measurable bullets, formatting, keyword placement.
- resume_score: overall resume quality independent of the JD.
- jd_match_score: semantic match to the provided JD.
- recommendation_score: likelihood this candidate should be recommended for this role.
- company_fit_score: fit for listed target companies, or role/company style if not specified.
- internship_readiness_score: readiness for internship or entry-level hiring.

Important:
- Missing skills must be important skills from the JD that are absent or weak in the resume.
- Never list job-title fragments as missing skills. Invalid examples: "eng", "software eng",
  "software engineer", "developer", "role", "candidate", "experience".
- Missing skills should be real technologies, tools, concepts, or soft skills such as Docker,
  Kubernetes, AWS, REST APIs, SQL, DSA, Leadership, Communication.
- Do not invent skills that are not in the resume.
- Do not give generic suggestions. Every recommendation must reference the resume/JD context.
- Separate technical_skills from soft_skills.
- Project analysis must mention project relevance, tech stack clarity, impact metrics, deployment/GitHub evidence.
- Experience analysis must mention seniority, measurable outcomes, role alignment, and responsibility depth.
- Keyword optimization must include exact keywords/phrases to add naturally.
- Return ONLY valid JSON. No markdown. No explanation outside JSON.

Return JSON with this exact shape. Fill every field:
{schema}

Target companies:
{companies}

Pre-parsed NLP context from the backend:
{context}

JOB DESCRIPTION:
{jd_text[:9000]}

RESUME:
{resume_text[:12000]}
""".strip()


def call_gemini(prompt):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None, "", "GEMINI_API_KEY is missing"
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        errors = []
        for model_name in get_gemini_model_candidates(genai):
            try:
                model = genai.GenerativeModel(
                    model_name,
                    generation_config={
                        "temperature": 0.15,
                        "response_mime_type": "application/json",
                    },
                )
                response = model.generate_content(prompt)
                return getattr(response, "text", None), model_name, ""
            except Exception as exc:
                errors.append(f"{model_name}: {exc}")
        return None, "", "Gemini API unavailable or no generateContent model worked"
    except Exception as exc:
        return None, "", f"Gemini API failed: {exc}"


def get_gemini_model_candidates(genai):
    configured = os.getenv("GEMINI_MODEL", "").strip()
    candidates = []
    if configured:
        candidates.append(configured)

    preferred = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    candidates.extend(preferred)

    try:
        available = [
            model.name
            for model in genai.list_models()
            if "generateContent" in getattr(model, "supported_generation_methods", [])
        ]
        flash_models = [name for name in available if "flash" in name.lower()]
        pro_models = [name for name in available if "pro" in name.lower()]
        candidates.extend(flash_models + pro_models + available)
    except Exception:
        pass

    return unique_list(candidates)


def call_openai(prompt):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "", "OPENAI_API_KEY is missing"
    try:
        from openai import OpenAI

        model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert ATS and technical recruiter. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
        )
        return response.choices[0].message.content, model_name, ""
    except Exception as exc:
        return None, os.getenv("OPENAI_MODEL", "gpt-4o-mini"), f"OpenAI API failed: {exc}"


def parse_json_response(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def merge_ai_with_fallback(ai_result, fallback, deterministic, nlp_context, provider_meta):
    result = fallback.copy()
    result.update(sanitize_ai_result(ai_result))

    result["ats_score"] = score_value(result.get("ats_score"), fallback["ats_score"])
    result["resume_score"] = score_value(result.get("resume_score"), fallback["resume_score"])
    result["jd_match_score"] = score_value(result.get("jd_match_score"), fallback["jd_match_score"])
    result["recommendation_score"] = score_value(result.get("recommendation_score"), result["jd_match_score"])
    result["company_fit_score"] = score_value(result.get("company_fit_score"), result["jd_match_score"])
    result["internship_readiness_score"] = score_value(
        result.get("internship_readiness_score"),
        fallback["internship_readiness_score"],
    )

    result["score_breakdown"] = normalize_breakdown(result.get("score_breakdown"), deterministic["score_breakdown"])
    result["technical_skills"] = filter_skill_terms(result.get("technical_skills") or nlp_context["resume_skills_flat"])
    result["soft_skills"] = filter_skill_terms(result.get("soft_skills"))
    result["missing_skills"] = filter_skill_terms(result.get("missing_skills") or fallback["missing_skills"])
    result["missing_keywords"] = filter_keyword_terms(result.get("missing_keywords") or fallback["missing_keywords"])
    result["evidence_gaps"] = filter_keyword_terms(result.get("evidence_gaps") or fallback.get("evidence_gaps", []))
    result["important_missing_technologies"] = filter_skill_terms(
        result.get("important_missing_technologies") or result["missing_skills"]
    )
    result["recommended_skills"] = filter_skill_terms(result.get("recommended_skills") or fallback["recommended_skills"])
    result["matched_keywords"] = filter_keyword_terms(result.get("matched_keywords") or fallback["matched_keywords"])
    result["skill_categories"] = build_skill_categories(result, nlp_context)
    result["target_company_fit"] = normalize_company_fit(
        result.get("target_company_fit"),
        fallback["target_company_fit"],
    )
    result["resume_heatmap"] = normalize_heatmap(result.get("resume_heatmap"), result["score_breakdown"])
    result["analysis_provider"] = provider_meta["provider"]
    result["analysis_model"] = provider_meta["model"]
    result["analysis_warning"] = provider_meta["warning"]
    result["summary"] = result.get("summary") or build_summary(result)
    return result


def build_fallback_analysis(deterministic, nlp_context, target_companies):
    profile = deterministic["profile"]
    match = deterministic["match"]
    resume_skills = nlp_context["resume_skills_flat"]
    jd_skills = nlp_context["jd_skills_flat"]
    missing = filter_skill_terms(match.get("missing_skills") or [skill for skill in jd_skills if skill not in resume_skills])[:12]
    evidence_gaps = build_evidence_gaps(match, missing)[:12]

    ats_score = round(
        deterministic["score_breakdown"]["Formatting"] * 0.45
        + deterministic["score_breakdown"]["Skills"] * 0.25
        + deterministic["score_breakdown"]["Experience"] * 0.2
        + deterministic["score_breakdown"]["Projects"] * 0.1
    )
    resume_score = deterministic["match_percentage"]
    jd_match_score = match["keyword_match_score"]

    result = {
        "ats_score": ats_score,
        "resume_score": resume_score,
        "jd_match_score": jd_match_score,
        "recommendation_score": round((ats_score + resume_score + jd_match_score) / 3),
        "technical_skills": resume_skills,
        "soft_skills": nlp_context["resume_skills_by_category"].get("Soft Skills", []),
        "missing_skills": missing,
        "recommended_skills": build_recommended_skills(missing),
        "matched_keywords": match["matched_keywords"],
        "missing_keywords": evidence_gaps,
        "evidence_gaps": evidence_gaps,
        "important_missing_technologies": missing[:6],
        "strengths": build_strengths(profile, match),
        "weaknesses": build_weaknesses(profile, missing),
        "strong_sections": strong_sections(deterministic["score_breakdown"]),
        "weak_sections": weak_sections(deterministic["score_breakdown"]),
        "projects_analysis": project_analysis(profile, missing),
        "experience_analysis": experience_analysis(profile),
        "grammar_issues": [
            "Use action verbs at the start of bullets.",
            "Keep tense consistent across current and past roles.",
            "Replace vague claims with measurable outcomes.",
        ],
        "summary_improvement": build_summary_improvement(resume_skills, missing),
        "industry_match": infer_industry(jd_skills, nlp_context["jd_keywords"]),
        "recommended_job_roles": infer_roles(jd_skills, resume_skills),
        "keyword_optimization": build_keyword_optimization(missing, evidence_gaps, match["matched_keywords"]),
        "ai_recommendations": build_ai_recommendations(missing, target_companies),
        "project_suggestions": build_project_suggestions(missing, resume_skills),
        "ats_improvements": deterministic["ats_flags"],
        "score_breakdown": normalize_breakdown(
            None,
            {**deterministic["score_breakdown"], "JD Match": jd_match_score},
        ),
        "resume_heatmap": normalize_heatmap(None, deterministic["score_breakdown"]),
        "internship_readiness_score": internship_score(profile, resume_skills),
        "company_fit_score": jd_match_score,
        "target_company_fit": normalize_company_fit(None, build_company_fit(target_companies, missing)),
        "improved_resume": build_improved_resume_block(profile, missing, resume_skills),
        "skill_categories": nlp_context["resume_skills_by_category"],
        "resume_metadata": profile["metadata"],
        "summary": "",
        "analysis_provider": "local-fallback",
        "analysis_model": "local-nlp-rules",
        "analysis_warning": "Gemini/OpenAI did not return a valid response. Showing transparent local fallback.",
    }
    result["summary"] = build_summary(result)
    return result


def sanitize_ai_result(ai_result):
    sanitized = {}
    list_fields = [
        "technical_skills",
        "soft_skills",
        "missing_skills",
        "recommended_skills",
        "matched_keywords",
        "missing_keywords",
        "important_missing_technologies",
        "strengths",
        "weaknesses",
        "strong_sections",
        "weak_sections",
        "grammar_issues",
        "recommended_job_roles",
        "keyword_optimization",
        "ai_recommendations",
        "project_suggestions",
        "ats_improvements",
    ]
    text_fields = [
        "summary",
        "projects_analysis",
        "experience_analysis",
        "summary_improvement",
        "industry_match",
        "job_role_fit",
    ]
    score_fields = [
        "ats_score",
        "resume_score",
        "jd_match_score",
        "recommendation_score",
        "internship_readiness_score",
        "company_fit_score",
    ]
    for field in list_fields:
        if isinstance(ai_result.get(field), list):
            sanitized[field] = unique_list(ai_result[field])[:18]
    for field in text_fields:
        if isinstance(ai_result.get(field), str):
            sanitized[field] = ai_result[field].strip()
    for field in score_fields:
        if ai_result.get(field) is not None:
            sanitized[field] = score_value(ai_result[field], 0)
    for field in ["score_breakdown", "improved_resume"]:
        if isinstance(ai_result.get(field), dict):
            sanitized[field] = ai_result[field]
    if isinstance(ai_result.get("target_company_fit"), list):
        sanitized["target_company_fit"] = ai_result["target_company_fit"]
    if isinstance(ai_result.get("resume_heatmap"), list):
        sanitized["resume_heatmap"] = ai_result["resume_heatmap"]
    return sanitized


def normalize_breakdown(value, fallback):
    source = value if isinstance(value, dict) else {}
    jd_default = fallback.get("JD Match", fallback.get("Skills", 0))
    defaults = {
        "Skills": fallback.get("Skills", 0),
        "Experience": fallback.get("Experience", 0),
        "Projects": fallback.get("Projects", 0),
        "Formatting": fallback.get("Formatting", 0),
        "ATS Compatibility": fallback.get("Formatting", 0),
        "JD Match": jd_default,
    }
    return {key: score_value(source.get(key), default) for key, default in defaults.items()}


def normalize_heatmap(value, breakdown):
    heatmap = []
    if isinstance(value, list):
        for item in value[:8]:
            if isinstance(item, dict):
                section = str(item.get("section", "")).strip()
                if section:
                    score = score_value(item.get("score"), breakdown.get(section, 0))
                    heatmap.append(
                        {
                            "section": section,
                            "score": score,
                            "status": item.get("status") or heat_status(score),
                            "feedback": str(item.get("feedback", "")).strip(),
                        }
                    )
    if heatmap:
        return heatmap
    return [
        {
            "section": section,
            "score": score,
            "status": heat_status(score),
            "feedback": f"{section} is {heat_status(score)} and should be improved with role-specific evidence.",
        }
        for section, score in breakdown.items()
    ]


def normalize_company_fit(value, fallback):
    if isinstance(value, list) and value:
        cleaned = []
        for item in value[:6]:
            if isinstance(item, dict):
                company = str(item.get("company", "Target company")).strip() or "Target company"
                advice = str(item.get("advice", "")).strip()
                if advice:
                    cleaned.append({"company": company, "advice": advice})
        if cleaned:
            return cleaned
    return fallback


def build_skill_categories(result, nlp_context):
    categories = dict(nlp_context["resume_skills_by_category"])
    if result.get("technical_skills"):
        categories["Technical Skills"] = unique_list(result["technical_skills"])
    if result.get("soft_skills"):
        categories["Soft Skills"] = unique_list(result["soft_skills"])
    return categories


def build_summary(result):
    missing_skills = result.get("missing_skills", [])[:4]
    evidence_gaps = result.get("evidence_gaps", result.get("missing_keywords", []))[:4]
    roles = ", ".join(result.get("recommended_job_roles", [])[:2]) or "the target role"
    if missing_skills:
        improvement = f"learn/add evidence for {', '.join(missing_skills)}"
    elif result.get("jd_match_score", 0) < 60 and evidence_gaps:
        improvement = f"show clearer JD evidence for {', '.join(evidence_gaps)}"
    elif result.get("jd_match_score", 0) < 60:
        improvement = "add stronger role-specific project and experience proof"
    else:
        improvement = "add quantified achievements and sharper project impact"
    return (
        f"Resume quality is {result['resume_score']}%, ATS compatibility is {result['ats_score']}%, "
        f"and JD match is {result['jd_match_score']}%. Best fit is {roles}; improve chances by {improvement}."
    )


def build_strengths(profile, match):
    skills = flatten_skills(profile["skills"])
    strengths = []
    if skills:
        strengths.append(f"Relevant skills detected: {', '.join(skills[:6])}.")
    if profile["section_presence"].get("projects"):
        strengths.append("Projects section is present and can support role fit.")
    if profile["section_presence"].get("experience"):
        strengths.append("Experience section is present for recruiter evaluation.")
    if match["matched_keywords"]:
        strengths.append(f"Matches JD keywords such as {', '.join(match['matched_keywords'][:5])}.")
    return strengths[:5] or ["Resume text is readable and can be optimized with stronger evidence."]


def build_weaknesses(profile, missing):
    weaknesses = []
    if missing:
        weaknesses.append(f"Missing important JD skills: {', '.join(missing[:6])}.")
    if not profile["section_presence"].get("projects"):
        weaknesses.append("Projects section is missing or not clearly labelled.")
    if not profile["section_presence"].get("experience"):
        weaknesses.append("Experience section is missing or weak.")
    if profile["word_count"] < 300:
        weaknesses.append("Resume is short and may not provide enough evidence for ATS ranking.")
    return weaknesses[:5] or ["Add more quantified outcomes and role-specific keywords."]


def build_recommended_skills(missing):
    return missing[:8]


def build_evidence_gaps(match, missing_skills):
    missing_skill_keys = {item.lower() for item in missing_skills}
    evidence = []
    for keyword in filter_keyword_terms(match.get("missing_keywords", [])):
        tokens = re.findall(r"[a-z0-9+#./-]+", keyword.lower())
        if len(tokens) == 1 and tokens[0] not in {"api", "apis", "testing", "deployment", "dashboard", "dashboards"}:
            continue
        if keyword.lower() not in missing_skill_keys:
            evidence.append(keyword)
    return unique_list(evidence)


def build_keyword_optimization(missing, evidence_gaps, matched):
    items = [f"Add missing skill naturally: {skill}." for skill in missing[:8]]
    items.extend(f"Add JD evidence/keyword naturally: {keyword}." for keyword in evidence_gaps[:8])
    if matched:
        items.append(f"Keep matched skills visible near the top: {', '.join(matched[:5])}.")
    return items[:10]


def build_ai_recommendations(missing, target_companies):
    recommendations = [
        "Rewrite the summary to match the target job title and top JD requirements.",
        "Add measurable impact to experience bullets using numbers, scale, or outcomes.",
        "Group skills by Languages, Frameworks, Databases, Cloud, Tools, and Soft Skills.",
    ]
    if missing:
        recommendations.insert(0, f"Learn or add proof for these missing skills: {', '.join(missing[:5])}.")
    else:
        recommendations.insert(0, "No major new technical skill is missing; improve score by proving JD keywords in projects and experience.")
    if target_companies:
        recommendations.append(f"Tailor one summary line for {', '.join(target_companies[:3])}.")
    return recommendations[:8]


def build_project_suggestions(missing, resume_skills):
    stack = ", ".join((missing or resume_skills)[:4]) or "the target stack"
    return [
        f"Build and deploy a role-specific project using {stack}; include GitHub, live link, and measurable outcome.",
        "Add an architecture or workflow bullet explaining APIs, database, testing, and deployment.",
        "Create one project that directly mirrors the JD responsibilities and keywords.",
    ]


def build_summary_improvement(resume_skills, missing):
    skills = ", ".join(resume_skills[:4]) or "core technical skills"
    gaps = ", ".join(missing[:3]) or "target-role keywords"
    return f"Write a 3-line summary that highlights {skills}, measurable impact, and alignment with {gaps}."


def build_improved_resume_block(profile, missing, resume_skills):
    skills = unique_list(resume_skills + missing)
    return {
        "summary": build_summary_improvement(resume_skills, missing),
        "skills_section": [f"Technical Skills: {', '.join(skills[:20])}"] if skills else [],
        "project_bullets": [
            f"Built a JD-aligned project using {', '.join(skills[:4])} with documented architecture and measurable results.",
            "Added testing, deployment notes, GitHub link, and outcome metrics to improve recruiter confidence.",
        ],
        "experience_bullets": [
            "Improved a workflow by applying automation, APIs, data handling, and measurable performance improvements.",
            "Collaborated with stakeholders to deliver maintainable features with documented business impact.",
        ],
    }


def build_company_fit(target_companies, missing):
    if not target_companies:
        return [{"company": "Target role", "advice": "Add target companies for company-specific fit scoring."}]
    gap_text = ", ".join(missing[:3]) or "project impact and role-specific keywords"
    return [
        {"company": company, "advice": f"Improve fit by adding evidence for {gap_text} and company-relevant projects."}
        for company in target_companies[:6]
    ]


def infer_roles(jd_skills, resume_skills):
    skills = {skill.lower() for skill in jd_skills + resume_skills}
    roles = []
    if {"python", "flask", "django", "fastapi", "sql"} & skills:
        roles.append("Backend Developer")
    if {"react", "javascript", "typescript", "html", "css"} & skills:
        roles.append("Frontend Developer")
    if {"machine learning", "ai", "pandas", "numpy", "tensorflow", "pytorch"} & skills:
        roles.append("AI/ML Engineer")
    if {"docker", "kubernetes", "aws", "azure", "gcp", "ci/cd"} & skills:
        roles.append("DevOps Engineer")
    if not roles:
        roles.append("Software Engineer")
    return unique_list(roles)[:5]


def infer_industry(jd_skills, jd_keywords):
    terms = {term.lower() for term in jd_skills + jd_keywords}
    if {"machine learning", "ai", "model", "data"} & terms:
        return "AI/Data technology roles"
    if {"aws", "docker", "kubernetes", "ci/cd"} & terms:
        return "Cloud and platform engineering roles"
    if {"react", "frontend", "ui"} & terms:
        return "Web product engineering roles"
    return "General software engineering roles"


def project_analysis(profile, missing):
    if not profile["section_presence"].get("projects"):
        return "Projects are missing or not clearly labelled. Add 2-3 role-specific projects with stack, GitHub/live links, and measurable outcomes."
    return f"Projects are present. Strengthen them by adding impact metrics and evidence for {', '.join(missing[:4]) or 'JD keywords'}."


def experience_analysis(profile):
    if not profile["section_presence"].get("experience"):
        return "Experience section is weak or missing. Add internships, freelance work, academic projects, or responsibility-led bullets."
    return "Experience section is present. Improve it with quantified outcomes, clearer ownership, action verbs, and JD-aligned keywords."


def strong_sections(breakdown):
    return [section for section, score in breakdown.items() if score >= 75]


def weak_sections(breakdown):
    return [section for section, score in breakdown.items() if score < 60]


def internship_score(profile, resume_skills):
    score = 35
    if profile["section_presence"].get("projects"):
        score += 25
    if profile["section_presence"].get("skills"):
        score += 15
    if profile["section_presence"].get("education"):
        score += 10
    score += min(15, len(resume_skills))
    return score_value(score, 50)


def heat_status(score):
    if score >= 75:
        return "strong"
    if score >= 55:
        return "average"
    return "weak"


def score_value(value, fallback):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return max(0, min(100, int(fallback)))


def unique_list(items):
    seen = set()
    output = []
    for item in items or []:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def build_improved_resume_text(resume_text, jd_text, result):
    profile = parse_resume_profile(resume_text)
    metadata = profile["metadata"]
    improved = result.get("improved_resume", {})
    name = metadata.get("name") or "Candidate Name"
    contact = " | ".join(item for item in [metadata.get("email"), metadata.get("phone")] if item)

    lines = [
        name,
        contact or "Email | Phone | LinkedIn | GitHub",
        "",
        "PROFESSIONAL SUMMARY",
        improved.get("summary") or result.get("summary_improvement") or result.get("summary", ""),
        "",
        "SKILLS",
    ]
    lines.extend(as_lines(improved.get("skills_section"), "Technical Skills: Add role-relevant tools and platforms."))
    lines.extend(["", "EXPERIENCE"])
    lines.extend(as_bullets(improved.get("experience_bullets"), result.get("experience_analysis", [])))
    lines.extend(["", "PROJECTS"])
    lines.extend(as_bullets(improved.get("project_bullets"), result.get("project_suggestions", [])))
    lines.extend(["", "KEYWORD PRIORITIES"])
    lines.extend(as_bullets(result.get("missing_skills", []), []))
    return "\n".join(lines)


def as_lines(value, fallback):
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return [fallback]


def as_bullets(value, fallback):
    items = value if isinstance(value, list) and value else fallback
    if isinstance(items, str):
        items = [items]
    return [f"- {item}" for item in items[:8]] if items else ["- Add a quantified, job-specific bullet here."]
