---
topic: AJPES data sources and AOP codes
researched: 2026-10-10
status: partly verified (see Open)
---

# AJPES: data access and AOP codes

Rule: take AOP codes only from AJPES primary docs. Web/LLM summaries returned wrong codes.

## Sources
- Developer page: https://www.ajpes.si/za_razvijalce_programske_opreme
  - 7.2.3: public/statistics data structures (`Struktura_gospodarstvo_javna_objava_2025.pdf`)
  - 7.3: LP API manual (`LP_API_LP_ZP_kapitalske_druzbe_v_5.10.2026.pdf`)
  - 8.3: ProFiPo structures (`Struktura_standardnega_izbora_podatkov_2024.pdf`)
- Full AOP form (company): https://www.ajpes.si/Doc/LP/Program/LPGD_2024_V1_6.xls
- Control formulas: https://www.ajpes.si/Drugo/Aplikacije/Letna_porocila/2024/kontrole
- JOLP (free web view, last 5 years): https://www.ajpes.si/jolp/default.asp

## LP API
- Base `https://wwwa.ajpes.si/api/v1`. GET only. Header `X-Api-Key`.
- Key: register on AJPES, then email cpu.it@ajpes.si. Keep it in `.env`; never commit it.
- Swagger: `/api/q/swagger-ui/`. OpenAPI: `/api/q/openapi`. Both work without a key.
- `GET /subjekti/{maticna10}`: manifest of reports, current year + previous 5.
  - Add `leto`, `format`, `identifikatorVira` to fetch one item.
  - `format=json` returns structured figures. Only for `vrstalp=01`.
  - `format=pdf|xml|xhtml|zip` returns the raw document; `format=base64` returns it in JSON (max 10 MiB).
- `GET /masovni-prenosi`: bulk ZIP catalog.
  - `/letni/{leto}` and `/letni/{leto}/deli/{n}`: last 4 closed years.
  - `/mesecni/{leto}/{01-13}`: monthly packages.
  - `/popravki`: latest corrections package.
- Rate limits per key: 100/min standard, 60/min documents, 5/h bulk.
- Coverage: capital companies only (VRORG 103, 104, 105, 117, 351, 352). No s.p.
- Licence: CC BY 4.0. Cite "Vir: AJPES".

## Data limits
- The public set is about 89 lines per year (current + prior year). Full AOP detail (001–216) is statistics data, given only to authorised bodies.
- So QoE, NWC and net debt must come from the target's TB/GL. AJPES is for reconciling to filed figures and for peer benchmarks.

## Key AOP (company form, SRS 2024; source: javna objava 2025 structure)
| Item | AOP | Item | AOP |
|---|---|---|---|
| Total assets | 001 | Net sales | 110 |
| Long-term assets | 002 | Change in inventories | 121−122 |
| Intangibles + LT deferred costs | 003 | Own work capitalised | 123 |
| PP&E | 010 | Other operating income | 124+125 |
| Investment property | 018 | Cost of goods, materials, services | 128 |
| LT financial investments | 019 | Services | 134 |
| Short-term assets | 032 | Labour costs | 139 |
| Inventories | 034 | Wages | 140 |
| ST financial investments | 040 | Write-downs | 144 |
| ST operating receivables | 048 | D&A | 145 |
| Cash | 052 | Other operating expenses | 148 |
| Equity | 056 | Fin. expense on financial liabilities | 169 |
| Share capital | 058 | Other income / other expenses | 178 / 181 |
| Provisions + LT deferred income | 072 | Income tax / deferred tax | 184 / 185 |
| LT liabilities | 075 | Net result | 186−187 |
| LT financial liabilities | 076 | Avg. employees (by hours) | 188 |
| LT operating liabilities | 080 | Months of operation | 189 |
| ST liabilities | 085 | | |
| ST financial liabilities | 087 | | |
| ST operating liabilities | 091 | | |
| Total liabilities and equity | 055 (= 001) | | |

Operating profit (EBIT) is 151 − 152 in the full form. It is absent from the narrow public set. EBITDA appears only as a ProFiPo indicator (K0007).

## Full AOP form (verified, extracted)
- `data/aop/gd_2024.csv` comes from LPGD_2024_V1_6.xls (sha256 in `gd_2024.source.json`). It is produced by `scripts/extract_aop_form.py`, which validates the tree: every line is counted exactly once in 001, 055 and 186.
- The balance sheet covers 001–096 plus 301; the income statement covers 110–189.
- The `Konto` column gives 2-digit konto groups per AOP, often marked "del" (only part of the group). So it shows which groups may feed a line, not a full konto→AOP mapping.
- Mutually exclusive pairs (one side non-zero, chosen by sign): 068/069, 070/071, 121/122 (increase/decrease), 151/152, 182/183, 186/187.
- Memo lines outside the totals: 154 (interest income) and 167 (interest expense), both already included elsewhere. Also 188 (employees), 189 (months) and 054/096 (off-balance-sheet items).

Known control rules (a subset is implemented in `argus.checks.check_ajpes_controls`):
- 055 = 001
- 121 and 122 are mutually exclusive
- 070 and 071 are mutually exclusive
- 140 > 0 ⇔ 188 > 0

## Open
- [ ] The API's `postavke` keys T001–T089 are not raw AOP codes. They are row indices of a selection structure: either javna-objava zapst 01–89 or ProFiPo compact numbering (e.g. cash = T018). Settle with one real call compared against the JOLP PDF before writing any mapping code.
- [ ] Do d.n.o. and k.d. fall outside the API coverage?
- [ ] Did AOP numbering stay stable from 2021 to 2025 (SRS 2016 → SRS 2024)? Diff the yearly structure PDFs.
- [x] 3-digit konti: located 2026-10-11. SEPS "Priporočeni enotni kontni načrt za gospodarske družbe, samostojne podjetnike in kmetije" and the official ENOTNI KONTNI NAČRT (Priloga 1 k SRS 2024, Uradni list RS 81/2024). Downloaded in `data/tb_web/`, see `docs/research/tb-sources.md`. `data/chart/` remains synthetic until this is extracted.
- [ ] Carried-forward losses: the AJPES control "if 070 > 0, then 069 + 071 = 0" suggests a current-year profit is netted against carried losses in the filed figures. If so, filed 070 can differ from net P&L (186 − 187), which would break the TB cross-check. Verify against ZGD-1/SRS before encoding it. The synthetic profiles are currently always profitable, so this path is untested.
- [x] Parse `LPGD_2024_V1_6.xls` into the full AOP tree (see "Full AOP form").
