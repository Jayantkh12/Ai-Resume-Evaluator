import re
import zipfile
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from PyPDF2 import PdfReader

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}

SKILL_CATEGORIES = OrderedDict(
    {
        "Programming Languages": [
            "python",
            "java",
            "javascript",
            "typescript",
            "c++",
            "c#",
            "go",
            "golang",
            "ruby",
            "php",
            "kotlin",
            "swift",
            "sql",
            "r",
            "bash",
            "shell scripting",
        ],
        "Frontend": [
            "react",
            "next.js",
            "nextjs",
            "vue",
            "angular",
            "html",
            "css",
            "tailwind",
            "bootstrap",
            "redux",
        ],
        "Backend": [
            "flask",
            "django",
            "fastapi",
            "node.js",
            "nodejs",
            "express",
            "spring",
            "rest api",
            "rest apis",
            "graphql",
            "microservices",
            "apis",
            "api development",
            "web services",
        ],
        "Databases": [
            "mysql",
            "postgresql",
            "postgres",
            "mongodb",
            "sqlite",
            "redis",
            "oracle",
            "firebase",
            "dynamodb",
        ],
        "Cloud & DevOps": [
            "aws",
            "azure",
            "gcp",
            "docker",
            "kubernetes",
            "jenkins",
            "github actions",
            "ci/cd",
            "terraform",
            "linux",
            "cloud deployment",
            "devops",
        ],
        "AI & Data": [
            "ai",
            "machine learning",
            "deep learning",
            "nlp",
            "llm",
            "generative ai",
            "openai",
            "gemini",
            "pandas",
            "numpy",
            "scikit-learn",
            "tensorflow",
            "pytorch",
            "power bi",
            "tableau",
            "excel",
            "data structures",
            "algorithms",
            "dsa",
        ],
        "Testing & Quality": [
            "pytest",
            "unit testing",
            "selenium",
            "playwright",
            "jest",
            "cypress",
            "postman",
        ],
        "Tools": [
            "git",
            "github",
            "jira",
            "figma",
            "notion",
            "agile",
            "scrum",
            "api",
            "vs code",
            "visual studio code",
        ],
        "Soft Skills": [
            "leadership",
            "communication",
            "teamwork",
            "collaboration",
            "problem solving",
            "ownership",
            "mentoring",
            "critical thinking",
            "adaptability",
            "time management",
        ],
    }
)

SECTION_ALIASES = {
    "summary": ["summary", "profile", "objective", "about"],
    "skills": ["skills", "technical skills", "core skills", "competencies"],
    "experience": ["experience", "work experience", "employment", "professional experience"],
    "projects": ["projects", "academic projects", "personal projects"],
    "education": ["education", "academics", "qualification"],
    "certifications": ["certifications", "certificates", "licenses"],
}


def extract_text_from_file(file_storage):
    filename = file_storage.filename or ""
    extension = Path(filename).suffix.lower().lstrip(".")
    data = file_storage.read()
    file_storage.stream.seek(0)

    if extension == "pdf":
        return extract_text_from_pdf(BytesIO(data))
    if extension == "docx":
        return extract_text_from_docx(BytesIO(data))
    if extension == "txt":
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported resume file type.")


def extract_text_from_pdf(stream):
    reader = PdfReader(stream)
    pages = [page.extract_text() or "" for page in reader.pages]
    return normalize_text("\n".join(pages))


def extract_text_from_docx(stream):
    text_parts = []
    with zipfile.ZipFile(stream) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for node in root.findall(".//w:t", namespace):
        if node.text:
            text_parts.append(node.text)
    return normalize_text("\n".join(text_parts))


def normalize_text(text):
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_resume_profile(text):
    clean_text = normalize_text(text)
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    metadata = {
        "name": infer_name(lines),
        "email": find_first(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean_text, re.I),
        "phone": find_first(r"(\+?\d[\d\s().-]{8,}\d)", clean_text),
        "links": sorted(set(re.findall(r"https?://\S+|linkedin\.com/\S+|github\.com/\S+", clean_text, re.I))),
    }
    skills = find_skills(clean_text)
    sections = extract_sections(clean_text)
    return {
        "metadata": metadata,
        "word_count": len(re.findall(r"\b[\w+#.-]+\b", clean_text)),
        "line_count": len(lines),
        "skills": skills,
        "sections": sections,
        "section_presence": {key: bool(value.strip()) for key, value in sections.items()},
        "bullet_count": len(re.findall(r"(^|\n)\s*[-*\u2022]", clean_text)),
    }


def infer_name(lines):
    for line in lines[:5]:
        candidate = re.sub(r"[^A-Za-z .'-]", "", line).strip()
        words = candidate.split()
        if 1 < len(words) <= 4 and all(len(word) > 1 for word in words):
            return candidate
    return ""


def find_first(pattern, text, flags=0):
    match = re.search(pattern, text, flags)
    return match.group(1 if match.lastindex else 0).strip() if match else ""


def find_skills(text):
    lowered = f" {text.lower()} "
    categories = OrderedDict((category, []) for category in SKILL_CATEGORIES)
    for category, skills in SKILL_CATEGORIES.items():
        for skill in skills:
            canonical = normalize_skill_name(skill)
            pattern = skill_pattern(skill)
            if re.search(pattern, lowered):
                if canonical not in categories[category]:
                    categories[category].append(canonical)
    return {category: values for category, values in categories.items() if values}


def flatten_skills(categorized_skills):
    skills = []
    for values in categorized_skills.values():
        skills.extend(values)
    return sorted(set(skills), key=str.lower)


def normalize_skill_name(skill):
    aliases = {
        "nextjs": "Next.js",
        "next.js": "Next.js",
        "nodejs": "Node.js",
        "node.js": "Node.js",
        "postgres": "PostgreSQL",
        "golang": "Go",
        "ci/cd": "CI/CD",
        "llm": "LLM",
        "nlp": "NLP",
        "aws": "AWS",
        "gcp": "GCP",
        "api": "API",
        "rest api": "REST API",
        "rest apis": "REST APIs",
        "apis": "APIs",
        "api development": "API Development",
        "c++": "C++",
        "c#": "C#",
        "dsa": "DSA",
        "ai": "AI",
    }
    return aliases.get(skill, skill.title())


def skill_pattern(skill):
    escaped = re.escape(skill.lower())
    if re.search(r"[^a-z0-9 ]", skill.lower()):
        return rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return rf"\b{escaped}\b"


def extract_sections(text):
    sections = OrderedDict((section, "") for section in SECTION_ALIASES)
    current_section = None
    buffer = []

    for line in text.splitlines():
        normalized = re.sub(r"[^a-z ]", "", line.lower()).strip()
        matched_section = find_section(normalized)
        if matched_section:
            if current_section:
                sections[current_section] = "\n".join(buffer).strip()
            current_section = matched_section
            buffer = []
            continue
        if current_section:
            buffer.append(line)

    if current_section:
        sections[current_section] = "\n".join(buffer).strip()
    return sections


def find_section(normalized_line):
    if not normalized_line or len(normalized_line.split()) > 4:
        return None
    for section, aliases in SECTION_ALIASES.items():
        if normalized_line in aliases:
            return section
    return None
