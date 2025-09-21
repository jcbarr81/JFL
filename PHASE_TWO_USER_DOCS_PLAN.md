# Phase Two – User Documentation Workstream (GM & Coach Focus)

**Docs goals:** Clear, click-by-click guides; context help inside the app; searchable website; tutorials; troubleshooting; accessible language.  
**Audience:** New players, returning players, power users (play designer, franchise tinkers).  
**Tone:** Friendly, authoritative, visual (screenshots, short GIFs), minimal jargon, consistent glossary.

---

## A. Doc Tooling & Architecture (Do this first)

**Do**
- Choose static site generator: **MkDocs + Material** (searchable, awesome nav, dark mode).
- Repo layout:
  ```
  docs/
    index.md
    getting-started/
    gm/
    coach/
    editor/
    analytics/
    season/
    live/
    troubleshooting/
    glossary.md
    faq.md
    changelog.md
  mkdocs.yml
  ```
- Add **docs CI**: build on PR; publish on `main` to `docs/` site (GitHub Pages or artifact).
- Screenshot/GIF process: lightweight script to export **UI screenshots** and **short GIFs** (LICEcap/ShareX or PySide snapshot). Store in `docs/assets/`.
- “Help beacon” pattern: `?` buttons that deep-link to exact docs sections using anchors.

**Definition of Done**
- `mkdocs serve` runs locally; full site renders with search/nav and dark/light theme.  
- CI builds docs; publishing works from `main`.  
- Template page includes: title, 1-paragraph overview, bullet goals, steps, screenshots, tips, and “Related” links.  
- App has a **global Help menu** linking to the docs home and a **context help router** (e.g., `help://depth-chart` → opens browser to `/coach/depth-chart/#drag-and-drop`).

... (full docs plan continues with all sections)
