# 0003: Databook uses live Excel formulas

Date: 2026-10-09 · Status: accepted

## Context
Reviewers trust Excel because they can trace any cell. Hard-coded values look like a black box and can't be customised easily (ADR 0002).

## Decision
- Analyses in the databook are written as live formulas (SUMIFS / structured references to data tables), not as pasted values.
- Code also computes every analysis independently. After generation, the workbook is recalculated and every formula result must equal the code result. This is an automatic tick and tie.

## Consequences
- A recalculation engine is needed (e.g. LibreOffice headless or Excel via xlwings). openpyxl writes formulas but does not calculate them.
- If a user edits the workbook (mapping, adjustments), the PowerPoint export must read the recalculated workbook values, not the code's cached results.
- Performance: large GLs are aggregated to the mapping level in code, and the formulas run over those aggregated tables.

## Open problem: regenerating after edits
Clients re-send TBs often. Regenerating the databook must not wipe out reviewer edits (mapping overrides, adjustments, commentary tweaks). Candidate approaches, undecided:
- Keep user edits on dedicated input sheets (overrides and adjustments) that the generator never overwrites. Generated sheets are read-only by convention.
- Diff the old and new workbook and surface conflicts for the reviewer.
- Store the mapping and adjustments outside the workbook (e.g. YAML/CSV) and re-import them on each run.
