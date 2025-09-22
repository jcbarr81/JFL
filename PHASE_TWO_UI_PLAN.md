Here’s a **Phase Two UI/UX & Franchise Experience** project plan, written in Markdown so you can drop it into your repo as `PHASE_TWO_UI_PLAN.md`. It’s ordered, step-by-step, and every step includes **Definition of Done** and **example Codex prompts**. The plan integrates each new capability directly into the GUI so the app feels like a real **GM/Coach** simulator as you build.

---

# Phase Two – UI/UX & Franchise Experience Project Plan

**Target roles:** General Manager (contracts, trades, scouting, cap) & Head Coach (playbooks, gameplans, depth charts, in-game adjustments)
**Primary tech:** PySide6/PyQt6 (desktop), FastAPI (existing), SQLModel, matplotlib/Plotly (charts)
**Design goals:** Cohesive app shell, intuitive flows, responsive interactions, attractive theming (dark preferred), keyboard shortcuts, accessibility

---

## Table of Contents

1. [Design System & UI Architecture Foundation](#0-design-system--ui-architecture-foundation)
2. [App Shell & Navigation Hub](#1-app-shell--navigation-hub)
3. [Team Select & Team Profile](#2-team-select--team-profile)
4. [Roster & Depth Chart Management (Coach)](#3-roster--depth-chart-management-coach)
5. [Contracts & Salary Cap (GM)](#4-contracts--salary-cap-gm)
6. [Trade Center (GM)](#5-trade-center-gm)
7. [Scouting & Draft Board (GM)](#6-scouting--draft-board-gm)
8. [Playbook Manager: Offense & Defense (Coach)](#7-playbook-manager-offense--defense-coach)
9. [Weekly Gameplan & Tendencies (Coach)](#8-weekly-gameplan--tendencies-coach)
10. [Scenario Simulator / Practice](#9-scenario-simulator--practice)
11. [Season Hub, Calendar & Results](#10-season-hub-calendar--results)
12. [Live Sim Console & Replay Viewer](#11-live-sim-console--replay-viewer)
13. [Analytics Dashboards](#12-analytics-dashboards)
14. [Injuries, Medical, Training & Development](#13-injuries-medical-training--development)
15. [News Hub & Narrative Layer](#14-news-hub--narrative-layer)
16. [Settings, Accessibility & Theming](#15-settings-accessibility--theming)
17. [Save/Load, Export & Share](#16-saveload-export--share)
18. [Plugins/Mods Framework](#17-pluginsmods-framework)
19. [Polish & Performance Pass](#18-polish--performance-pass)
20. [Appendix: Navigation Map & Shared Components](#appendix-navigation-map--shared-components)

---

## 0) Design System & UI Architecture Foundation

**Goal:** Establish a consistent look/feel, component library, and navigation framework so subsequent features drop in cleanly.

**Do**

* Create `ui/core/` for shared widgets (AppWindow, NavSidebar, TopBar, Theming, Dialogs, Toasts, Confirmations, BusyOverlay).
* Establish **theme tokens**: colors, typography, spacing, radii, elevation; implement Qt stylesheets (QSS).
* Add a simple **state bus** (signals/slots or a lightweight event hub) for cross-page updates (e.g., “roster changed”, “cap updated”).
* Add **loading/error** patterns and **empty-state** placeholders for all tables and panes.

**Definition of Done**

* A new “AppWindow” with sidebar + topbar renders and can host dummy pages.
* One source of truth for theme; dark/light toggle works globally.
* Shared components: `PrimaryButton`, `SecondaryButton`, `IconButton`, `Table`, `Card`, `Tag`, `Pill`, `FormRow`, `Modal`, `Toast`.
* Keyboard shortcuts: `Ctrl+S` (save), `Ctrl+F` (search), `Esc` (close modal).
* Unit/UI tests for component creation and theming injection.

**Codex Prompt**

> PySide6: Build `AppWindow` with a permanent left `NavSidebar` and a `TopBar`. Provide a `PageRouter` (QStackedWidget) that switches pages on sidebar clicks. Add a `Theme` class with dark/light palettes and a function to apply QSS app-wide.

---

## 1) App Shell & Navigation Hub

**Goal:** A “Home” dashboard that orients the user each time they open the app.

**Do**

* Implement **Home Dashboard** (cards for: Next Game, Record/Standings, Cap Room, Top Performers, Injury Report, News).
* Add top-level nav routes: *Home, Team, Coach, GM, Playbooks, Season, Analytics, Settings*.

**Definition of Done**

* Sidebar routes switch pages without memory leaks.
* Dashboard tiles load fast (<200 ms after data fetch).
* All tiles link to their detail pages.

**Codex Prompt**

> Create a `HomeDashboard` view with cards (Next Game, Cap Room, Injuries, News). Each card should load via async tasks and show skeleton loaders, then hydrate content.

---

## 2) Team Select & Team Profile

**Goal:** Let users pick a franchise and view a rich team overview.

**Do**

* Team selector modal on first launch or via TopBar team switcher.
* Team Profile page: logo, colors, coach, scheme, current streak, leaders, upcoming schedule.

**Definition of Done**

* Team switch persists across sessions.
* Team profile pulls live stats from DB; all links navigate correctly.

**Codex Prompt**

> Build `TeamSelectDialog` with grid of team logos/colors. Persist choice in a settings table. Implement a `TeamProfilePage` showing team summary and links to Roster, Contracts, Depth Chart, Playbooks.

---

## 3) Roster & Depth Chart Management (Coach)

**Goal:** Coach-feel drag-and-drop lineup and depth chart tools.

**Do**

* Roster table with filters (position, age, OVR, contract status).
* Depth chart board per unit (Offense/Defense/Special Teams) with drag-and-drop.
* Validation: 53-man roster (or your league rule), min positional requirements.

**Definition of Done**

* Drag-and-drop updates depth chart, persists, and emits “depth\_chart\_changed”.
* Validation banners on illegal configurations; “Auto-Fix” button.
* Performance: drag interaction smooth at 60 FPS on typical hardware.

**Codex Prompt**

> Implement `DepthChartView` with PySide6: left is Roster (QTableView), right is depth chart slots per position. Enable drag from table rows to slots; persist updates; show validation alerts.

---

## 4) Contracts & Salary Cap (GM)

**Goal:** Contract management UI with live cap impact.

**Do**

* Contracts table (AAV, years, guarantees, cap hit by year, dead money).
* New Contract dialog with sliders and live cap room meter.
* Cap summary bar with projections (current, next 3 seasons).

**Definition of Done**

* Creating/renegotiating a contract updates DB, cap tables, and UI immediately.
* Cap and roster validation integrated; cannot exceed roster/contract limits without override.
* CSV export of cap table.

**Codex Prompt**

> Build a `ContractEditorDialog` that calculates cap hit and dead money year-by-year. Show a progress bar for remaining cap space. On save, update SQLModel rows and emit `cap_updated`.

---

## 5) Trade Center (GM)

**Goal:** CPU and human trades with value assessment.

**Do**

* Trade screen: drag players/picks from each side into offer lists.
* Trade value meter (OVR, age, contract, positional scarcity).
* CPU proposes counter-offers.

**Definition of Done**

* Trades validate and update rosters, cap, depth charts.
* Value meter correlates with CPU accept/decline decisions.
* Undo last trade (one-level revert).

**Codex Prompt**

> Implement `TradeCenter` UI with two columns (Our vs Their assets), a trade value bar, and an `Evaluate` button that returns accept/decline and suggested adjustments.

---

## 6) Scouting & Draft Board (GM)

**Goal:** Seasonal scouting loop with a tactile draft experience.

**Do**

* Scouting board: prospects list, filters, watchlist, grades (noisy), combine metrics.
* Draft board with tiers and drag-to-tier UI.
* Draft Day view: on-clock timer, best available, team needs, trade pick offers.

**Definition of Done**

* Scouting budget allocation UI affects visibility/noise of grades.
* Draft picks update rosters and depth charts live; recap screen generated.
* Export “Draft Class” and “Draft Results” CSVs.

**Codex Prompt**

> Create `DraftBoardView` with draggable tiers (T1–T5). Integrate a `DraftDayDialog` that simulates CPU picks with pause/skip and allows pick trades.

---

## 7) Playbook Manager: Offense & Defense (Coach)

**Goal:** Move beyond the editor—curate complete playbooks and link to gameplan.

**Do**

* Playbook browser for offense & defense: list, tags, formations, success rates.
* Import/export plays; mirror plays; versioning.
* Hook defensive play editor (zones, blitz paths, coverage shells).

**Definition of Done**

* Playbook changes reflect in weekly gameplan selection.
* Defensive editor saves to same JSON schema (plus coverage metadata).
* Per-play success stats populate from season logs.

**Codex Prompt**

> Build `PlaybookManager` with tabs for Offense/Defense, filters by formation/personnel/tags, and inline mini-diagram previews from JSON route data.

---

## 8) Weekly Gameplan & Tendencies (Coach)

**Goal:** Game-by-game strategy that the AI uses in live sims.

**Do**

* Sliders for run/pass mix, deep/short bias, blitz %, coverage call rates.
* Situational tables (e.g., 3rd & long: preferred plays/formations).
* Opponent scouting report panel.

**Definition of Done**

* Gameplan parameters feed the sim’s playcalling and influence outcomes.
* Export/import gameplans; compare plan vs result post-game.

**Codex Prompt**

> Implement `GameplanView` with sliders and situational matrices (down/distance buckets). Provide a “Sim 10 test drives” button to preview expected tendencies.

---

## 9) Scenario Simulator / Practice

**Goal:** Fast iteration on plays and situational coaching.

**Do**

* Quick setup: down, distance, yardline, time, score, hash, weather.
* Select play(s) to test; see outcomes summary.
* “Auto-repeat” and variability toggles.

**Definition of Done**

* Scenario results produce a summary panel (success rate, EPA, pressure rate).
* “Promote to Gameplan” button to add tested plays into situational tables.

**Codex Prompt**

> Build `ScenarioSimulator` with a right-hand config panel and a center canvas. Add a `Run 25 reps` action and aggregate results into a table + chart.

---

## 10) Season Hub, Calendar & Results

**Goal:** Franchise overview with a calendar flow.

**Do**

* Month/Week calendar with game days, bye weeks, key deadlines (trade, draft, FA).
* Results list with expandable box scores and drive charts.
* “Sim to date” with checkpoint save prompts.

**Definition of Done**

* Calendar events are clickable and navigate to appropriate views.
* Drive chart renders for any completed game.
* “Sim to…” respects pause conditions (injury, trade offer, user flags).

**Codex Prompt**

> Implement `SeasonHub` with a monthly calendar widget. Add `SimToDateDialog` that takes a target date and pauses on configured milestones.

---

## 11) Live Sim Console & Replay Viewer

**Goal:** Make watching or coaching through a game compelling.

**Do**

* Live console with scoreboard, possession, down/distance, playclock.
* Playcall panel (if “coach mode” enabled); CPU suggestions.
* Replay viewer that steps through per-tick logs with animation.

**Definition of Done**

* Live sim runs in real time or “fast sim”; pausing works reliably.
* Replay viewer animates routes/ball with step/seek controls.
* In-game adjustments (tempo, aggressiveness) reflected mid-game.

**Codex Prompt**

> Create `LiveSimConsole` with a field canvas, scoreboard, and Playcall sidebar. Build `ReplayViewer` that reads event logs and animates entities at 20Hz with play/pause/step.

---

## 12) Analytics Dashboards

**Goal:** Surface deeper insight for both GM and Coach decisions.

**Do**

* Team dashboard: EPA/play, success rate, pressure %, run/pass rates, down/distance breakdowns.
* Player dashboard: usage, YAC vs air yards, heatmaps (targets, run lanes).
* Compare tool: head-to-head vs league averages.

**Definition of Done**

* Charts render quickly (<250 ms per chart with cached queries).
* Export PNG/CSV from every chart/table.
* Color-blind friendly palette; tooltips with precise values.

**Codex Prompt**

> Implement `AnalyticsPage` with tabs (Team, Player, League). Use matplotlib or Plotly; add export buttons and a theming adapter.

---

## 13) Injuries, Medical, Training & Development

**Goal:** Tie gameplay to long-term health and growth.

**Do**

* Injury report page: current injuries, timelines, depth chart impact.
* Training planner: focus areas per unit/player (e.g., pass pro, tackling).
* Development screen: progression, regression, dev traits, morale.

**Definition of Done**

* Setting training focus updates progression rates in sims.
* Injury timeline updates post-game; medical decisions affect risk (UI warns).
* Morale impacts performance with transparent tooltips.

**Codex Prompt**

> Build `MedicalCenter` (injury list with ETA) and `TrainingPlanner` (weekly focus with tooltips on projected gains/losses). Persist selections and show effects in post-week summary.

---

## 14) News Hub & Narrative Layer

**Goal:** Atmosphere and immersion.

**Do**

* News feed: game recaps, trades, injuries, milestones, draft rumors.
* “Press conference” flavor choices affecting morale/fan sentiment.
* Searchable archive.

**Definition of Done**

* Every major transaction/injury/game generates news items.
* Choices (3-option dialog) adjust small morale/fan perception values.
* News cards link to relevant players/teams.

**Codex Prompt**

> Implement `NewsHub` that subscribes to event bus (“trade\_completed”, “injury\_updated”, “game\_final”). Render news cards with tags and quick links.

---

## 15) Settings, Accessibility & Theming

**Goal:** Make it comfortable and professional.

**Do**

* Graphics & animation speed, data refresh intervals, autosave cadence.
* Input customization, common shortcuts list.
* Accessibility: font size scale, dyslexia-friendly font, high contrast theme.

**Definition of Done**

* All settings persist, are applied instantly or on restart as appropriate.
* WCAG-aware color contrast where feasible.
* Global error boundary shows friendly message with copyable diagnostics.

**Codex Prompt**

> Build `SettingsPage` with sections: General, Display, Controls, Accessibility. Implement `SettingsStore` with load/save and change events.

---

## 16) Save/Load, Export & Share

**Goal:** A user-friendly layer over existing persistence.

**Do**

* Save game slots with thumbnails and version metadata.
* Export/import: leagues, draft classes, playbooks, gameplans.
* “Share Package” zip creator for a selected franchise.

**Definition of Done**

* Corrupted or mismatched versions handled with safe error flows.
* Exported packages re-import cleanly on a fresh install.
* Background progress dialog for long exports with cancelation.

**Codex Prompt**

> Implement `SaveManager` UI with slot thumbnails and details. Add `ExportCenter` that packages selected artifacts into a zip and validates integrity on import.

---

## 17) Plugins/Mods Framework

**Goal:** Extensibility for power users.

**Do**

* Define plugin hooks (pre\_play, post\_play, pre\_game, post\_season).
* “Plugins” page with enable/disable, ordering, and simple permissions.
* Sample plugin: custom stat or narrative generator.

**Definition of Done**

* Plugin lifecycle documented; errors sandboxed with logs.
* Enabling/disabling a plugin changes behavior immediately where safe.
* Sample plugin installs via UI and demonstrates new column in analytics.

**Codex Prompt**

> Create a `PluginManager` with a registry of hook functions and a UI to manage plugins. Sandbox plugin execution with try/except and structured logging.

---

## 18) Polish & Performance Pass

**Goal:** Smoothness and quality before calling Phase Two done.

**Do**

* Profile UI responsiveness; virtualized tables for large lists.
* Cache heavy queries; background preload upcoming pages.
* Add micro-animations (hover, press, transitions) and consistent empty-state art.

**Definition of Done**

* Time-to-interactive < 1.0s on app launch (warm DB).
* Large roster/draft tables scroll at 60 FPS on mid-range hardware.
* No blocking spinners > 500 ms without a progress indicator.

**Codex Prompt**

> Add a `DataCache` layer with TTL and prefetch hooks (e.g., prefetch opponent data when opening Gameplan). Replace heavy tables with virtualized models.

---

## Appendix: Navigation Map & Shared Components

**Navigation (sidebar)**

* Home
* Team (Profile, Roster, Depth Chart, Injuries)
* GM (Contracts/Cap, Trades, Scouting, Draft Board)
* Coach (Playbooks, Gameplan, Practice/Scenarios)
* Season (Calendar, Results)
* Live (Live Sim, Replay)
* Analytics
* News
* Settings
* Plugins

**Shared components to build early**

* `AppWindow`, `NavSidebar`, `TopBar`, `PageRouter`
* `Card`, `Table`, `FormRow`, `Modal`, `Toast`, `BusyOverlay`
* `FieldCanvas` (used by Play Editor, Replay, Practice, Live Sim)
* `ValuePill` (cap room, morale, fatigue, injury risk)
* `MiniChart` (sparklines in tables)

---

## Cross-Cutting “Definition of Done” (every step)

* �... The feature’s UI is reachable from the sidebar or a contextual link.
* �... Changes persist to DB; backing API methods are typed and covered by tests.
* �... Telemetry/events update other open pages appropriately.
* �... Theming, keyboard shortcuts, and accessibility applied.
* �... Performance budget respected; no noticeable UI hitches.
* �... Docs updated: short “How to use” paragraph in `docs/` and a screenshot.

---

## Milestone Order (suggested)

1. **Foundations**: Design System → App Shell → Team Select/Profile
2. **Coach Loop**: Roster/Depth → Playbook Manager → Gameplan → Practice
3. **GM Loop**: Contracts/Cap → Trade Center → Scouting/Draft
4. **Season & Presentation**: Season Hub → Live Sim/Replay → Analytics
5. **Worldbuilding**: Injuries/Training → News Hub → Settings/Accessibility
6. **Power User**: Save/Export → Plugins → Polish/Perf

