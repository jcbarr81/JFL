Absolutely—let’s bake **comprehensive user documentation** into Phase Two so players (GM/Coach) always know what to do. Below is an add-on you can drop into your repo as a new section (or a separate file like `PHASE_TWO_USER_DOCS_PLAN.md`). It integrates docs tasks into each feature milestone **and** adds a parallel “Docs Workstream” with its own acceptance criteria, tooling, and example Codex prompts.

---

# Phase Two – User Documentation Workstream (GM & Coach Focus)

**Docs goals:** Clear, click-by-click guides; context help inside the app; searchable website; tutorials; troubleshooting; accessible language.
**Audience:** New players, returning players, power users (play designer, franchise tinkers).
**Tone:** Friendly, authoritative, visual (screenshots, short GIFs), minimal jargon, consistent glossary.

---

## A. Doc Tooling & Architecture (Do this first)

**Do**

* Choose static site generator: **MkDocs + Material** (searchable, awesome nav, dark mode).
* Repo layout:

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
* Add **docs CI**: build on PR; publish on `main` to `docs/` site (GitHub Pages or artifact).
* Screenshot/GIF process: lightweight script to export **UI screenshots** and **short GIFs** (LICEcap/ShareX or PySide snapshot). Store in `docs/assets/`.
* “Help beacon” pattern: `?` buttons that deep-link to exact docs sections using anchors.

**Definition of Done**

* `mkdocs serve` runs locally; full site renders with search/nav and dark/light theme.
* CI builds docs; publishing works from `main`.
* Template page includes: title, 1-paragraph overview, bullet goals, steps, screenshots, tips, and “Related” links.
* App has a **global Help menu** linking to the docs home and a **context help router** (e.g., `help://depth-chart` → opens browser to `/coach/depth-chart/#drag-and-drop`).

**Example Codex prompt**

> Create an `mkdocs.yml` using Material theme with dark/light toggle, search, version switcher, and a left nav that mirrors our docs/ tree. Add a custom 404 page and site footer with version/build hash.

---

## B. Per-Feature Documentation Hooks (Integrated with Your UI Plan)

For **every Phase Two feature**, add a paired docs task. Below are the *extra* docs items on top of the feature acceptance criteria you already have.

### 1) App Shell & Navigation Hub

**Docs**

* `getting-started/navigation.md` with map of sidebar/pages, keyboard shortcuts, theme toggle.
* 30–60s GIF: “Tour of the Home Dashboard”.

**DoD (Docs)**

* All sidebar items documented with 1-line purpose + “When to use”.
* Screenshot of each dashboard card and where it links.

**Prompt**

> Draft `getting-started/navigation.md` with screenshots and a labeled diagram of the sidebar. Add a tip box for keyboard shortcuts.

---

### 2) Team Select & Team Profile

**Docs**

* `getting-started/team-select.md`, `team/profile.md` (color/logo, coach scheme, leaders).

**DoD**

* “Switching Teams” section tested end-to-end; persistent setting explained.
* Link to Roster, Contracts, Playbooks docs.

**Prompt**

> Write `team/profile.md` explaining each metric on the profile card and how it’s calculated.

---

### 3) Roster & Depth Chart (Coach)

**Docs**

* `coach/roster.md`, `coach/depth-chart.md` (drag-and-drop, validation rules, Auto-Fix).
* Troubleshooting: “Why can’t I save my depth chart?”

**DoD**

* GIF: dragging a player into WR2, saving, undoing.
* Validation rules listed (min counts, special teams).

**Prompt**

> Create `coach/depth-chart.md` with a step list and a “Common errors” expandable section; include a table of min positional requirements.

---

### 4) Contracts & Salary Cap (GM)

**Docs**

* `gm/contracts.md`, `gm/salary-cap.md` (cap room meter, dead money, multi-year view).
* Example: re-sign a player and see cap change.

**DoD**

* Worked example with screenshots of each dialog step; CSV export instructions.

**Prompt**

> Draft `gm/salary-cap.md` explaining cap hit vs. cash, guarantees, and dead money with a numerical example.

---

### 5) Trade Center (GM)

**Docs**

* `gm/trades.md` (drag assets, value meter, CPU counter-offers).
* FAQ: “Why did the CPU reject my trade?”

**DoD**

* Example trade walkthrough with acceptance/decline screenshots; undo step.

**Prompt**

> Write `gm/trades.md` including a “How the CPU evaluates value” section and a troubleshooting list.

---

### 6) Scouting & Draft Board (GM)

**Docs**

* `gm/scouting.md` (budget, grades, combine) and `gm/draft-board.md` (tiers, watchlist).
* `gm/draft-day.md` (on-clock, best available, pick trades).

**DoD**

* End-to-end “Your first draft” tutorial; export “Draft Results” instructions.

**Prompt**

> Create `gm/draft-day.md` with a step-by-step timeline and annotated images of the on-clock panel.

---

### 7) Playbook Manager & Defensive Editor (Coach)

**Docs**

* `coach/playbooks.md` (tags, formations, success rates).
* `editor/defense.md` (zones, blitz paths, coverage metadata).
* `editor/offense.md` (routes, timepoints, mirroring).

**DoD**

* Before/after screenshots of mirroring; JSON schema referenced with examples.

**Prompt**

> Document `editor/defense.md`: explain coverage shells, zone landmarks, and how to encode them in JSON metadata.

---

### 8) Weekly Gameplan & Tendencies (Coach)

**Docs**

* `coach/gameplan.md` (sliders, situational tables, opponent scouting).
* “Preview with 10 test drives” how-to.

**DoD**

* Example template (balanced, pass-heavy, blitz-heavy) downloadable JSON.

**Prompt**

> Write `coach/gameplan.md` covering recommended presets and how each slider affects AI playcalling.

---

### 9) Scenario Simulator / Practice

**Docs**

* `coach/scenarios.md` (setup panel, reps, variability).
* Use cases: 2-minute drill, red zone, 3rd & long.

**DoD**

* GIF: 25 reps of a slant-flat; reading the summary.

**Prompt**

> Draft a scenario cookbook with 5 examples and expected KPIs to watch.

---

### 10) Season Hub, Calendar & Results

**Docs**

* `season/calendar.md`, `season/results.md` (drive charts, sim-to-date).

**DoD**

* “Pause on milestones” explained with list of triggers.

**Prompt**

> Write `season/results.md` explaining drive chart symbols and how to open replays.

---

### 11) Live Sim Console & Replay Viewer

**Docs**

* `live/console.md` (coach mode, CPU suggestions).
* `live/replay.md` (seek/step, overlays).

**DoD**

* Keybinds reference; “fast sim vs real time” notes.

**Prompt**

> Document `live/replay.md` with a callout on performance tips and how to export a replay.

---

### 12) Analytics Dashboards

**Docs**

* `analytics/team.md`, `analytics/player.md`, `analytics/league.md`.
* How to export PNG/CSV; glossary links.

**DoD**

* Each chart has a “What it means” box and “Coaching/GM decisions” guidance.

**Prompt**

> Create `analytics/player.md` explaining YAC vs. air yards and route heatmaps with coaching takeaways.

---

### 13) Injuries, Medical, Training & Development

**Docs**

* `team/injuries.md`, `coach/training.md`, `gm/development.md`.
* Risk/morale tooltips explained.

**DoD**

* Decision examples: conservative vs aggressive return timelines.

**Prompt**

> Draft `team/injuries.md` including a table of injury types, typical recovery windows, and performance impacts.

---

### 14) News Hub & Narrative

**Docs**

* `news/index.md` (what generates news, filters, archive).
* Press conference choices & morale effects.

**DoD**

* Example story anatomy with links to team/player.

**Prompt**

> Write `news/index.md` and include a “What triggers news?” matrix.

---

### 15) Settings, Accessibility & Theming

**Docs**

* `settings/index.md`, `settings/accessibility.md` (font scale, high contrast, dyslexia-friendly font).

**DoD**

* Screenshot of each settings group; restore defaults guide.

**Prompt**

> Create `settings/accessibility.md` with step-by-step toggles and screenshots for each option.

---

### 16) Save/Load, Export & Share

**Docs**

* `save-load/index.md`, `export/index.md`.
* “Share Package” how-to, version compatibility.

**DoD**

* Corruption recovery and version mismatch flows documented.

**Prompt**

> Draft `export/index.md`—how to package a franchise, verify integrity, and import on a new machine.

---

### 17) Plugins/Mods Framework

**Docs**

* `mods/index.md` (hooks, examples, safety).
* Sample plugin tutorial.

**DoD**

* Step-by-step: build the sample plugin and see it in Analytics.

**Prompt**

> Write `mods/sample-plugin.md` showing how to add a post-game hook that computes a custom stat.

---

### 18) Troubleshooting, FAQ, Glossary

**Docs**

* `troubleshooting/index.md` (install, missing deps, GPU issues, DB lock, save conflicts).
* `faq.md` (common gameplay questions).
* `glossary.md` (EPA, SR, AoS, YAC, personnel groups, coverage names).

**DoD**

* At least 20 troubleshooting entries with copy-paste commands.
* Glossary links appear inline across docs.

**Prompt**

> Generate a comprehensive `troubleshooting/index.md` with categorized issues and a search-friendly table of contents.

---

## C. In-App Help Integration

**Do**

* Add `?` buttons on every complex UI panel linking to exact anchors.
* Tooltip text for icons/metrics, consistent style (short, actionable).
* “Learn more” links beside sliders and advanced settings.

**Definition of Done**

* All primary screens have at least one direct docs link.
* Tooltips exist for all non-obvious controls (min. 90% coverage).
* Keyboard shortcut overlay (`?` or `F1`) shows current context shortcuts.

**Prompt**

> Insert `HelpLink` widgets beside advanced controls, resolving `help://` keys to docs URLs; log clicks for future UX analytics.

---

## D. Release Notes & Versioned Docs

**Do**

* `docs/changelog.md` updated per release with “What’s new”, “Upgrade notes”, “Known issues”.
* Versioned docs (e.g., `v0.2`, `latest`) using MkDocs Material version selector.

**Definition of Done**

* Each release PR must update `changelog.md`.
* Docs site shows version dropdown; old versions remain accessible.

**Prompt**

> Add versioned docs configuration and a GitHub Action that copies `docs/` into `site/vX.Y/` on tagged releases.

---

## E. Documentation Quality Gates (apply to every feature PR)

* �... Each new UI view must add/modify at least one docs page.
* �... Screenshots/GIFs updated; filenames reflect the current theme.
* �... A `HelpLink` to the new/updated page exists in the UI.
* �... Docs lints pass (broken links/anchors checked via `mkdocs build -s`).
* �... “What changed” entry added to `changelog.md`.

---

## F. Example “Getting Started” Outline (for `docs/index.md`)

1. What is Gridiron Sim?
2. Choose your role: **GM** vs **Coach** (or both)
3. The 5 screens you’ll use most (with screenshots)
4. Quick start: run your first season in 5 steps
5. Where to get help, report issues, or request features

**Prompt**

> Draft `docs/index.md` with a “First 10 minutes” mini-tutorial: pick a team, set a depth chart, choose a gameplan preset, simulate a week, read results.

---

## G. Accessibility & Readability in Docs

* Minimum 12–14pt base size; high contrast; dark & light reading modes.
* Alt text for all images; captions explaining context.
* Avoid jargon; link to glossary on first occurrence of any acronym.
* Use “Do/Don’t” callouts and tip/warning admonitions.

---

### Roll-Up Milestones (Docs)

1. **Docs Framework Online** (MkDocs site, CI, help router wired)
2. **Coach Loop Docs** (Roster/Depth, Playbooks, Gameplan, Practice)
3. **GM Loop Docs** (Contracts/Cap, Trade Center, Scouting/Draft)
4. **Season & Presentation Docs** (Calendar, Results, Live, Replay, Analytics)
5. **Worldbuilding Docs** (Injuries/Training, News, Settings/Accessibility)
6. **Power User Docs** (Export/Share, Plugins, Troubleshooting, Glossary)

