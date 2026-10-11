# Context: argus-dd

Tool for FDD (financial due diligence) teams, Slovenia first. Turns client data into an Excel databook and PowerPoint slides, deterministically. See `docs/adr/`.

## Terms
- **Dataset**: tabular client input with dimensions and amounts over periods. Examples: trial balance (TB), fixed asset register (FAR), AR ageing, payroll. Year-end TBs are typical.
- **Wrangling**: reshaping usable but untidy client exports into a tidy dataset (one row per account × period). Typical problems: months as columns, multi-row headers, subtotals mixed into the data, code and name in one cell, one sheet per period. This is not cleaning; the data is correct, just shaped wrong. Checks on a wrangled TB:
  - Opening and closing each sum to 0.
  - Each account appears once per period (catches duplicates).
  - Opening + debit − credit = closing for every account.
  - Every row maps to a konto (catches total and subtotal rows, which net to 0 and pass the sum check).
  - Closing of year N = opening of year N+1 for balance-sheet konti. The current-year result konto opens with last year's net P&L, and P&L konti open at 0.
  - Post-closing TB: net P&L = current-year result in equity (070/071). Pre-closing TB: net assets − equity excluding the current-year result = net P&L.
  - After mapping: matches AJPES totals at FY end (cross-check).
- **Mapping**: assigns dataset rows to a reporting structure. For a TB: konto → AOP line. The AJPES form gives only 2-digit konto groups per AOP, often marked "del" (shared between lines). Splitting a shared group is a judgement, or a user override. Paired lines (e.g. 070/071) are chosen by the sign of the amount.
- **AOP**: line code in the AJPES standardised financial statements (SRS 2024). See `docs/research/ajpes.md`.
- **Cross-check**: comparison of the TB rolled up at FY end against the AOP figures filed with AJPES. Used only for verification, never as an input.
- **Analysis**: deterministic computation over a dataset (group-by over dimensions × periods → change, share, bridge, rank).
- **Layout**: one of the standard slide types (table + chart + commentary). Provisional set:
  1. Trend: table over periods + bar chart
  2. Mix: composition, stacked bars or share %
  3. Bridge: waterfall (e.g. EBITDA → adjusted EBITDA, opening → closing NWC)
  4. Top-N: concentration (customers, suppliers, assets)
  5. KPI summary: headline figures + short commentary
- **Commentary**: descriptive text on a layout. Code computes the numbers; the LLM may only phrase them; every number is checked against the data.
- **Databook**: the Excel workbook holding datasets, mappings and analyses. The system of record. Analyses are live formulas, cross-verified against code (ADR 0003).
- **Judgement**: a small LLM-made decision (e.g. a classification), always marked for reviewer attention.

## Avoid
- "AI slides" or "generated report" to describe the product. Say workflow/tool.
