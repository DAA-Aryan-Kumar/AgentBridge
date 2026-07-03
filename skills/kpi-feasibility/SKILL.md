---
name: kpi-feasibility
description: Run the EmployBridge CRM→ATS dashboard transition pipeline - data lineage workbooks, KPI feasibility analysis and client feasibility workbooks, Snowflake source validation via CoCo. Use when the user mentions KPI feasibility, feasibility file/workbook, dashboard transition, CRM to ATS, data lineage file for a dashboard, or names an EB dashboard (MMM, COO, Productivity, Order Fulfilment, Heat Map, Branch Review...) in a transition context.
---

# CRM→ATS KPI Feasibility Pipeline

Client: EmployBridge (EB) is deprecating Microsoft Dynamics CRM for Salesforce ATS /
Recruitment Cloud (RC). Other systems stay: Lawson (financial/billing), UKG, Essbase,
FP&A, SF opportunity data. ~15 Power BI dashboards must transition in under 6 months.
Aryan's team (Accordion/Merilytics analysts) runs a 3-stage pipeline per dashboard;
Order Fulfilment is done and is the experience base. Current queue: MMM → COO →
Productivity (confirm with the user).

## First invocation in a chat — ask the user for (never assume, files move):
1. Which dashboard, and the Atlan impact report location (folder of `*_Upstream.csv`).
2. Data Lineage tool location (a Python project + built exe; has CLI `-i/-o/--config`
   and GUI; use its `lineage_settings.json` as `--config` to match user preferences).
3. The reference feasibility workbook (format standard to reproduce exactly).
4. Power BI access: Service XMLA endpoint + model/workspace name
   (`powerbi://api.powerbi.com/v1.0/myorg/<Workspace>`), or an open Desktop instance.
5. Output folder for deliverables.

## The 3-stage pipeline

**Stage 1 — Data lineage.** Run the Data Lineage tool on the dashboard's Atlan impact
report → client-formatted lineage workbook. Identify the CRM-side sources that will be
deprecated (schemas like CRM_MSCRM; DW objects pinned to `DW_DATA_SOURCE_KEY=1`).
The lineage file goes to the client by MAIL (user sends; you draft) to help their team.
Lineage files are 100% correct and parallel — use them to ground source-system calls.

**Stage 2 — KPI feasibility (the core).** For each KPI on the dashboard:
base tables → fully-qualified Snowflake source → source system → CRM dependency →
ATS replacement → feasibility verdict. Build the internal + client workbooks.
- Extract KPIs/measures from the dashboard via **Power BI MCP — READ-ONLY** (a
  read-only MCP mode EXISTS and should be enabled — verify with the user; never call
  create/update/delete/refresh/deploy operations regardless). Useful queries:
  `INFO.VIEW.TABLES`, `INFO.VIEW.MEASURES` (DAX), `INFO.PARTITIONS` (M expressions —
  reverses Power Query renames to real Snowflake columns). Determine which tables feed
  measures vs. slicers. Keep query count low (rate limits; personal auth token).
  EB discourages downloading dashboards to the local machine unless necessary.
- Validate ATS sources in **Snowflake via CoCo** (use the `agent-bridge` skill): CoCo
  runs read-only SQL. ATS RC is NEW — columns often exist but are EMPTY, and joins can
  produce bogus results. Always ask CoCo for: row counts by `DW_DATA_SOURCE_KEY`/src,
  null/fill-rate of candidate columns, join coverage %, and distinct-value sanity.
  One task per message, exact fully-qualified names, results as attached files.
- **Send the resulting KPI feasibility workbook to the client** (user mails it).

**Stage 3 — Transition the dashboard** (repoint sources, rebuild measures). Assist as
asked; the feasibility file is the spec.

## Source reliability order (resolve conflicts top-down)
1. The transitioned/revamp dashboard's implemented ATS measures — ground truth
   (EXCEPT paid-rate metrics there: forward-looking/aspirational, not authoritative).
2. The md "key findings by source" analysis (CoCo output).
3. Prior Order-Fulfilment feasibility file.
4. Older feasibility files (lowest).

## Feasibility taxonomy (exact definitions)
- **Yes** — transitions to ATS, or has no CRM dependency.
- **Probable** — derivable via indirect logic or an implemented approximation
  (may be unreliable — say so plainly).
- **No** — no confirmed ATS equivalent.

## EB domain cheat-sheet (usually holds; verify per dashboard)
- Migration copies active accounts (~84% active, ~22% inactive). SF `ACCOUNT`
  under-represents billed/historical customers (~28%) → billed-customer counts use
  Lawson `ARCUSTOMER`; SF fine for active-population slicers.
- Transactional/assignment/billing grain already carries Lawson `CUSTOMER_NUMBER`
  (~90–100% for ATS rows); the gap is only at the SF ACCOUNT master layer.
- ATS holds job detail at finalization, not creation; no within-order history:
  openings/committed/filled/fill-rate = Yes (`TR1__JOB__C[TR1__NUMBER_OF_OPENINGS__C]`,
  `TR1__JOB__C[BH_NUMBER_COMMITTED__C]`, `TR1__CLOSING_REPORT__C`); on-time/
  at-creation/first-line metrics = No.
- Paid metrics: ATS assignments ↔ Lawson `REPORT_FPR` via CRM-legacy ids; coverage
  incomplete & declining (~1/3) → feasible-but-unreliable, keep **Probable**; a
  dedicated ATS-financial key is expected (client-confirmed).
- `MASTER_ASSIGNMENT_FACT`/`VW_TURNOVER_EDW` are CRM-only (0 ATS) → repoint to
  `ASSIGNMENT_FACT` (src=2, has `PAYOUT_WORKING_HOURS`); dates re-derivable from Lawson
  `ACTRANS`. Turnover roll-ups (`TURNOVER_CUSTOMER_FACT`/`_BRANCH_FACT`) inherit this.
- Candidate funnel mostly not feasible; only Assignment stage maps (`ASSIGNMENT_DIM` src=2).
- Financial/headcount views (`VW_PRODUCTIVITY_ACTUALS`) are CRM-safe. Branch/customer
  dims pinned to `DW_DATA_SOURCE_KEY=1` → switch to dual/SF (`BRANCH__C`, `CUSTOMER_SF_DIM`).
- Identity: `EMPLOYEE_ID = TALENT.ID` (ATS) / `CONTACT_DYNAMICS_GUID__C` (CRM).

## Extra process facts (from the user's draft transition doc)
- Maintained regardless of CRM: all EDW-production tables/views; Enterprise objects EB
  itself uses. Scrutinize `DEV_SANDBOX_MERILYTICS` objects especially. Mixed tables
  carry both CRM+ATS rows — ATS data via `dw_data_source_key = 2`.
- Key ATS base tables (`PROD_DATALAKE.SALESFORCE`): `TR1__CLOSING_REPORT__C`
  (Assignment), `TALENT` (Employee), `TR1__JOB__C` (Job), `DEPARTMENT__C` (Department).
- Validation SQL strategy: join CRM↔ATS on GUIDs/ids, note field-level differences,
  measure % of datapoints flowing into ATS for recent time frames.
- If a field is absent from ATS Snowflake tables: search the Salesforce ATS RC portal;
  if it exists there, ask the client data team to land it in Snowflake; if nowhere →
  unfeasible (No) and goes on the list.
- Historic timings (manual → assisted): lineage 1–3h (now minutes via the tool);
  used-columns/KPIs 5–6h manual with Tabular Editor, ~2–3h assisted (PBI MCP replaces
  this); Snowflake replacement mapping highly variable (Job Order tables took 2 days);
  full dashboard rewrite ~1 week.

## Deliverables
**Internal workbook**: Summary, Detailed, KPI catalogue (definition+DAX+SQL+ATS
implementation), Data Sources (lineage), Refinements changelog, Gaps & Open Questions.
Colour-code feasibility (green/amber/red). Reference internal sources freely.

**Client workbook (strict)**: Only Summary + Detailed. See FORMAT_SPEC.md next to this
skill for the full extracted spec (headers, widths, merges, boilerplate notes language);
still read the current reference workbook at runtime and match it EXACTLY (Messina Sans 10, header band #E5E8EE, data starts col B,
two-tier merged header: "Current Methodology" over {CRM Fields, Non-CRM/PROD_EDW
Fields}, "Updated Methodology" over ATS alternative; NO feasibility colour-coding;
"None" for empty cells; Bucket & Base Tables merged vertically on Detailed; page-
presence matrix keyed to report pages — ask for the PBIP/page list). Prefer editing a
copy of the reference file in place to preserve formatting. NEVER reference sources the
client hasn't seen (revamp dashboard, md files, internal packs) — attribute findings as
"analysis". Keep the paid note realistic (unreliable legacy-id link, future key).
Filename: `YYYYMMDD_KPIs_Feasibility_List_-_<Dashboard>_vX_Y_AC.xlsx` (confirm version).
Read the xlsx skill before building workbooks; validate (recalc → zero errors).

**Client communication style**: formal complete-sentence prose; open "We are sharing…";
ask "It would be great if you could…"; spell out "approximately"; benefit framing;
avoid "drivers", "further confirms", "configurable", "beyond". Concise, never fragmentary.

## Non-negotiables
- Strong verification only; unverifiable items → gap list. Questions over guesses.
- Power BI MCP strictly read-only, one model at a time, confirm connection first.
- On EB SharePoint touch nothing outside the AgentBridge (AK) folder.
- After each dashboard, append lessons to the transition-learnings memory
  (what surprised us, wrong assumptions, new cheat-sheet facts, process fixes).
