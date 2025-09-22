# Weekly Gameplan & Tendencies

Dial in your weekly strategy before the sim takes control. The Gameplan view lives under **Coach ? Weekly Gameplan** inside the desktop client.

## Goals
- Align run/pass balance, shot selection, blitz rate, and coverage tendencies for the next opponent.
- Capture situational plans (3rd & long, red zone, hurry-up, goal line) in one table the staff can follow.
- Keep notes on matchup flags, injuries, or tactics to revisit after the game.

## Workflow
1. Pick the **week** you are preparing for. The opponent and scouting report update instantly.
2. Adjust the four **tendency sliders**. Zone % automatically mirrors man coverage so you can see the trade-off.
3. Edit the **situational table**. Double-click any cell to tweak formations, calls, or reminders; add rows for custom looks.
4. Drop quick reminders in **Coaching Notes** so the staff remembers critical adjustments.
5. Press **Sim 10 test drives** to preview expected totals (plays, blitzes, explosive chance, etc.).
6. Hit **Save Gameplan**. The simulator listens for `gameplan.updated` events and will call your tendencies during live or quick sims.

## Import / Export
- **Export Plan** writes a JSON file (e.g. `TST_wk3_OPP.json`) into your `exports/` folder. Share it with other leagues or back up game-specific scripts.
- **Import Plan** lets you pull a saved JSON and remap it onto the active team/week. Useful for copying a successful strategy from last season.

## Tips\n- Use the scouting blurb to decide whether to dial up pressure or play coverage. Explosive %, pressure allowed, and key players are prefilled.\n- Post-sim, check the new plan comparison summary (UI/API) to see how actual run/pass mix, deep shots, blitz %, and zone % aligned with the sliders.\n- Pair this page with **Roster & Depth Chart** adjustments so personnel matches the plan (e.g., more dime DBs when zone rate is high).
- After the game, compare the **Plan vs Results** metrics surfaced in analytics to refine tendencies.

## Next Steps
- Document depth-chart tweaks in `coach/roster.md` (once created) so assistants know which units support each gameplan.
- Capture screenshots/GIFs for the docs site after major UI updates to keep tutorials current.


