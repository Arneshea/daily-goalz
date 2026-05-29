// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(url, opts = {}) {
    const res = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
    });
    const data = await res.json();
    if (!res.ok) throw { status: res.status, data };
    return data;
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg, duration = 2500) {
    let el = document.getElementById("toast");
    if (!el) {
        el = document.createElement("div");
        el.id = "toast";
        document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("show"), duration);
}

// ── Date helpers ──────────────────────────────────────────────────────────────

function daysInMonth(year, month) {
    return new Date(year, month, 0).getDate();   // month is 1-based here
}

function todayISO() {
    const d = new Date();
    return formatDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

function formatDate(year, month, day) {
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

const MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
];
const MONTH_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DAY_NAMES   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

// ── Theme switcher ────────────────────────────────────────────────────────────

const THEMES = {
    earthy:   { primary: "#8d4b00", secondary: "#3f6a00" },
    dark:     { primary: "#ffb77d", secondary: "#96d947" },
    ocean:    { primary: "#005f8c", secondary: "#007a5e" },
    lavender: { primary: "#6750a4", secondary: "#4a7c59" },
};

function applyTheme(name) {
    const root = document.documentElement;
    if (name === "dark") {
        root.classList.add("dark");
    } else {
        root.classList.remove("dark");
    }
    localStorage.setItem("dg_theme", name);
}

function initTheme() {
    applyTheme(localStorage.getItem("dg_theme") || "earthy");
}

document.addEventListener("DOMContentLoaded", () => {
    initTheme();

    // Palette button cycles themes
    document.querySelectorAll(".js-theme-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const themes = Object.keys(THEMES);
            const current = localStorage.getItem("dg_theme") || "earthy";
            const next = themes[(themes.indexOf(current) + 1) % themes.length];
            applyTheme(next);
            showToast(`Theme: ${next}`);
        });
    });

    // Logout
    document.querySelectorAll(".js-logout").forEach(btn => {
        btn.addEventListener("click", () => { window.location = "/logout"; });
    });
});

// ── Nav active state ──────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    const path = window.location.pathname.replace("/", "") || "monthly";
    document.querySelectorAll(".js-nav-link").forEach(link => {
        const page = link.dataset.page;
        if (page === path) {
            link.classList.add(
                "bg-secondary-container", "text-on-secondary-container",
                "border-2", "border-on-surface", "brutalist-shadow"
            );
            link.classList.remove("text-on-surface-variant", "hover:bg-surface-container-highest");
        }
    });
});
