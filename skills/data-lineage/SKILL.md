---
name: data-lineage
description: Build client-formatted data lineage workbooks from Atlan impact reports using the Data Lineage Builder tool (stage 1 of the EB CRM→ATS transition pipeline). Use when the user asks for a lineage file/workbook for a dashboard, mentions Atlan impact reports, or starts a dashboard transition.
---

# Data Lineage Builder (stage 1 of the CRM→ATS pipeline)

Turns Atlan impact reports (`<Dashboard>_Upstream.csv`) into client-formatted Excel
lineage workbooks. It is a Python project + built exe with GUI and CLI.

## First invocation in a chat — confirm with the user (paths move):
1. Tool location (a folder containing `lineage_app.py` + `lineage_settings.json`,
   and/or the built `Data Lineage Builder.exe`).
2. Atlan impact reports folder.
3. Output folder for the workbook.

## Running (CLI)
```powershell
# from source (needs a python with pandas+openpyxl — plain WindowsApps python lacks them;
# on Aryan's machine use anaconda python):
& <python> <tool>\lineage_app.py -i "<report>_Upstream.csv" -o "<out>\<Dashboard> Lineage.xlsx" --config <tool>\lineage_settings.json -y
# or the exe with the same flags. --help lists everything.
```
- ALWAYS pass `--config <tool>\lineage_settings.json` — it carries the user's saved
  pruning rules, source labels, and format prefs; without it you get defaults.
- Single input auto-names sheets/output after the dashboard; multiple inputs merge
  into one combined workbook with a "List of Reports" index (default) — `--no-combine`
  for one file per report. `-s` splits Detailed sheets to a separate file.
- A single report builds in ~1–2 min; ALL dashboards with detailed sheets can take
  20+ min — don't batch-build casually.

## Gotchas
- Never leave the tool's own OUTPUT workbooks in the input folder (they get skipped,
  but historically caused slowdowns).
- Atlan export column names/connector values vary in case/spacing between exports —
  the tool canonicalizes, but if a report is skipped for "missing required columns",
  check whether the data is on a non-first sheet (only sheet 1 is read).
- The lineage file is 100% correct and parallel — downstream (KPI feasibility) treats
  it as ground truth for source-system calls.

## After building
- Identify deprecated CRM sources: schema `CRM_MSCRM`, `CRM_MIGRATIONDB*`, and DW
  objects pinned to `DW_DATA_SOURCE_KEY=1` (the /kpi-feasibility skill continues from
  here).
- The lineage workbook goes to the client by mail (user sends; draft on request).
