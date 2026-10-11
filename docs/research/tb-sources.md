---
topic: Publicly exposed Slovenian trial balances (web harvest)
researched: 2026-10-11
status: verified (files downloaded, spot-checked by text extraction)
---

# Real TBs exposed on the Slovenian web

Hypothesis: some Slovenian firms/institutions publish real trial balances (bruto
bilanca, glavna knjiga) on public websites, deliberately (meeting packs) or
accidentally (leftover exports). **Confirmed.** Downloaded set:
`data/tb_web/` (manifest: `tb_web.sources.json`, sha256 per file; harvested by
`scripts/harvest_tb_web.ps1`).

## What was found (verified konto-level TBs)

| File | Entity type | Chart | Notes |
|---|---|---|---|
| `litija_bruto_bilanca.pdf` | d.o.o. (SVC Litija, komunalno podjetje) | company, konto+subkonto (0, 002, 00201, 04, ...) | FY2021, Breme/Dobro promet + začetno/končno. Only real gospodarska družba TB found. Source: obcina Litija DownloadFile?id=513027 |
| `kocevje_priloga1_bruto_bilanca_2018.pdf` | indirect budget user (zavod) | POPRS/budget, 6-digit analitična konta (003100) + groups | FURS "predizdelana bruto bilanca", konto names included. Source: kocevje.si |
| `slovenijavgibanju_bruto_bilanca_2020.pdf` | s.p./demo data (Dragica Žunko) | company | Analitika 1 software export. Same file exposed on 4 domains: slovenijavgibanju.si, arhiv.sportna-unija.si, vetervlaseh.si, zdravjuprijaznaorganizacija.si (`/datoteke/bruto_bilanca_2020.pdf`) |
| `razvoj_podezelja_bruto_bilanca_drpsn_2023.pdf` | društvo | društvo chart | "BRUTO BILANCA NA DAN 31.12.23", zbor assembly pack. Source: razvoj-podezelja.si/images/02_pdf/16zbor/ |
| `razvoj_podezelja_4_bilanca_2023.pdf` | društvo | društvo chart | Same zbor pack, 15zbor/ |
| `fotoklub_maribor_analiticna_bruto_bilanca_2019.pdf` | društvo/klub | 3+4-digit konti + naziv | Source: fotoklub-maribor.si |
| `posvet_financno_porocilo_2025.pdf` | zveza/zavod | 3+4-digit konti + opis (4020, 4030...) | "Bruto bilanca - samo prihodki in odhodki", FY2025. Source: posvet.org |

Reference/layout files (not real-firm TBs): `kamnik_velika_planina_pregled.pdf`
(ISRS 4400 review of a d.o.o., incl. accounting info), `piramida_gkw_frp_razkritje.pdf`
(Piramida software sample GK disclosure), `ijs_glavna_knjiga_navodilo.pdf` (IJS internal GK manual).

## Extraction gotchas (verified 2026-10-11)

- `pdftotext -layout` scrambles these exports: names/amounts drift one row (Litija, Kočevje, fotoklub). Use `pdftotext -table` (xpdf 4.06): rows stay aligned. xpdf build has no `-bbox`.
- `razvoj_podezelja_*.pdf`: scanned JPEG pages (200 dpi), no text layer. OCR needed; skipped.
- Litija (Minimax): totals only at 1–3 digits (razred/skupina/sintetični konto). All 4+ digit konti are leaves even when one prefixes another (1100 + 11001 = 110; 9010 + 90100 = 901). Prefix-as-parent breaks sums (opening off by 6.86M). With 1–3-digit rule: 197 rows → 95 leaves; opening, promet, končno each net 0.00; začetno + promet = skupaj on every row; every total = sum of next level; no duplicates.
- Litija: ZAČETNO/PROMET/SKUPAJ always print both sides (0,00 when empty); KONČNO prints one side only → infer side from sign of SKUPAJ B − D. Grand-total SKUPAJ KONČNO (2.043.482,02 each side) = razred-level nets summed by side, NOT leaf closings summed by side (8.471.368,41). Gross columns do equal leaf sums.
- Tidy extraction: `scripts/extract_litija_tb.py` → `data/tb_real/svc_litija_2021.csv` (+ `.source.json`), validated (KONČNO side, cross-foot, totals = next level, leaves = SKUPAJ).
- Litija is post-closing: P&L konti (4, 7) closed via razred 8 (80, 89); FY2021 loss 71.374,38 sits debit in 933. Class 99 = off-balance (izvenbilančno, 990/995 net 0).
- `kamnik_velika_planina_pregled.pdf`: has konto × Jan–Dec tables (months-as-columns wrangling case).
- Športna unija (Analitika): konto names wrap onto a second line with no code; 1 Saldo column split DB/KR.
- Analitika 1 (`slovenijavgibanju_bruto_bilanca_2020.pdf`, local `pdftotext -table`): leaves print Otvoritev DB/KR + Promet DB/KR (4 amounts), then one Saldo side when nonzero (5 amounts). `0030`: `0,00 0,00 972,34 0,00 972,34`; `0080`: `0,00 0,00 0,00 15,66 15,66` (credit); `0860`: `2.763,01 0,00 0,00 2.763,01` (blank Saldo).
- Analitika totals follow children; 3-digit `003` prints the same 5 amounts plus Razlika `972,34 D`; `008` ends `15,66 K`. Mixed-side totals (`975`, razredi) print both Saldo sides plus net Razlika + D/K (7 amounts). Zero total `086` prints 4 amounts + Razlika `0,00` without D/K. Grand `SKUPAJ` prints 6 gross amounts; separate `SKUPAJ saldo` is a net summary. No digit-length rule used for total classification.
- Analitika names wrap on code-free lines (`03506`, `76802`, `9320`); usually all amounts stay on the code line. Exceptions under `-table`: `4800` Saldo `16.503,76` lands on the preceding wrapped total-name line; `7690` movement/Saldo land on preceding `PREMIJE.....)` line; `9680` first line has preceding `SREDSTEV` + 3 amounts, next line has its name + opening DB/Saldo. Do not silently join these displaced amounts.
- Analitika content traps: decimal percentages in names (`16001`: `8,5 %`; `9670`: `0,0641 %`) trip amount-suffix parsing; left-margin `Registriran uporabnik: ...` prefixes hide some konto/total rows; address `1000 LJUBLJANA` is currently reported as an invalid account line. These are unresolved extraction/parser issues, not proven ledger errors.
- Analitika smoke (2026-10-11, same real PDF): before 0 rows / 316 problems (220 wrong counts; 92 unparsed suffixes; 1 no amount tokens; 1 no rows; 1 global classification; 1 grand-total mismatch). After one-sided Saldo + labelled Razlika parsing: 308 rows / 16 problems (2 wrong counts; 2 unparsed suffixes; 1 no amount tokens; 1 printed Saldo mismatch; 5 bounded-classification limits; 1 global classification; 1 grand-total mismatch; 2 balance sums; 1 row cross-foot). Unresolved totals remain among extracted rows; this is not a clean leaf TB. Saldo mismatch/cross-foot on `4800` follows the displaced amount above; reconciliation cannot certify this extraction.
- Generic numeric-konto Excel imitation (issue #8, no web source): INT cells lose `0400` → `400`, `04001` → `4001`; content alone cannot recover zeros. Wrangler preserves numeric codes as `str(int(cell))`, warns once per sheet, leaves repair to user judgement. Truth retains original codes; excluded from clean mapping/cross-check fixtures.

## Official company chart — located (closes ajpes.md open item)

- SEPS Priporočeni enotni kontni načrt za gospodarske družbe, samostojne podjetnike in kmetije: `seps_kontni_nacrt_gd.pdf` (seps.si, 2025) and 2024 revision `sirevizija_enotni_kontni_nacrt_2024.pdf` (si-revizija.si/datoteke/standardi/3280/).
- CORRECTION (2026-10-11): `uradni_list_srs2024_priloga1_kontni_nacrt.pdf` (Uradni list RS 81/2024, uradni-list.si/files/RS_-2024-081-02384-OB~P001-0000.PDF) is the **budget-users chart** (proračun, proračunski uporabniki: "sredstva v upravljanju", 90 = splošni sklad), not the company chart. It matches the Kočevje TB, not d.o.o. TBs. Filename is misleading.
- Company chart = SIR "Priporočeni enotni kontni načrt" (recommended, not binding): 2015 version `seps_kontni_nacrt_gd.pdf`, 2023 revision (adopted 15.11.2023) `sirevizija_enotni_kontni_nacrt_2024.pdf`. Column "Uporablja" marks applicability (D d.o.o./d.d., P s.p., Z zadruge, N neprofitne, DI društva). Matches Litija (90 vpoklicani kapital, 93 čisti poslovni izid, 80 poslovni izid).
- Copyright: both SIR PDFs state SIR holds the rights; copying/distribution for commercial purposes without written permission is prohibited. Extracting the chart into the repo needs an owner decision (issue #5).
- The chart in `data/chart/` is still synthetic.

## Where TBs are published (finding patterns)

- Deliberate: društva/zavodi assembly (zbor) packs and meeting annexes; municipality-published zavod packs ("priloga – bruto bilanca", "predizdelana bruto bilanca" from FURS); municipal company review reports.
- Accidental: accounting-software exports left in web roots by web agencies/accountants (e.g. `/datoteke/bruto_bilanca_2020.pdf` on the Sportna unija portal family — one accountant, 4 domains).
- Not found: tender documentation (eNaročanje) with company TBs — plausible but unproven.

## Search method (repeatable)

- Engines: DDG html and Google (Google result links need `/goto?url=` resolution by navigation; DDG rate-limits after ~2 calls, use gaps).
- Productive queries: `"bruto bilanca" filetype:pdf site:si`, `"analitična bruto bilanca"`, `"bruto bilanca" priloga obcina`, `"glavna knjiga" "dnevnik knjiženja" filetype:pdf`, export signatures ("Iskanje tečaja", "Datum obdobja knjiženja", "BRUTO BILANCA NA DAN", "Bruto bilanca - Analitika").
- Path probing works when a file is found (year variants, sibling zbor dirs) but most exposures are one-off uploads.
- `scripts/harvest_tb_web.ps1` re-downloads the current set and rebuilds the manifest.

## Open

- [x] SVC Litija → tidy dataset (see Extraction gotchas).
- [ ] Kočevje, Športna unija → tidy datasets; SVC Litija FY2021 AJPES cross-check once real chart lands.
- [ ] Extract SEPS/uradni-list chart into `data/chart/` replacing the synthetic chart (label provenance).
- [ ] d.o.o. TBs beyond municipal companies: try eNaročanje tender docs; SVC Litija was found via a municipality DownloadFile link, so crawl občina sites' "sklepi"/"nadzorni odbor" sections.
- [ ] Verify whether predizdelana bruto bilanca files (FURS) are systematically published by občine; if so, that is a reliable source of budget-user-chart TBs.
