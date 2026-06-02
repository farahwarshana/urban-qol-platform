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

const AUTH_TXT = {
  en: {
    pageTitle: "Malaz · Login",
    brand: "Malaz · Urban Quality of Life Analysis",
    loginHeading: "Welcome back",
    loginSubtitle: "Sign in to get full access to Malaz.",
    emailLabel: "Email",
    passwordLabel: "Password",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "Login",
    guestButton: "Continue as guest",
    noAccountText: 'Don\'t have an account? <a href="register.html">Register</a>',
    registerHeading: "Create an account",
    registerSubtitle: "and get full access to analyze urban quality of life.",
    nameLabel: "Name",
    namePlaceholder: "Jane Doe",
    confirmPasswordLabel: "Confirm Password",
    confirmPasswordPlaceholder: "••••••••",
    createAccountButton: "Create account",
    alreadyAccountText: 'Already have an account? <a href="login.html">Login</a>',
    langButtonLabel: "العربية",
    errorFillFieldsLogin: "Please fill in both email and password.",
    errorFillFieldsRegister: "Please fill in all fields.",
    errorPasswordsMismatch: "Passwords do not match.",
    errorConnection: "Connection error.",
    loginFailed: "Login failed.",
    registrationFailed: "Registration failed.",
  },
  ar: {
    pageTitle: "ملاز · تسجيل الدخول",
    brand: "مالاز · تحليل جودة الحياة الحضرية",
    loginHeading: "مرحباً بعودتك",
    loginSubtitle: "سجّل الدخول للوصول الكامل لتحليل جودة الحياة الحضرية.",
    emailLabel: "البريد الإلكتروني",
    passwordLabel: "كلمة المرور",
    emailPlaceholder: "you@example.com",
    passwordPlaceholder: "••••••••",
    loginButton: "تسجيل الدخول",
    guestButton: "المتابعة كزائر",
    noAccountText: 'ليس لديك حساب؟ <a href="register.html">تسجيل</a>',
    registerHeading: "إنشاء حساب",
    registerSubtitle: "واحصل على وصول كامل لتحليل جودة الحياة الحضرية.",
    nameLabel: "الاسم",
    namePlaceholder: "سارة أحمد",
    confirmPasswordLabel: "تأكيد كلمة المرور",
    confirmPasswordPlaceholder: "••••••••",
    createAccountButton: "إنشاء الحساب",
    alreadyAccountText: 'لديك حساب بالفعل؟ <a href="login.html">تسجيل الدخول</a>',
    langButtonLabel: "English",
    errorFillFieldsLogin: "يرجى تعبئة البريد الإلكتروني وكلمة المرور.",
    errorFillFieldsRegister: "يرجى تعبئة جميع الحقول.",
    errorPasswordsMismatch: "كلمات المرور غير متطابقة.",
    errorConnection: "خطأ في الاتصال.",
    loginFailed: "فشل تسجيل الدخول.",
    registrationFailed: "فشل إنشاء الحساب.",
  }
};

function applyAuthLang() {
  const currentLang = localStorage.getItem("lang") || "en";
  const T = AUTH_TXT[currentLang];
  if (!T) return;

  document.documentElement.lang = currentLang;
  document.documentElement.dir = currentLang === "ar" ? "rtl" : "ltr";

  const titleEl = document.querySelector("title");
  if (titleEl) titleEl.textContent = T.pageTitle;

  const brandLabel = document.querySelector(".brand span:last-child");
  if (brandLabel) brandLabel.textContent = T.brand;

  const langBtn = document.getElementById("langBtn");
  if (langBtn) {
    langBtn.innerHTML =
      currentLang === "ar"
        ? '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/language.png" alt="lang" class="nav-icon" style="vertical-align:middle;margin-right:5px;"/> English'
        : '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/language.png" alt="lang" class="nav-icon" style="vertical-align:middle;margin-right:5px;"/> العربية';
  }

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    const heading = document.getElementById("pageHeading");
    if (heading) heading.textContent = T.loginHeading;
    const subtitle = document.getElementById("pageSubtitle");
    if (subtitle) subtitle.textContent = T.loginSubtitle;
    const emailLabel = document.querySelector('label[for="email"]');
    if (emailLabel) emailLabel.textContent = T.emailLabel;
    const passwordLabel = document.querySelector('label[for="password"]');
    if (passwordLabel) passwordLabel.textContent = T.passwordLabel;
    const emailInput = document.getElementById("email");
    if (emailInput) emailInput.placeholder = T.emailPlaceholder;
    const passwordInput = document.getElementById("password");
    if (passwordInput) passwordInput.placeholder = T.passwordPlaceholder;
    const submitBtn = loginForm.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.textContent = T.loginButton;
    const guestBtnEl = document.getElementById("guestBtn");
    if (guestBtnEl) guestBtnEl.textContent = T.guestButton;
    const authFooter = document.querySelector(".auth-footer");
    if (authFooter) authFooter.innerHTML = T.noAccountText;
    return;
  }

  const registerForm = document.getElementById("registerForm");
  if (registerForm) {
    const heading = document.getElementById("pageHeading");
    if (heading) heading.textContent = T.registerHeading;
    const subtitle = document.getElementById("pageSubtitle");
    if (subtitle) subtitle.textContent = T.registerSubtitle;
    const nameLabel = document.querySelector('label[for="name"]');
    if (nameLabel) nameLabel.textContent = T.nameLabel;
    const emailLabel = document.querySelector('label[for="email"]');
    if (emailLabel) emailLabel.textContent = T.emailLabel;
    const passwordLabel = document.querySelector('label[for="password"]');
    if (passwordLabel) passwordLabel.textContent = T.passwordLabel;
    const confirmPasswordLabel = document.querySelector('label[for="confirmPassword"]');
    if (confirmPasswordLabel) confirmPasswordLabel.textContent = T.confirmPasswordLabel;
    const nameInput = document.getElementById("name");
    if (nameInput) nameInput.placeholder = T.namePlaceholder;
    const emailInput = document.getElementById("email");
    if (emailInput) emailInput.placeholder = T.emailPlaceholder;
    const passwordInput = document.getElementById("password");
    if (passwordInput) passwordInput.placeholder = T.passwordPlaceholder;
    const confirmPasswordInput = document.getElementById("confirmPassword");
    if (confirmPasswordInput) confirmPasswordInput.placeholder = T.confirmPasswordPlaceholder;
    const submitBtn = registerForm.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.textContent = T.createAccountButton;
    const authFooter = document.querySelector(".auth-footer");
    if (authFooter) authFooter.innerHTML = T.alreadyAccountText;
  }
}

/* ---------- LOGIN FORM ---------- */
const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async function (e) {        
                                                                  //  # change fuction to async function
    
    e.preventDefault();

    const currentLang = localStorage.getItem("lang") || "en";
    const T = AUTH_TXT[currentLang] || AUTH_TXT.en;
    const email    = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    // Very basic UI-only validation
    if (!email || !password) {
      alert(T.errorFillFieldsLogin);
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
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || T.loginFailed);
      return;
    }
    localStorage.setItem("token", data.token);
    localStorage.setItem("username", data.username);
    window.location.href = "dashboard.html";
  } catch {
    alert(T.errorConnection);
  }
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
    e.preventDefault();

    const currentLang = localStorage.getItem("lang") || "en";
    const T = AUTH_TXT[currentLang] || AUTH_TXT.en;
    const name            = document.getElementById("name").value.trim();
    const email           = document.getElementById("email").value.trim();
    const password        = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (!name || !email || !password) {
      alert(T.errorFillFieldsRegister);
      return;
    }
    if (password !== confirmPassword) {
      alert(T.errorPasswordsMismatch);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: name.split(" ")[0].toLowerCase(),
          email,
          password,
          full_name: name
        })
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || T.registrationFailed);
        return;
      }
      localStorage.setItem("token", data.token);
      localStorage.setItem("username", data.username);
      window.location.href = "dashboard.html";
    } catch {
      alert(T.errorConnection);
    }
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

/* ---------- LANGUAGE TOGGLE (shared, non-dashboard pages) ---------- */
(function initLang() {
  const lang = localStorage.getItem("lang") || "en";
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  applyAuthLang();
})();

// Only define if the page hasn't defined its own (dashboard.js / profile_1 define their own)
if (typeof toggleLang === "undefined") {
  window.toggleLang = function toggleLang() {
    const next = (localStorage.getItem("lang") || "en") === "en" ? "ar" : "en";
    localStorage.setItem("lang", next);
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
    const btn = document.getElementById("langBtn");
    if (btn) btn.innerHTML = next === "ar"
      ? '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/language.png" alt="lang" class="nav-icon" style="vertical-align:middle;margin-right:5px;"/> English'
      : '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/language.png" alt="lang" class="nav-icon" style="vertical-align:middle;margin-right:5px;"/> العربية';
    if (typeof applyAuthLang === "function") {
      applyAuthLang();
    }
  };
}

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
