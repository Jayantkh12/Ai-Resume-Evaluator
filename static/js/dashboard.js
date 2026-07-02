const dashboardData = window.dashboardData || {};
const scoreHistory = dashboardData.score_history || [];
const labels = scoreHistory.map((item) => item.label);
const scores = scoreHistory.map((item) => item.score);
const canvas = document.getElementById("scoreChart");
const fallback = document.getElementById("scoreFallback");

if (window.Chart && canvas && scores.length) {
    new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Resume Score",
                    data: scores,
                    tension: 0.35,
                    borderColor: "#2563eb",
                    backgroundColor: "rgba(37, 99, 235, 0.14)",
                    fill: true,
                    pointRadius: 4,
                    pointBackgroundColor: "#0f766e"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 180,
            animation: false,
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    ticks: { callback: (value) => `${value}%` }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `${context.parsed.y}%`
                    }
                }
            }
        }
    });
} else if (fallback) {
    if (canvas) {
        canvas.style.display = "none";
    }
    fallback.style.display = "flex";
    if (!scores.length) {
        fallback.innerHTML = '<p class="muted">No scores yet.</p>';
    } else {
        fallback.innerHTML = scores
            .map((score) => `<div class="fallback-bar" style="height:${Math.max(score, 8)}%">${score}%</div>`)
            .join("");
    }
}
