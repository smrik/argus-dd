# Downloads real trial-balance (TB) files publicly exposed on Slovenian websites,
# plus official chart-of-accounts references, into data/tb_web/ with a manifest.
# Purpose: real-world test inputs for TB wrangling/mapping (see docs/research/tb-sources.md).
# Run: pwsh -File scripts/harvest_tb_web.ps1
$ErrorActionPreference = 'Stop'
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
$dest = Join-Path $PSScriptRoot '..' 'data' 'tb_web'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$files = @(
  @{ file = 'slovenijavgibanju_bruto_bilanca_2020.pdf';     url = 'https://www.slovenijavgibanju.si/datoteke/bruto_bilanca_2020.pdf';                                                                                             note = 'Analitika 1 software bruto bilanca export, s.p./company chart, FY2020. Same file also exposed at arhiv.sportna-unija.si, www.vetervlaseh.si, www.zdravjuprijaznaorganizacija.si (/datoteke/bruto_bilanca_2020.pdf).' },
  @{ file = 'kocevje_priloga1_bruto_bilanca_2018.pdf';      url = 'https://www.kocevje.si/files/other/news/66/182962Priloga%201%20-%20Bruto%20bilanca.pdf';                                                                            note = 'Municipality-published bruto bilanca (predizdelana), 2018, budget-user chart.' },
  @{ file = 'razvoj_podezelja_4_bilanca_2023.pdf';         url = 'https://razvoj-podezelja.si/images/02_pdf/15zbor/4_Bilanca_2023.pdf';                                                                                          note = 'NGO (društvo) zbor assembly pack bilanca, 2023, društvo chart.' },
  @{ file = 'razvoj_podezelja_bruto_bilanca_drpsn_2023.pdf'; url = 'https://razvoj-podezelja.si/images/02_pdf/16zbor/03_bruto_bilanca_DRPSN_2023.pdf';                                                                              note = 'NGO (društvo) bruto bilanca "na dan 31.12.23", konto-level, društvo chart.' },
  @{ file = 'litija_bruto_bilanca.pdf';                     url = 'https://www.litija.si/DownloadFile?id=513027';                                                                                                                note = 'Municipality (Občina Litija) "Bruto bilanca" file.' },
  @{ file = 'fotoklub_maribor_analiticna_bruto_bilanca_2019.pdf'; url = 'https://www.fotoklub-maribor.si/klub/wp-content/uploads/sites/2/2020/05/Analiti%C4%8Dna-bruto-bilanca-2019-1.pdf';                                             note = 'Club analytical bruto bilanca, 2019.' },
  @{ file = 'posvet_financno_porocilo_2025.pdf';            url = 'http://posvet.org/wp-content/uploads/2026/02/Financno-porocilo-2025.pdf';                                                                                   note = 'Slovenian-language financial report incl. bruto bilanca (prihodki/odhodki).' },
  @{ file = 'kamnik_velika_planina_pregled.pdf';            url = 'https://www.kamnik.si/DownloadFile?id=448234';                                                                                                                note = 'Municipal review of accounting information of company (družba Velika planina).' },
  @{ file = 'piramida_gkw_frp_razkritje.pdf';               url = 'https://www.piramida-lj.si/media/uploads/documents/GKW-FRP_Financno%20razkritje%20podatkov.pdf';                                                              note = 'Piramida software sample "Glavna knjiga" FRP financial-disclosure export; layout reference.' },
  @{ file = 'ijs_glavna_knjiga_navodilo.pdf';              url = 'https://ijs.si/ijsw/IJSvision_Navodila_Uprava?action=AttachFile&do=get&target=Finance_1_Poglavje_5_Glavna_knjiga_1.2.pdf';                                      note = 'IJS (Institut Jožef Stefan) internal glavna knjiga instructions; layout reference.' },
  @{ file = 'seps_kontni_nacrt_gd.pdf';                     url = 'https://seps.si/wp-content/uploads/2025/02/Kontni-nacrt-za-gospodarske-druzbe-1.pdf';                                                                       note = 'SEPS Priporočeni enotni kontni načrt za gospodarske družbe (company 3-digit chart); closes ajpes.md open item on official chart.' },
  @{ file = 'sirevizija_enotni_kontni_nacrt_2024.pdf';      url = 'https://si-revizija.si/datoteke/standardi/3280/enotni-kontnii-nacrt-2024.pdf';                                                                               note = 'Priporočeni enotni kontni načrt 2024 revision (si-revizija.si copy).' },
  @{ file = 'uradni_list_srs2024_priloga1_kontni_nacrt.pdf'; url = 'https://www.uradni-list.si/files/RS_-2024-081-02384-OB~P001-0000.PDF';                                                                                       note = 'Official ENOTNI KONTNI NAČRT, Priloga 1 to SRS 2024 (Uradni list RS 2024-81).' }
)

$manifest = @()
foreach ($f in $files) {
  $out = Join-Path $dest $f.file
  try {
    Invoke-WebRequest -Uri $f.url -OutFile $out -UserAgent $ua -UseBasicParsing -TimeoutSec 60
    $sha = (Get-FileHash -Path $out -Algorithm SHA256).Hash.ToLower()
    $len = (Get-Item $out).Length
    $manifest += [ordered]@{ file = $f.file; url = $f.url; sha256 = $sha; bytes = $len; note = $f.note }
    Write-Host "OK  $($f.file) ($len bytes)"
  } catch {
    Write-Host "ERR $($f.file): $($_.Exception.Message)"
    if (Test-Path $out) { Remove-Item $out }
  }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $dest 'tb_web.sources.json') -Encoding utf8
Write-Host "Manifest: data/tb_web/tb_web.sources.json ($($manifest.Count) files)"
