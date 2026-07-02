const form = document.getElementById("resume-form");
const fileInput = document.getElementById("resume-file");
const fileName = document.getElementById("file-name");
const dropzone = document.getElementById("dropzone");
const alertBox = document.getElementById("alert-box");
const analyzeBtn = document.getElementById("analyze-btn");
const buttonText = document.getElementById("button-text");
const placeholder = document.getElementById("placeholder");
const resultsArea = document.getElementById("results-area");

const scoreRing = document.getElementById("score-ring");
const scoreDisplay = document.getElementById("score-display");
const rankLabel = document.getElementById("rank-label");
const verdictText = document.getElementById("verdict-text");
const breakdown = document.getElementById("score-breakdown");
const downloadReport = document.getElementById("download-report");
const downloadImproved = document.getElementById("download-improved");
const analysisProvider = document.getElementById("analysis-provider");
const multiResultsCard = document.getElementById("multi-results-card");
const multiResultsCount = document.getElementById("multi-results-count");
const multiResultsList = document.getElementById("multi-results-list");

const missingList = document.getElementById("missing-keywords-list");
const strengthsList = document.getElementById("strengths-list");
const whatToAddList = document.getElementById("what-to-add-list");
const skillCategories = document.getElementById("skill-categories");
const companyFitList = document.getElementById("company-fit-list");
const projectList = document.getElementById("project-suggestions-list");
const atsFixesList = document.getElementById("ats-fixes-list");
const recommendedRoles = document.getElementById("recommended-roles");
const keywordOptimizationList = document.getElementById("keyword-optimization-list");
const projectAnalysisText = document.getElementById("project-analysis-text");
const experienceAnalysisText = document.getElementById("experience-analysis-text");
const summaryImprovementText = document.getElementById("summary-improvement-text");
const resumeHeatmap = document.getElementById("resume-heatmap");

if (fileInput) {
    fileInput.addEventListener("change", updateFileName);
}

if (dropzone) {
    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("is-dragging");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateFileName();
        }
    });
}

if (form) {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        hideAlert();

        const jdText = document.getElementById("job-description").value.trim();
        const files = Array.from(fileInput.files || []);
        const selectedSaved = Array.from(form.querySelectorAll('input[name="resume_ids"]:checked'));

        if (!jdText) {
            showAlert("Please paste the job description.");
            return;
        }
        if (!files.length && !selectedSaved.length) {
            showAlert("Please upload or select at least one resume.");
            return;
        }
        if (files.some((file) => !/\.(pdf|docx|txt)$/i.test(file.name))) {
            showAlert("Only PDF, DOCX, and TXT resumes are supported.");
            return;
        }

        const formData = new FormData(form);
        setLoading(true);

        try {
            const response = await fetch("/analyze", {
                method: "POST",
                body: formData
            });
            const data = await response.json();
            if (!response.ok || data.error) {
                throw new Error(data.error || "Unable to analyze this resume.");
            }
            if (Array.isArray(data.results)) {
                displayResults(data.results[0]);
                renderMultiResults(data.results, data.errors || []);
            } else {
                displayResults(data);
                renderMultiResults([data], []);
            }
        } catch (error) {
            showAlert(error.message || "Unexpected error while analyzing.");
        } finally {
            setLoading(false);
        }
    });
}

if (window.initialReport) {
    displayResults(window.initialReport);
}

function updateFileName() {
    const files = Array.from(fileInput.files || []);
    if (!files.length) {
        fileName.textContent = "Choose resumes";
    } else if (files.length === 1) {
        fileName.textContent = files[0].name;
    } else {
        fileName.textContent = `${files.length} resumes selected`;
    }
}

function setLoading(isLoading) {
    analyzeBtn.disabled = isLoading;
    analyzeBtn.classList.toggle("loading", isLoading);
    buttonText.textContent = isLoading ? "Analyzing..." : "Analyze Resume";
}

function showAlert(message) {
    alertBox.textContent = message;
    alertBox.classList.add("show");
}

function hideAlert() {
    alertBox.textContent = "";
    alertBox.classList.remove("show");
}

function displayResults(data) {
    const score = clamp(Number(data.jd_match_score || data.match_percentage) || 0, 0, 100);
    const scoreColor = getScoreColor(score);

    placeholder.style.display = "none";
    resultsArea.classList.add("show");
    scoreDisplay.textContent = `${score}%`;
    scoreRing.style.setProperty("--score-color", scoreColor);
    scoreRing.style.background = `conic-gradient(${scoreColor} ${score * 3.6}deg, #e5e7eb 0deg)`;

    rankLabel.textContent = data.rank_label || "Rank";
    verdictText.textContent = data.summary || data.final_verdict || "No verdict returned.";
    analysisProvider.textContent = buildProviderText(data);

    renderBreakdown(buildScoreBreakdown(data));
    renderList(missingList, normalizeList(data.missing_skills), "No new technical skill/language is missing. Improve JD evidence and keywords below.");
    renderList(strengthsList, normalizeList(data.strengths), "No strengths returned.");
    renderList(
        whatToAddList,
        normalizeList(data.recommended_skills).concat(normalizeList(data.ai_recommendations)).slice(0, 10),
        "No additions returned."
    );
    renderSkillCategories(data.skill_categories || {});
    renderCompanyFit(data.target_company_fit || []);
    renderList(projectList, normalizeList(data.project_suggestions), "No project suggestions returned.");
    renderList(
        atsFixesList,
        normalizeList(data.ats_improvements).concat(normalizeList(data.grammar_issues || data.grammar_fixes)),
        "No ATS or grammar fixes returned."
    );
    renderTags(recommendedRoles, normalizeList(data.recommended_job_roles), "No roles returned.");
    renderList(keywordOptimizationList, normalizeList(data.keyword_optimization), "No keyword optimization returned.");
    projectAnalysisText.textContent = data.projects_analysis || "No project analysis returned.";
    experienceAnalysisText.textContent = data.experience_analysis || "No experience analysis returned.";
    summaryImprovementText.textContent = data.summary_improvement || "No summary rewrite suggestion returned.";
    renderHeatmap(data.resume_heatmap || []);

    setLink(downloadReport, data.download_url);
    setLink(downloadImproved, data.improved_resume_url);
}

function buildProviderText(data) {
    const provider = data.analysis_provider || "unknown";
    const model = data.analysis_model ? ` - ${data.analysis_model}` : "";
    const warning = data.analysis_warning ? ` - ${data.analysis_warning}` : "";
    return `Analysis: ${provider}${model}${warning}`;
}

function buildScoreBreakdown(data) {
    return {
        "Resume Score": data.resume_score,
        "ATS Score": data.ats_score,
        "JD Match": data.jd_match_score || data.match_percentage,
        "Recommendation": data.recommendation_score,
        ...(data.score_breakdown || {})
    };
}

function renderMultiResults(results, errors) {
    if (!multiResultsCard || !multiResultsList) return;
    const allItems = [
        ...results.map((result) => ({ type: "result", ...result })),
        ...errors.map((error) => ({ type: "error", ...error }))
    ];
    if (allItems.length <= 1) {
        multiResultsCard.hidden = true;
        return;
    }
    multiResultsCard.hidden = false;
    multiResultsCount.textContent = `${allItems.length} files`;
    multiResultsList.innerHTML = "";
    allItems.forEach((item) => {
        const row = document.createElement(item.report_url ? "a" : "div");
        row.className = "report-row";
        if (item.report_url) {
            row.href = item.report_url;
        }
        const score = item.type === "error" ? "Error" : `${clamp(Number(item.match_percentage) || 0, 0, 100)}%`;
        const status = item.type === "error" ? item.error : item.rank_label;
        row.innerHTML = `
            <span>
                <strong>${escapeHtml(item.resume_name || "Resume")}</strong>
                <small>${escapeHtml(status || "Analyzed")}</small>
            </span>
            <span class="mini-score">${escapeHtml(score)}</span>
        `;
        multiResultsList.appendChild(row);
    });
}

function renderBreakdown(items) {
    breakdown.innerHTML = "";
    Object.entries(items).forEach(([label, value]) => {
        const score = clamp(Number(value) || 0, 0, 100);
        const card = document.createElement("div");
        card.className = "metric-card";
        card.innerHTML = `
            <span>${escapeHtml(label)}</span>
            <strong>${score}%</strong>
            <div class="metric-progress"><span style="width:${score}%"></span></div>
        `;
        breakdown.appendChild(card);
    });
}

function renderSkillCategories(categories) {
    skillCategories.innerHTML = "";
    const entries = Object.entries(categories).filter(([, values]) => Array.isArray(values) && values.length);
    if (!entries.length) {
        skillCategories.innerHTML = '<p class="muted">No skills detected.</p>';
        return;
    }
    entries.forEach(([category, values]) => {
        const group = document.createElement("div");
        group.className = "tag-group";
        group.innerHTML = `<strong>${escapeHtml(category)}</strong>`;
        values.forEach((skill) => {
            const tag = document.createElement("span");
            tag.textContent = skill;
            group.appendChild(tag);
        });
        skillCategories.appendChild(group);
    });
}

function renderCompanyFit(items) {
    companyFitList.innerHTML = "";
    const fitItems = Array.isArray(items) ? items : [];
    if (!fitItems.length) {
        renderList(companyFitList, [], "No company advice returned.");
        return;
    }
    fitItems.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = `${item.company || "Company"}: ${item.advice || ""}`;
        companyFitList.appendChild(li);
    });
}

function renderTags(element, items, emptyText) {
    element.innerHTML = "";
    const finalItems = items.length ? items : [emptyText];
    finalItems.forEach((item) => {
        const tag = document.createElement("span");
        tag.textContent = item;
        element.appendChild(tag);
    });
}

function renderHeatmap(items) {
    resumeHeatmap.innerHTML = "";
    if (!Array.isArray(items) || !items.length) {
        resumeHeatmap.innerHTML = '<p class="muted">No heatmap returned.</p>';
        return;
    }
    items.forEach((item) => {
        const score = clamp(Number(item.score) || 0, 0, 100);
        const row = document.createElement("div");
        row.className = `heatmap-row ${item.status || getHeatStatus(score)}`;
        row.innerHTML = `
            <div>
                <strong>${escapeHtml(item.section || "Section")}</strong>
                <small>${escapeHtml(item.feedback || "")}</small>
            </div>
            <span>${score}%</span>
        `;
        resumeHeatmap.appendChild(row);
    });
}

function getHeatStatus(score) {
    if (score >= 75) return "strong";
    if (score >= 55) return "average";
    return "weak";
}

function renderList(element, items, emptyText) {
    element.innerHTML = "";
    const finalItems = items.length ? items : [emptyText];
    finalItems.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        element.appendChild(li);
    });
}

function normalizeList(value) {
    return Array.isArray(value)
        ? value.filter((item) => String(item).trim()).map((item) => String(item).trim())
        : [];
}

function setLink(element, href) {
    if (!href) {
        element.hidden = true;
        return;
    }
    element.href = href;
    element.hidden = false;
}

function getScoreColor(score) {
    if (score >= 75) return "#10b981";
    if (score >= 50) return "#f59e0b";
    return "#ef4444";
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
