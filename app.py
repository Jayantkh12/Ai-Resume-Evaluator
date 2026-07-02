import json
import os
import sqlite3
import uuid
from collections import Counter
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from flask_login import (
        LoginManager,
        UserMixin,
        current_user as flask_current_user,
        login_user as flask_login_user,
        logout_user as flask_logout_user,
    )
except ImportError:  # pragma: no cover - optional until requirements are installed
    LoginManager = None
    UserMixin = object
    flask_current_user = None
    flask_login_user = None
    flask_logout_user = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in local development
    load_dotenv = None

from utils.ai_analysis import analyze_resume, build_improved_resume_text
from utils.ats import rank_label, score_resume
from utils.jd_match import extract_job_trends
from utils.parser import ALLOWED_EXTENSIONS, extract_text_from_file
from utils.pdf_generator import create_text_pdf
from utils.skill_filter import filter_keyword_terms, filter_skill_terms

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-resume-evaluator-secret")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

login_manager = LoginManager() if LoginManager else None
if login_manager:
    login_manager.login_view = "login"
    login_manager.init_app(app)


class AuthUser(UserMixin):
    def __init__(self, row):
        self.row = dict(row)
        self.id = str(row["id"])

    @property
    def name(self):
        return self.row.get("name", "")

    @property
    def email(self):
        return self.row.get("email", "")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


if login_manager:
    @login_manager.user_loader
    def load_user(user_id):
        row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return AuthUser(row) if row else None


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resume_name TEXT NOT NULL,
                resume_path TEXT,
                file_type TEXT,
                resume_text TEXT NOT NULL,
                latest_score INTEGER,
                status TEXT NOT NULL,
                latest_report_id INTEGER,
                uploaded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS resume_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                resume_id INTEGER,
                resume_name TEXT NOT NULL,
                resume_path TEXT,
                jd_text TEXT NOT NULL,
                target_companies TEXT,
                resume_text TEXT NOT NULL,
                result_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                rank_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        ensure_column(db, "resume_reports", "resume_id", "INTEGER")
        migrate_existing_reports_to_resumes(db)
        db.commit()


def ensure_column(db, table_name, column_name, column_type):
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def migrate_existing_reports_to_resumes(db):
    rows = db.execute(
        """
        SELECT * FROM resume_reports
        WHERE resume_id IS NULL
        ORDER BY datetime(created_at) ASC, id ASC
        """
    ).fetchall()
    for row in rows:
        cursor = db.execute(
            """
            INSERT INTO resumes (
                user_id, resume_name, resume_path, file_type, resume_text,
                latest_score, status, latest_report_id, uploaded_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["user_id"],
                row["resume_name"],
                row["resume_path"],
                infer_file_type(row["resume_name"], row["resume_path"]),
                row["resume_text"],
                row["score"],
                "Analyzed",
                row["id"],
                row["created_at"],
                row["created_at"],
            ),
        )
        resume_id = cursor.lastrowid
        db.execute("UPDATE resume_reports SET resume_id = ? WHERE id = ?", (resume_id, row["id"]))


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        flask_logged_in = bool(
            flask_current_user
            and getattr(flask_current_user, "is_authenticated", False)
        )
        if not session.get("user_id") and not flask_logged_in:
            flash("Please login or create an account to continue.", "warning")
            return redirect(url_for("login"))
        if flask_logged_in and not session.get("user_id"):
            session["user_id"] = int(flask_current_user.id)
        return view(*args, **kwargs)

    return wrapped_view


def current_user():
    if flask_current_user and getattr(flask_current_user, "is_authenticated", False):
        return flask_current_user.row
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def split_target_companies(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def infer_file_type(resume_name, resume_path=None):
    source = resume_name or resume_path or ""
    extension = Path(source).suffix.lower().lstrip(".")
    return extension or "txt"


def get_resume_files(field_name="resumes"):
    files = [file for file in request.files.getlist(field_name) if file and file.filename]
    if not files and request.files.get("resume"):
        files = [request.files["resume"]]
    return files


def save_resume_upload(user_id, resume_file):
    original_name = secure_filename(resume_file.filename or "resume")
    extension = original_name.rsplit(".", 1)[1].lower() if "." in original_name else "txt"
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    stored_path = UPLOAD_DIR / stored_name

    if not allowed_file(original_name):
        raise ValueError("Upload a PDF, DOCX, or TXT resume.")

    resume_text = extract_text_from_file(resume_file)
    if len(resume_text.strip()) < 80:
        raise ValueError(f"Could not read enough text from {resume_file.filename}.")

    resume_file.stream.seek(0)
    resume_file.save(stored_path)

    timestamp = now_iso()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO resumes (
            user_id, resume_name, resume_path, file_type, resume_text,
            latest_score, status, latest_report_id, uploaded_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            resume_file.filename or original_name,
            str(stored_path.relative_to(BASE_DIR)),
            extension,
            resume_text,
            None,
            "Uploaded",
            None,
            timestamp,
            timestamp,
        ),
    )
    db.commit()
    return get_resume(cursor.lastrowid, user_id)


def save_report(user_id, resume, jd_text, target_companies, result):
    timestamp = now_iso()
    report_score = int(result.get("recommendation_score", result.get("match_percentage", 0)))
    resume_score = int(result.get("resume_score", report_score))
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO resume_reports (
            user_id, resume_id, resume_name, resume_path, jd_text, target_companies,
            resume_text, result_json, score, rank_label, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            resume["id"],
            resume["resume_name"],
            resume["resume_path"],
            jd_text,
            ", ".join(target_companies),
            resume["resume_text"],
            json.dumps(result),
            report_score,
            result.get("rank_label", "Weak"),
            timestamp,
        ),
    )
    report_id = cursor.lastrowid
    db.execute(
        """
        UPDATE resumes
        SET latest_score = ?, status = ?, latest_report_id = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            resume_score,
            result.get("rank_label", "Analyzed"),
            report_id,
            timestamp,
            resume["id"],
            user_id,
        ),
    )
    db.commit()
    return report_id


def get_user_resumes(user_id, limit=None):
    sql = """
        SELECT * FROM resumes
        WHERE user_id = ?
        ORDER BY datetime(uploaded_at) DESC, id DESC
    """
    params = [user_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = get_db().execute(sql, params).fetchall()
    return [hydrate_resume(row) for row in rows]


def get_resume(resume_id, user_id):
    row = get_db().execute(
        "SELECT * FROM resumes WHERE id = ? AND user_id = ?",
        (resume_id, user_id),
    ).fetchone()
    return hydrate_resume(row) if row else None


def hydrate_resume(row):
    if row is None:
        return None
    resume = dict(row)
    resume["uploaded_label"] = resume["uploaded_at"].replace("T", " ")
    resume["updated_label"] = resume["updated_at"].replace("T", " ")
    if resume.get("latest_report_id"):
        report_row = get_db().execute(
            "SELECT * FROM resume_reports WHERE id = ? AND user_id = ?",
            (resume["latest_report_id"], resume["user_id"]),
        ).fetchone()
        if report_row:
            report_result = clean_report_result(
                json.loads(report_row["result_json"] or "{}"),
                report_row["resume_text"],
                report_row["jd_text"],
            )
            resume["latest_score"] = int(
                report_result.get(
                    "resume_score",
                    report_result.get("recommendation_score", resume.get("latest_score") or 0),
                )
                or 0
            )
    resume["score_label"] = f"{resume['latest_score']}%" if resume.get("latest_score") is not None else "Pending"
    resume["report_url"] = (
        url_for("home", report_id=resume["latest_report_id"])
        if resume.get("latest_report_id")
        else ""
    )
    return resume


def get_user_reports(user_id, limit=None):
    sql = """
        SELECT * FROM resume_reports
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
    """
    params = [user_id]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    rows = get_db().execute(sql, params).fetchall()
    return [hydrate_report(row) for row in rows]


def get_report(report_id, user_id):
    row = get_db().execute(
        "SELECT * FROM resume_reports WHERE id = ? AND user_id = ?",
        (report_id, user_id),
    ).fetchone()
    return hydrate_report(row) if row else None


def hydrate_report(row):
    if row is None:
        return None
    report = dict(row)
    report["result"] = json.loads(report["result_json"] or "{}")
    report["result"] = clean_report_result(report["result"], report.get("resume_text"), report.get("jd_text"))
    report["score"] = int(
        report["result"].get(
            "recommendation_score",
            report["result"].get("jd_match_score", report.get("score", 0)),
        )
        or 0
    )
    report["rank_label"] = report["result"].get("rank_label", report.get("rank_label", "Weak Match"))
    report["target_company_list"] = split_target_companies(report.get("target_companies"))
    report["created_label"] = report["created_at"].replace("T", " ")
    return report


def clean_report_result(result, resume_text=None, jd_text=None):
    if not isinstance(result, dict):
        return {}
    if "missing_skills" in result:
        result["missing_skills"] = filter_skill_terms(result.get("missing_skills", []))
    if "missing_keywords" in result:
        result["missing_keywords"] = filter_keyword_terms(result.get("missing_keywords", []))
    if "recommended_skills" in result:
        result["recommended_skills"] = filter_skill_terms(result.get("recommended_skills", []))
    if "important_missing_technologies" in result:
        result["important_missing_technologies"] = filter_skill_terms(
            result.get("important_missing_technologies", [])
        )
    if should_recalibrate_result(result) and resume_text and jd_text:
        local = score_resume(resume_text, jd_text)
        corrected_score = int(local["match"].get("keyword_match_score", 0))
        result["jd_match_score"] = corrected_score
        result["match_percentage"] = corrected_score
        result["rank_label"] = rank_label(corrected_score)
        result["missing_skills"] = filter_skill_terms(local["match"].get("missing_skills", []))
        result["missing_keywords"] = filter_keyword_terms(local["match"].get("missing_keywords", []))
        result["summary"] = (
            f"Resume quality is {result.get('resume_score', local['match_percentage'])}%, "
            f"ATS compatibility is {result.get('ats_score', local['score_breakdown']['Formatting'])}%, "
            f"and JD match is {corrected_score}%. "
            "If no new technical skill is missing, improve the score by adding clearer JD keywords, "
            "project proof, and measurable experience bullets."
        )
    return result


def should_recalibrate_result(result):
    score = int(result.get("jd_match_score", result.get("match_percentage", 0)) or 0)
    has_quality = int(result.get("resume_score", 0) or 0) > 0 or int(result.get("ats_score", 0) or 0) > 0
    no_missing_skills = not result.get("missing_skills")
    return score == 0 and has_quality and no_missing_skills


def build_dashboard_data(reports, resumes=None):
    resumes = resumes or []
    chronological = list(reversed(reports[-12:])) if len(reports) > 12 else list(reversed(reports))
    score_history = [
        {
            "label": report["created_at"][:10],
            "score": report["score"],
            "resume": report["resume_name"],
        }
        for report in chronological
    ]

    missing_counter = Counter()
    trend_counter = Counter()
    for report in reports:
        result = report["result"]
        missing_counter.update(result.get("missing_keywords", []))
        trend_counter.update(extract_job_trends(report["jd_text"]))

    return {
        "score_history": score_history,
        "top_missing_skills": missing_counter.most_common(8),
        "job_trends": trend_counter.most_common(8),
        "average_score": round(sum(r["score"] for r in reports) / len(reports), 1) if reports else 0,
        "best_score": max((r["score"] for r in reports), default=0),
        "total_reports": len(reports),
        "total_resumes": len(resumes),
    }


def report_to_text(report, improved=False):
    result = report["result"]
    if improved:
        return build_improved_resume_text(report["resume_text"], report["jd_text"], result)

    breakdown = result.get("score_breakdown", {})
    lines = [
        "Professional AI Resume Analysis Report",
        f"Resume: {report['resume_name']}",
        f"Resume Score: {result.get('resume_score', report['score'])}%",
        f"ATS Score: {result.get('ats_score', report['score'])}%",
        f"JD Match Score: {result.get('jd_match_score', result.get('match_percentage', report['score']))}%",
        f"Recommendation Score: {result.get('recommendation_score', report['score'])}%",
        f"Rank: {result.get('rank_label', report['rank_label'])}",
        f"AI Provider: {result.get('analysis_provider', 'unknown')} {result.get('analysis_model', '')}".strip(),
        "",
        "Executive Summary",
        result.get("summary") or result.get("final_verdict") or "No summary available.",
        "",
        "Score Breakdown",
    ]
    for section, score in breakdown.items():
        lines.append(f"- {section}: {score}")
    lines.extend(["", "Extracted Technical Skills"])
    lines.extend(f"- {item}" for item in result.get("technical_skills", []))
    lines.extend(["", "Extracted Soft Skills"])
    lines.extend(f"- {item}" for item in result.get("soft_skills", []))
    lines.extend(["", "Missing Important Skills"])
    lines.extend(f"- {item}" for item in result.get("missing_skills", result.get("missing_keywords", [])))
    lines.extend(["", "Recommended Skills To Add"])
    lines.extend(f"- {item}" for item in result.get("recommended_skills", []))
    lines.extend(["", "Strong Sections"])
    lines.extend(f"- {item}" for item in result.get("strong_sections", []))
    lines.extend(["", "Weak Sections"])
    lines.extend(f"- {item}" for item in result.get("weak_sections", []))
    lines.extend(["", "Project Analysis", result.get("projects_analysis", "")])
    lines.extend(["", "Experience Analysis", result.get("experience_analysis", "")])
    lines.extend(["", "Grammar Improvements"])
    lines.extend(f"- {item}" for item in result.get("grammar_issues", result.get("grammar_fixes", [])))
    lines.extend(["", "Summary Improvement", result.get("summary_improvement", "")])
    lines.extend(["", "Industry Match", result.get("industry_match", "")])
    lines.extend(["", "Recommended Job Roles"])
    lines.extend(f"- {item}" for item in result.get("recommended_job_roles", []))
    lines.extend(["", "Keyword Optimization"])
    lines.extend(f"- {item}" for item in result.get("keyword_optimization", []))
    lines.extend(["", "ATS Improvements"])
    lines.extend(f"- {item}" for item in result.get("ats_improvements", []))
    lines.extend(["", "Project Suggestions"])
    lines.extend(f"- {item}" for item in result.get("project_suggestions", []))
    lines.extend(["", "AI Recommendations"])
    lines.extend(f"- {item}" for item in result.get("ai_recommendations", []))
    return "\n".join(lines)


@app.route("/")
@login_required
def home():
    reports = get_user_reports(session["user_id"], limit=5)
    resumes = get_user_resumes(session["user_id"], limit=5)
    selected_report = None
    report_id = request.args.get("report_id")
    if report_id:
        selected_report = get_report(report_id, session["user_id"])
    return render_template("index.html", reports=reports, resumes=resumes, selected_report=selected_report)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        form_type = request.form.get("form_type", "login")
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("login"))

        db = get_db()
        if form_type == "signup":
            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return redirect(url_for("login") + "#signup-form")
            name = (request.form.get("name") or email.split("@")[0]).strip()
            exists = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                flash("Account already exists. Please login.", "warning")
                return redirect(url_for("login") + "#login-form")
            db.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), now_iso()),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            session["user_id"] = user["id"]
            if flask_login_user:
                flask_login_user(AuthUser(user))
            flash("Account created. Welcome to your resume workspace.", "success")
            return redirect(url_for("home"))

        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        if flask_login_user:
            flask_login_user(AuthUser(user))
        flash("Logged in successfully.", "success")
        return redirect(url_for("home"))

    reports = get_user_reports(session["user_id"], limit=6) if session.get("user_id") else []
    return render_template("login.html", reports=reports)


@app.route("/logout")
def logout():
    if flask_logout_user:
        flask_logout_user()
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    try:
        job_description = (request.form.get("jd") or "").strip()
        target_companies = split_target_companies(request.form.get("target_companies"))
        resume_files = get_resume_files()
        selected_resume_ids = [int(value) for value in request.form.getlist("resume_ids") if value.isdigit()]

        if not job_description or (not resume_files and not selected_resume_ids):
            return jsonify({"error": "Add a job description and at least one resume."}), 400

        resumes = []
        errors = []
        for resume_id in selected_resume_ids:
            resume = get_resume(resume_id, session["user_id"])
            if resume:
                resumes.append(resume)

        for resume_file in resume_files:
            try:
                resumes.append(save_resume_upload(session["user_id"], resume_file))
            except Exception as exc:
                errors.append({"resume_name": resume_file.filename, "error": str(exc)})

        results = []
        for resume in resumes:
            try:
                result = analyze_resume(resume["resume_text"], job_description, target_companies)
                report_id = save_report(session["user_id"], resume, job_description, target_companies, result)
                result["report_id"] = report_id
                result["resume_id"] = resume["id"]
                result["resume_name"] = resume["resume_name"]
                result["report_url"] = url_for("home", report_id=report_id)
                result["download_url"] = url_for("download_report", report_id=report_id)
                result["improved_resume_url"] = url_for("download_improved_resume", report_id=report_id)
                results.append(result)
            except Exception as exc:
                errors.append({"resume_name": resume["resume_name"], "error": str(exc)})

        if not results:
            return jsonify({"error": errors[0]["error"] if errors else "No resumes could be analyzed.", "errors": errors}), 400
        if len(results) == 1 and not errors:
            return jsonify(results[0])
        return jsonify({"results": results, "errors": errors})
    except Exception as exc:
        app.logger.exception("Resume analysis failed")
        return jsonify({"error": f"Internal error: {exc}"}), 500


@app.route("/resumes/upload", methods=["POST"])
@login_required
def upload_resumes():
    resume_files = get_resume_files()
    if not resume_files:
        flash("Choose at least one resume to upload.", "error")
        return redirect(url_for("dashboard"))

    saved_count = 0
    errors = []
    for resume_file in resume_files:
        try:
            save_resume_upload(session["user_id"], resume_file)
            saved_count += 1
        except Exception as exc:
            errors.append(f"{resume_file.filename}: {exc}")

    if saved_count:
        flash(f"Uploaded {saved_count} resume{'s' if saved_count != 1 else ''}.", "success")
    if errors:
        flash("Some files were skipped: " + "; ".join(errors[:3]), "error")
    return redirect(url_for("dashboard"))


@app.route("/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete_resume(resume_id):
    resume = get_resume(resume_id, session["user_id"])
    if not resume:
        flash("Resume not found.", "error")
        return redirect(url_for("dashboard"))

    path = (BASE_DIR / resume["resume_path"]).resolve() if resume.get("resume_path") else None
    if path and BASE_DIR.resolve() in path.parents and path.exists():
        path.unlink()

    db = get_db()
    db.execute("DELETE FROM resume_reports WHERE resume_id = ? AND user_id = ?", (resume_id, session["user_id"]))
    db.execute("DELETE FROM resumes WHERE id = ? AND user_id = ?", (resume_id, session["user_id"]))
    db.commit()
    flash("Resume deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    reports = get_user_reports(session["user_id"])
    resumes = get_user_resumes(session["user_id"])
    dashboard_data = build_dashboard_data(reports, resumes)
    return render_template("dashboard.html", reports=reports, resumes=resumes, dashboard_data=dashboard_data)


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    results = []
    resumes = get_user_resumes(session["user_id"])
    selected_ids = [int(value) for value in request.values.getlist("resume_ids") if value.isdigit()]
    if request.method == "POST":
        job_description = (request.form.get("jd") or "").strip()
        target_companies = split_target_companies(request.form.get("target_companies"))
        resume_files = get_resume_files()
        selected_resumes = [get_resume(resume_id, session["user_id"]) for resume_id in selected_ids]
        selected_resumes = [resume for resume in selected_resumes if resume]

        if not job_description or (not resume_files and not selected_resumes):
            flash("Add a job description and at least one resume.", "error")
            return render_template("compare.html", results=results, resumes=resumes, selected_ids=selected_ids)

        analysis_resumes = selected_resumes[:]
        for resume_file in resume_files:
            try:
                analysis_resumes.append(save_resume_upload(session["user_id"], resume_file))
            except Exception as exc:
                results.append({"resume_name": resume_file.filename, "error": str(exc)})

        for resume in analysis_resumes:
            try:
                result = analyze_resume(resume["resume_text"], job_description, target_companies)
                report_id = save_report(session["user_id"], resume, job_description, target_companies, result)
                result["report_id"] = report_id
                result["resume_id"] = resume["id"]
                result["resume_name"] = resume["resume_name"]
                results.append(result)
            except Exception as exc:
                results.append({"resume_name": resume["resume_name"], "error": str(exc)})

        results.sort(key=lambda item: item.get("match_percentage", -1), reverse=True)
    return render_template("compare.html", results=results, resumes=resumes, selected_ids=selected_ids)


@app.route("/reports/<int:report_id>/download")
@login_required
def download_report(report_id):
    report = get_report(report_id, session["user_id"])
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("dashboard"))

    pdf = create_text_pdf("Resume Analysis Report", report_to_text(report))
    filename = f"resume-report-{report_id}.pdf"
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/reports/<int:report_id>/improved-resume.pdf")
@login_required
def download_improved_resume(report_id):
    report = get_report(report_id, session["user_id"])
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("dashboard"))

    pdf = create_text_pdf("ATS Optimized Resume", report_to_text(report, improved=True))
    filename = f"improved-resume-{report_id}.pdf"
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


init_db()


if __name__ == "__main__":
    print("Starting Flask Server...")
    app.run(debug=True)
