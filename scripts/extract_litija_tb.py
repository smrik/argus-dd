# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract SVC Litija's FY2021 Minimax trial balance; validate before writing.

Usage:
    uv run scripts/extract_litija_tb.py data/tb_web/litija_bruto_bilanca.pdf data/tb_real/svc_litija_2021.csv
    # If xpdf is not on PATH, add --pdftotext PATH.

Use xpdf's -table mode: -layout shifts amounts between rows in this PDF.
Amounts stay in integer cents until the tidy CSV is formatted in EUR.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path

SOURCE_URL = "https://www.litija.si/DownloadFile?id=513027"
SHA256 = "812d44a635f10be6e02fe391b7acc2042b2e07ba26e2ec11c38e51da354196c7"
YEAR = 2021
GROSS_TOTALS = (1_359_061_963, 1_359_061_963, 887_548_459, 887_548_459, 2_246_610_422, 2_246_610_422)
CLOSING_TOTAL = 204_348_202
FIELDS = ("year", "konto", "name", "opening", "debit", "credit", "closing")
KONTO_RE = re.compile(r"[0-9]{1,7}")
AMOUNT_RE = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]{2}")
HEADERS = ("KONTO", "Bruto bilanca", "Temeljnice:", "Konti:", "Izpisano:", "Stran:", "www.minimax.si", "SVC")
NOTES = [
    "post-closing TB: P&L konti closed via razred 8; FY2021 loss 71.374,38 debit on 933",
    "class 99 = off-balance (izvenbilančno)",
    "no konto names in source",
    "totals rule (1-3 digit = total, 4+ digit = leaf) is specific to this Minimax export, verified by check (c)",
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse(text):
    rows, grand = [], None
    for line_no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(HEADERS):
            continue
        konto, *tokens = line.split()
        require(konto == "SKUPAJ" or KONTO_RE.fullmatch(konto), f"line {line_no}: unknown row {line!r}")
        require(all(AMOUNT_RE.fullmatch(t) for t in tokens), f"{konto}: malformed amounts {tokens}")
        require(len(tokens) in ((8,) if konto == "SKUPAJ" else (6, 7)), f"{konto}: wrong amount count {len(tokens)}")
        amounts = tuple(int(Decimal(t.replace(".", "").replace(",", ".")) * 100) for t in tokens)
        if konto == "SKUPAJ":
            require(grand is None, "duplicate SKUPAJ")
            grand = amounts
        else:
            require(grand is None, f"{konto}: data after SKUPAJ")
            rows.append((konto, amounts))
    require(grand is not None, "missing SKUPAJ")
    return rows, grand


def gross_sum(rows):
    return tuple(sum(a[i] for _, a in rows) for i in range(6))


def closing_sums(rows):
    nets = [a[4] - a[5] for _, a in rows]
    return sum(max(n, 0) for n in nets), sum(max(-n, 0) for n in nets)


def validate(rows, grand):
    require(len({k for k, _ in rows}) == len(rows), "(e) duplicate konti")
    for konto, a in rows:
        closing = a[4] - a[5]
        require(len(a) == (7 if closing else 6), f"(a) {konto}: KONCNO presence disagrees with net")
        require(not closing or a[6] == abs(closing), f"(a) {konto}: printed KONCNO disagrees with net")
    print(f"(a) PASS: printed KONCNO magnitude/presence, {len(rows)} rows")

    for konto, a in [*rows, ("SKUPAJ", grand)]:
        require(a[0] + a[2] == a[4] and a[1] + a[3] == a[5], f"(b) {konto}: gross cross-foot failed")
    print(f"(b) PASS: both gross sides cross-foot, {len(rows)} rows + SKUPAJ")

    # 4+ digit prefix matches are siblings, never totals, in this export.
    totals, leaves, short_leaves = [], [], []
    for index, (konto, a) in enumerate(rows):
        descendants = [(k, v) for k, v in rows if len(k) > len(konto) and k.startswith(konto)]
        if len(konto) >= 4 or not descendants:
            leaves.append((konto, a))
            if len(konto) < 4:
                short_leaves.append(konto)
            continue
        children = [(k, v) for k, v in descendants if len(k) == len(konto) + 1 or len(konto) == 3]
        require(children and gross_sum(children) == a[:6], f"(c) {konto}: next-level gross sums disagree")
        require(all(not k.startswith(konto) for k, _ in rows[:index]), f"(c) {konto}: total follows descendants")
        totals.append(konto)
    print(f"(c) PASS: {len(totals)} totals match next level on 6 columns; short leaves: {short_leaves}")

    require(grand[:6] == GROSS_TOTALS, "(d) unexpected printed gross totals")
    require(gross_sum(leaves) == grand[:6], "(d) leaf gross sums disagree with SKUPAJ")
    require(grand[6:] == (CLOSING_TOTAL, CLOSING_TOTAL), "(d) unexpected printed closing totals")
    # Minimax nets KONCNO per razred before summing, so compare against class rows, not leaves.
    require(closing_sums([r for r in rows if len(r[0]) == 1]) == grand[6:], "(d) razred closing sums disagree with SKUPAJ")
    print("(d) PASS: leaf gross sums and razred closing sums match printed SKUPAJ")

    require(sum(a[0] - a[1] for _, a in leaves) == 0, "(e) opening net is not zero")
    require(sum(a[4] - a[5] for _, a in leaves) == 0, "(e) closing net is not zero")
    require(all(a[4] == a[5] for k, a in rows if k[0] in "478"), "(e) P&L konto not closed")
    print("(e) PASS: opening/closing nets 0; unique konti; all P&L konti close at 0")

    require(len(rows) == 197 and len(leaves) == 95, f"(f) expected 197 rows/95 leaves, got {len(rows)}/{len(leaves)}")
    print("(f) PASS: 197 data rows, 95 leaves")
    return leaves, short_leaves


def eur(cents):
    return format(Decimal(cents) / 100, ".2f")


def main(pdf_path, csv_path, pdftotext="pdftotext"):
    pdf_path, csv_path = Path(pdf_path), Path(csv_path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    require(digest == SHA256, f"input sha256 mismatch: {digest}")
    # xpdf 4.06 exits 99 for -v despite successfully printing its version.
    version = subprocess.run([pdftotext, "-v"], capture_output=True, text=True, encoding="utf-8")
    version_text = (version.stdout + version.stderr).strip()
    require(version.returncode in (0, 99) and version_text.startswith("pdftotext version "), "cannot read pdftotext version")
    version_string = version_text.splitlines()[0]
    text = subprocess.run([pdftotext, "-table", str(pdf_path), "-"], check=True, capture_output=True, text=True, encoding="utf-8").stdout
    rows, grand = parse(text)
    leaves, short_leaves = validate(rows, grand)
    output = [(YEAR, k, "", *(eur(v) for v in (a[0] - a[1], a[2], a[3], a[4] - a[5]))) for k, a in sorted(leaves)]
    source = {
        "source_url": SOURCE_URL,
        "source_file": pdf_path.name,
        "sha256": digest,
        "pdftotext_version": version_string,
        "extraction_mode": "pdftotext -table",
        "data_rows": len(rows),
        "total_rows": len(rows) - len(leaves),
        "rows": len(leaves),
        "short_leaf_konti": short_leaves,
        "notes": NOTES,
    }
    source_text = json.dumps(source, indent=2, ensure_ascii=False) + "\n"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        writer.writerows(output)
    csv_path.with_suffix(".source.json").write_text(source_text, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("csv_path")
    parser.add_argument("--pdftotext", default="pdftotext")
    main(**vars(parser.parse_args()))
