# argus-dd

Deterministic FDD helper for Slovenian companies: trial balance → AOP mapping → AJPES cross-check → Excel databook. Background: `CONTEXT.md`, decisions: `docs/adr/`, external facts: `docs/research/`.

## Status
- `data/aop/gd_2024.csv`: full AOP tree of the AJPES company form, extracted and validated by `scripts/extract_aop_form.py`.
- `argus.synth`: synthetic companies (fake data). Produces multi-year pre-closing TBs that map exactly back to "filed" AOP statements, plus messy ERP-style exports for wrangling tests.

## Run
```bash
uv sync
uv run pytest
uv run argus-synth --profile trading --seed 7   # writes out/synth/trading_seed7/
```

Known limits:
- The TB is assumed to be pre-closing. A post-closing TB has its P&L konti at zero, so it cannot reproduce the income statement.
- Mapping needs exact 3-digit konti. Real TBs use sub-accounts (1200, 12000…), so prefix mapping comes first for real data.
- All synthetic companies are profitable; loss scenarios are not covered yet.

Outputs per company: `tb_tidy.csv` (reference), `tb_<year>_erp.xlsx` and `tb_<year>_export.csv` (messy layouts), `statements_filed.csv` (cross-check target).
