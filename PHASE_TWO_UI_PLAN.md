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
- Create `ui/core/` for shared widgets (AppWindow, NavSidebar, TopBar, Theming, Dialogs, Toasts, Confirmations, BusyOverlay).
- Establish **theme tokens**: colors, typography, spacing, radii, elevation; implement Qt stylesheets (QSS).
- Add a simple **state bus** (signals/slots or a lightweight event hub) for cross-page updates (e.g., “roster changed”, “cap updated”).
- Add **loading/error** patterns and **empty-state** placeholders for all tables and panes.

**Definition of Done**
- A new “AppWindow” with sidebar + topbar renders and can host dummy pages.
- One source of truth for theme; dark/light toggle works globally.
- Shared components: `PrimaryButton`, `SecondaryButton`, `IconButton`, `Table`, `Card`, `Tag`, `Pill`, `FormRow`, `Modal`, `Toast`.
- Keyboard shortcuts: `Ctrl+S` (save), `Ctrl+F` (search), `Esc` (close modal).
- Unit/UI tests for component creation and theming injection.

**Codex Prompt**
> PySide6: Build `AppWindow` with a permanent left `NavSidebar` and a `TopBar`. Provide a `PageRouter` (QStackedWidget) that switches pages on sidebar clicks. Add a `Theme` class with dark/light palettes and a function to apply QSS app-wide.

... (full plan continues with all steps)
