const modeForms = {
    login: document.getElementById("login-form"),
    signup: document.getElementById("signup-form")
};

const authStage = document.querySelector(".auth-stage");
const heroModes = Array.from(document.querySelectorAll("[data-auth-hero]"));
const navLinks = Array.from(document.querySelectorAll(".auth-side-nav a"));
const switchLinks = Array.from(document.querySelectorAll("[data-auth-switch]"));

function setAuthMode(mode) {
    const nextMode = mode === "signup" ? "signup" : "login";
    if (authStage) {
        authStage.classList.toggle("signup-mode", nextMode === "signup");
    }
    Object.entries(modeForms).forEach(([key, form]) => {
        if (form) {
            form.classList.toggle("active", key === nextMode);
        }
    });
    heroModes.forEach((hero) => {
        hero.classList.toggle("active", hero.dataset.authHero === nextMode);
    });
    navLinks.forEach((link) => {
        const isSignup = link.getAttribute("href") === "#signup-form";
        link.classList.toggle("active", nextMode === (isSignup ? "signup" : "login"));
    });
}

navLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
        event.preventDefault();
        setAuthMode(link.getAttribute("href") === "#signup-form" ? "signup" : "login");
    });
});

switchLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
        event.preventDefault();
        setAuthMode(link.dataset.authSwitch);
    });
});

document.querySelectorAll("[data-toggle-password]").forEach((button) => {
    button.addEventListener("click", () => {
        const input = document.getElementById(button.dataset.togglePassword);
        if (!input) return;
        const visible = input.type === "text";
        input.type = visible ? "password" : "text";
        button.setAttribute("aria-label", visible ? "Show password" : "Hide password");
    });
});

if (window.location.hash === "#signup-form") {
    setAuthMode("signup");
}
