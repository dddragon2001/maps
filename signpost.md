# Master Signpost

Hop 1 of 2. Each line points to one area signpost; the area signpost points to the real files.
Facts live in the target files, never here.

- [Investments & Trading](F:\Cloude_Code\maps\Investments\signpost.md): Stock market investments, algorithms, automated trading, and portfolio tracking (stocks, ETFs).
- [Gaming & AI Development](F:\Cloude_Code\maps\Gaming\signpost.md): Game creation, AI agents, tools, and project codebases (GitHub & local).
- [Marketing & Affiliate](F:\Cloude_Code\maps\Marketing\signpost.md): Social media marketing, recruitment marketing, and affiliate networks.
- [BI & Data Engineering](F:\Cloude_Code\maps\BI\signpost.md): Business intelligence systems, data pipelines, and analytics frameworks.
- [Archives & Reference](F:\Cloude_Code\maps\Archives\signpost.md): Inactive projects, historical records, and documentation.

## Maintenance
- [Nightly checker](F:\Cloude_Code\maps\check_signposts.py): Validates every signpost link, section order, and unreferenced folders.
- [Sync script](F:\Cloude_Code\maps\sync_maps.py): Two-way git sync with GitHub, run every 5 minutes on each account.
- [Agent deny profile](F:\Cloude_Code\maps\agent_settings.json): Claude settings for claude-agent; blocks every tool that can send, share or delete.

## Pulse
- [Routines list](F:\Cloude_Code\maps\routines.json): Every scheduled routine with its schedule, machine, model, tools, limits and output, plus the two run caps.
- [Routine runner](F:\Cloude_Code\maps\run_routines.py): Runs due routines every 5 minutes as claude-agent, sends to Telegram, logs each run to logs\runs.log.
- [Morning digest prompt](F:\Cloude_Code\maps\digest_prompt.md): What the 07:00 digest covers: overnight, due today, waiting.
- [To-do](F:\Cloude_Code\maps\todo.md): Open items with due dates and who is waiting; the digest reads it.

## Screen
- [Dashboard server](F:\Cloude_Code\maps\serve_dashboard.py): Read-only page on http://127.0.0.1:8765, this PC only; serves the page and panel files, nothing else.
- [Dashboard page](F:\Cloude_Code\maps\dashboard.html): Panels for due and waiting, routines and sync, each with its own timestamp and a stale mark.
- [Panel writer](F:\Cloude_Code\maps\panels.py): The runner and the sync script use it to write panel files to C:\MAPS\screen\data.
