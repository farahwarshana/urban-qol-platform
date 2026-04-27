# Urban Quality of Life Analysis Platform — UI

A multi-page **vanilla HTML / CSS / JavaScript** UI for an urban analysis platform.
No frameworks, no build step. Just open `login.html` in a browser.

## Structure

```
project/
├── index.html        ← redirects to login
├── login.html        ← login form (UI only)
├── register.html     ← register form (UI only)
├── dashboard.html    ← main GIS dashboard (3-column layout + map + chatbot)
├── profile.html      ← past analyses list
├── css/
│   └── styles.css    ← all styles, dark theme variables at the top
└── js/
    ├── app.js        ← shared (auth forms, navbar, logout)
    └── dashboard.js  ← service workflow, tabs, chatbot, map placeholder
```

## How to run

Just open `login.html` in any modern browser. No server required for the UI.

> When you wire a Python backend, you'll need to serve the files
> (e.g. `python -m http.server 5500`) and configure CORS on the backend.

## Where to plug your Python backend

Search the codebase for `// TODO:` comments. Every backend integration point is marked:

- `js/app.js` — authentication (login, register, logout)
- `js/dashboard.js` — analysis runs (file upload, run analysis, AI chatbot)
- `js/dashboard.js` — `initMap()` for real Leaflet tiles
- `profile.html` — fetch user history

## Design notes

- Dark, minimal, GIS-style theme.
- All colors live in CSS variables in `:root` (top of `styles.css`) — change them once to retheme.
- Bootstrap 5 is loaded via CDN for utility classes.
- Leaflet 1.9.4 is loaded via CDN; the map div is ready, init is commented out.
