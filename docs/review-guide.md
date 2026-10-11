# Review guide

Lay of the land for reviewing argus-dd, and PR #15 in particular. Background: `CONTEXT.md` (terms), `docs/adr/` (decisions), `docs/research/` (verified external facts).

## Data flow

```
synth.generate ──► TbRow lists + filed AOP statements      (fake company, exact by construction)
      │
      ▼
layouts.write_all ─► tb_tidy.csv, statements_filed.csv
      │             exports.*: messy files + <file>.truth.csv + manifest.json
      ▼
wrangle.wrangle ──► Wrangled(rows, dropped, problems)      (reads file CONTENT only)
      │
      ▼
mapping.rollup ───► chart konti (longest prefix)
      │
      ▼
mapping.statements_from_tb ─► AOP statements
      │
      ▼
checks.cross_check ─► differences vs filed figures        (verification only, never an input)
```

Real data enters at `wrangle` too: `data/tb_web/litija_bruto_bilanca.pdf` → `data/tb_real/svc_litija_2021.csv`.

## Modules (src/argus)

| File | Lines | Role | Review priority |
|---|---|---|---|
| `wrangle.py` | 511 | messy file → tidy TB; format/year detection; `classify()` total detection | **high** |
| `exports.py` | 340 | renders synthetic TBs as fake Minimax/Analitika/FURS/xlsx/csv exports | medium (fixtures only) |
| `mapping.py` | 50 | `rollup` (new), konto → AOP | high, short |
| `checks.py` | 116 | TB checks, `load_filed` + `cross_check` (new), AJPES controls | high, short |
| `pdf.py` | 24 | finds an xpdf `pdftotext` that supports `-table` | low |
| `synth.py`, `aop.py`, `chart.py`, `layouts.py`, `tb.py` | | already on `main`, unchanged in substance | skip |

Scripts: `scripts/extract_litija_tb.py` is a one-off extractor for the real Litija PDF, with independent checks (a)–(f). It's already on `main`.

## Suggested reading order for PR #15 (~1–2 h)

1. **The PR description and `git log main..pipeline`**: 3 feature commits plus this guide.
2. **`mapping.rollup` and `checks.cross_check` / `MEMO_AOPS`**: short, and the end of the pipeline. Ask: is skipping memo lines 154/167 right? (They're "od tega" interest lines; a konto-level TB can't split them out.)
3. **`tests/test_pipeline.py::test_pipeline`**: the main claim. Every export format → wrangle → rollup → map gives the filed statements.
4. **`wrangle.py` top to bottom, except `classify()`**: `cents()` (amount parsing), `read_pdf_lines` (PDF row parsing), `read_table` (xlsx/csv), `wrangle_all` (format detection).
5. **`classify()` (wrangle.py:71–229)**: the hard part. It's a data-driven placeholder for issue #3, so read it to judge the *approach*, not to polish it.
6. **`tests/test_wrangle.py`**: check that the tests could actually fail (fixtures are copied to neutral names; constructed tie cases).

## Where to be suspicious

- **Circularity.** Fixtures and wrangler were written by the same agents. Guardrails: the wrangler never reads `manifest.json`, truth files or filenames, and tests copy inputs to `input.pdf` etc. Spot-check that `wrangle.py` has no `len(code)` rule for totals.
- **`classify()` complexity.** Bounded search (4096 states), with ambiguity reported as problems. It works on fixtures and on Litija, but **hits the limit on the real FURS file (Kočevje)**. See #3 for the evidence and the proposed switch to per-format declared levels.
- **Amount parsing.** Must be Decimal only and exactly 2 decimals. It must handle trailing minus, parentheses and NBSP, and reject `1.234` and `1,234.56`.
- **Synthetic ≠ real.** reportlab PDFs extract cleanly; real exports can push amounts onto the wrong line under `pdftotext -table` (see the Analitika notes in `docs/research/tb-sources.md`).
- **Exit codes.** `argus-wrangle` exits 1 on *any* problem, including FURS hidden rows, even when the cross-check is OK. That's intended (see #4).

## Trust levels

| Claim | Evidence |
|---|---|
| Synthetic exports round-trip exactly | `test_exports.py`, `test_wrangle.py::test_fixtures` |
| Pipeline reproduces filed statements | `test_pipeline.py` (3 companies × 8 formats) |
| Real Minimax TB extracted correctly | `scripts/extract_litija_tb.py` checks (a)–(f), plus the wrangler reproduces it without the digit rule |
| Real Analitika TB | **not clean**: 308 rows / 16 problems, documented |
| Real FURS TB (Kočevje) | **fails**: parse errors and the classification limit (#3) |
| Mapping to AOP for real companies | **not done**: the chart is synthetic (#5, #6) |

## Run it

```bash
uv sync
uv run pytest -q tests
uv run argus-synth --profile trading --seed 7
uv run argus-wrangle out/synth/trading_seed7/tb_2024_minimax_pdf.pdf --filed out/synth/trading_seed7/statements_filed.csv
```

PDF tests and formats need xpdf 4.x `pdftotext` (has `-table`). In PowerShell, TeX Live's `pdftotext` comes first on PATH and lacks it, so:

```powershell
$env:PDFTOTEXT = 'C:\Program Files\Git\mingw64\bin\pdftotext.exe'
```

Without it, the PDF tests skip (they don't fail). Open the files in `out/synth/trading_seed7/` to see what each fake export looks like next to its `.truth.csv`.

## Open decisions (yours)

- #3: total detection, data-driven vs per-format declared levels (blocks real-world reliability)
- #4: FURS hidden zero-closing rows, fail or accept closing-only
- #5: SIR company chart copyright (the PDFs are already in the public repo)
- #13: repo visibility and licence
