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
                    borderColor: "#6366f1",
                    backgroundColor: "rgba(99, 102, 241, 0.15)",
                    fill: true,
                    pointRadius: 5,
                    pointBackgroundColor: "#a855f7",
                    pointBorderColor: "#ffffff",
                    pointHoverRadius: 7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 180,
            animation: {
                duration: 800,
                easing: 'easeInOutQuart'
            },
            scales: {
                x: {
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)",
                        borderColor: "rgba(255, 255, 255, 0.1)"
                    },
                    ticks: {
                        color: "#9ca3af",
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif"
                        }
                    }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)",
                        borderColor: "rgba(255, 255, 255, 0.1)"
                    },
                    ticks: {
                        color: "#9ca3af",
                        font: {
                            family: "'Plus Jakarta Sans', sans-serif"
                        },
                        callback: (value) => `${value}%`
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "rgba(15, 23, 42, 0.95)",
                    titleColor: "#ffffff",
                    bodyColor: "#e5e7eb",
                    borderColor: "rgba(255, 255, 255, 0.1)",
                    borderWidth: 1,
                    titleFont: { family: "'Plus Jakarta Sans', sans-serif", weight: 'bold' },
                    bodyFont: { family: "'Plus Jakarta Sans', sans-serif" },
                    callbacks: {
                        label: (context) => `Score: ${context.parsed.y}%`
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
