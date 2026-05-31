/* ============================================================
   app.js
   ------------------------------------------------------------
   Shared JavaScript used across every page (login, register,
   dashboard, profile). Keep this file SMALL and SIMPLE.
   ============================================================ */
var API_BASE_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "";
/* ---------- LOGIN FORM ---------- */
const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async function (e) {        
                                                                  //  # change fuction to async function
    
    e.preventDefault();

    const email    = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    // Very basic UI-only validation
    if (!email || !password) {
      alert("Please fill in both email and password.");
      return;
    }

    // TODO: connect to backend authentication API
    // Example (when backend is ready):
    //   fetch("http://localhost:8000/api/login", {
    //     method: "POST",
    //     headers: { "Content-Type": "application/json" },
    //     body: JSON.stringify({ email, password })
    //   })
    //     .then(r => r.json())
    //     .then(data => { localStorage.setItem("token", data.token); ... })

    // For now, just go to the dashboard.


    
    // window.location.href = "dashboard.html";  استبدلت السطر ده  بالاسطر الجاية 

    try {
  const res = await fetch(`${API_BASE_URL}/login`, {
  // fetch("http://localhost:8000/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await res.json();
  if (!res.ok) { alert(data.detail || "Login failed."); return; }
  localStorage.setItem("token", data.token);
  localStorage.setItem("username", data.username);
  window.location.href = "dashboard.html";
} catch { alert("Connection error."); }
  });
}


// /* ---------- "Continue as guest" button ---------- */
// const guestBtn = document.getElementById("guestBtn");
// if (guestBtn) {
//   guestBtn.addEventListener("click", function () {
//     // TODO: connect to backend if guests should still be tracked
//     window.location.href = "dashboard.html";
//   });
// }
const guestBtn = document.getElementById("guestBtn");
if (guestBtn) {
  guestBtn.addEventListener("click", function () {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    window.location.href = "dashboard.html";
  });
}
/* ---------- REGISTER FORM ---------- */
const registerForm = document.getElementById("registerForm");
if (registerForm) {
  registerForm.addEventListener("submit", async function (e) {      
                                                                      // change function to async function
    e.preventDefault();

    const name            = document.getElementById("name").value.trim();
    const email           = document.getElementById("email").value.trim();
    const password        = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (!name || !email || !password) {
      alert("Please fill in all fields.");
      return;
    }
    if (password !== confirmPassword) {
      alert("Passwords do not match.");
      return;
    }

  //   // TODO: connect to backend authentication API (register endpoint)
  //   alert("Account created! (UI only — wire backend in app.js)");
  //   window.location.href = "login.html";
  // });          هستبدل دول بالاسطر الجاية 
try {
  const res = await fetch(`${API_BASE_URL}/register`, {
  // fetch("http://localhost:8000/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: name.split(" ")[0].toLowerCase(),
      email, password,
      full_name: name
    })
  });
  const data = await res.json();
  if (!res.ok) { alert(data.detail || "Registration failed."); return; }
  localStorage.setItem("token", data.token);
  localStorage.setItem("username", data.username);
  window.location.href = "dashboard.html";
} catch { alert("Connection error."); }
  });
}




/* ---------- USER DROPDOWN (navbar) ---------- */
// Used on dashboard.html and profile.html
function toggleUserMenu() {
  const menu = document.getElementById("userMenu");
  if (menu) menu.classList.toggle("open");
}
// Close dropdown when clicking outside
document.addEventListener("click", function (e) {
  const menu = document.getElementById("userMenu");
  if (!menu) return;
  if (!menu.contains(e.target)) menu.classList.remove("open");
});

/* ---------- LOGOUT ---------- */
// function logout() {
//   // TODO: connect to backend (invalidate token, clear session)
//   window.location.href = "login.html";
// }      غيرتها للاسطر الجاية

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  window.location.href = "login.html";
}

// _____________________________________________

// Share
function sharePortal()
{
window.location.href = "mailto:?subject=Urban Quality of Life Platform&body=Check out this platform!";
}

/* ---------- LANGUAGE DIRECTION RESTORE ---------- */
(function initLang() {
  const lang = localStorage.getItem("lang") || "en";
  if (lang === "ar") document.documentElement.dir = "rtl";
})();

/* ---------- DARK / LIGHT THEME TOGGLE ---------- */
(function initTheme() {
  const saved = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
})();

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  _syncThemeButtons(next);
}

function _syncThemeButtons(theme) {
  const icon = theme === "dark" ? "☀️" : "🌙";
  const title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  document.querySelectorAll(".theme-toggle, .theme-toggle-float, #themeBtn").forEach(function(btn) {
    btn.textContent = icon;
    btn.title = title;
  });
}

// Set correct icon on page load
document.addEventListener("DOMContentLoaded", function() {
  const theme = document.documentElement.getAttribute("data-theme") || "dark";
  _syncThemeButtons(theme);
});
