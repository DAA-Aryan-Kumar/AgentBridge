# Client feasibility workbook — exact format spec
(extracted 2026-07-03 from 20260630_KPIs_Feasibility_List_-_Productivity_Analysis_v1_0_AC_1.xlsx;
if a newer reference file exists, re-verify against it — the reference file always wins)

Two sheets: `Summary`, `Detailed`. Gridlines hidden. Everything Messina Sans 10
(headers bold). Content starts at column B (col A = spacer, width ~3.9–4.4).
No freeze panes, no tab colors, NO feasibility colour-coding anywhere.

## Notes block (both sheets, B2:B8, row height 13.5, no fill/border)
- B2 bold: `Notes`
- B3: `1. The below-mentioned KPI list includes the key KPIs present in the <Dashboard> Dashboard, along with their initial KPI feasibility in CRM to ATS data transition assessment.`
- B4: `2. Feasibility is categorized into three types:`
- B5: `    Yes: Represents KPIs that can be transitioned from CRM to ATS data sources or do not have CRM dependency.`
- B6: `    Probable: Represents KPIs that are not directly available in ATS but can be derived using certain logic or indirect calculations.`
- B7: `    No: Represents KPIs that cannot be transitioned from CRM to ATS due to the unavailability of corresponding ATS equivalents.`
- B8: `3. This is an initial high-level draft of the feasible KPIs and will require further data validation, and exploration of CRM equivalents for accompanying filters at the individual visual level.`
- Row 9 blank.

## Summary sheet
- Row 10 group banner: E10:F10 merged = `Current Methodology`; G10 = `Updated
  Methodology`. Bold, fill FFE5E8EE, centered, thin borders. B10:D10 + H10 unfilled.
- Row 11 headers B–H: `KPI` | `Feasibility` | `Only CRM Dependency?` | `CRM Fields` |
  `Non-CRM / PROD_EDW Fields` | `Non-CRM / PROD_EDW /ATS Alternative` | `Notes`
- Data from row 12. Col widths: B=27, C=11.9, D=16, E=40, F/G default, H=55.
- Empty alternatives/notes = literal `None`.

## Detailed sheet
- Row 10 headers B–H: `Bucket` | `KPI` | `Feasibility` | `Base Tables` | `Logic` |
  `Additional Filters` | `Notes`
- Data from row 11. `Bucket` (B) merged vertically per group, centered. `Base Tables`
  (E) merged vertically per shared source, centered. Logic like
  `[# Placements Assigned] / [# Orders]`. Col widths: B=14, C=30, D=11.3, E=40,
  F=42, G=18, H=55.

## Cell formatting (both sheets, whole table incl. headers)
Thin borders all sides, color FFD0D0D0; header fill FFE5E8EE; data cells no fill;
alignment top + wrap text (merged Bucket/Base Tables cells centered vertically).
Data row height 26.4 default (taller where Notes wrap).

## Reusable Notes boilerplate (verbatim from shipped deliverable)
- Direct Yes: "Available directly from the ATS job record at finalization; analysis
  confirms a direct field equivalent."
- Paid metrics (Probable): "Paid metrics require linking ATS assignments to the
  financial (payroll and billing) data. The only link currently available relies on
  legacy identifiers carried over from CRM, whose coverage is incomplete and declining;
  analysis indicates it captures only a portion of paid associates, so the metric is
  feasible but not yet reliable until a dedicated ATS-to-financial key is in place."
- No CRM dependency: "Sourced from billing data with no CRM dependency, and is
  therefore unaffected by the migration."
- No: "ATS captures job orders at finalization rather than at creation, so
  creation-time and on-time metrics cannot currently be reproduced."
