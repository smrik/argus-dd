# argus-dd

Deterministic FDD helper for Slovenian companies: trial balance → AOP mapping → AJPES cross-check → Excel databook. Background: `CONTEXT.md`, decisions: `docs/adr/`, external facts: `docs/research/`.

## Status
- `data/aop/gd_2024.csv`: full AOP tree of the AJPES company form, extracted and validated by `scripts/extract_aop_form.py`.
- `argus.synth`: synthetic companies (fake data). Produces multi-year pre-closing TBs that map exactly back to "filed" AOP statements, plus messy ERP-style exports for wrangling tests.
- `argus-wrangle`: messy export → tidy TB → longest-prefix chart rollup → AOP closing statements → filed AJPES cross-check, per year. Filings verify the TB; they never feed the mapping. Problems return exit 1.

## Run
```bash
uv sync
uv run pytest
uv run argus-synth --profile trading --seed 7   # writes out/synth/trading_seed7/
uv run argus-wrangle out/synth/trading_seed7/tb_2024_minimax_pdf.pdf --filed out/synth/trading_seed7/statements_filed.csv
```

Known limits:
- The TB is assumed to be pre-closing. A post-closing TB has its P&L konti at zero, so it cannot reproduce the income statement.
- Mapping uses the synthetic chart; shared konto groups still need reviewer judgement for real companies.
- PDF formats need xpdf 4.x `pdftotext` with `-table`. Set `PDFTOTEXT` to its executable (Windows: `C:\Program Files\Git\mingw64\bin\pdftotext.exe`).
- FURS hides zero-closing rows: closing statements remain recoverable, but opening/turnover checks can fail. Monthly exports recover closing and net movement only.
- All synthetic companies are profitable; loss scenarios are not covered yet.

Outputs per company: `tb_tidy.csv` (reference), `tb_<year>_erp.xlsx` and `tb_<year>_export.csv` (messy layouts), `statements_filed.csv` (cross-check target).
