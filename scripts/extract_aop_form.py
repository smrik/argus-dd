# /// script
# requires-python = ">=3.11"
# dependencies = ["xlrd==2.0.1"]
# ///
"""Extract the AOP tree from the AJPES company form (LPGD) into a CSV.

Usage:
    curl -L -o LPGD_2024_V1_6.xls https://www.ajpes.si/Doc/LP/Program/LPGD_2024_V1_6.xls
    uv run scripts/extract_aop_form.py LPGD_2024_V1_6.xls data/aop/gd_2024.csv

Reads sheets BS (balance sheet) and IPI (income statement). For every AOP row it
keeps the konto groups, the label, and the sum formula embedded in the label,
then validates the tree before writing anything.
"""

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import xlrd

SOURCE_URL = "https://www.ajpes.si/Doc/LP/Program/LPGD_2024_V1_6.xls"
SHEETS = {"BS": "balance_sheet", "IPI": "income_statement"}
COL_KONTO, COL_NUMBERING, COL_LABEL, COL_AOP = 0, 1, 2, 3

# A formula is a parenthesised group made only of 3-digit codes, + / - and "do" ranges.
# Mutually exclusive pairs: only one side is non-zero, chosen by the sign of the net amount.
PAIRS = {"068": "069", "070": "071", "121": "122", "151": "152", "182": "183", "186": "187"}
# Profit-side formulas of these pairs are already net (e.g. 151 = 126-127), so when expanding
# a total the loss side contributes nothing extra.
RESULT_LOSS_LINES = {"152", "183", "187"}
ROOTS = {"balance_sheet": ("001", "055"), "income_statement": ("186",)}
# Lines outside every total: off-balance items, memo lines, non-financial data.
OUTSIDE_TOTALS = {"054", "096", "154", "167", "188", "189"}

FORMULA_RE =re.compile(r"\(\s*(\d{3}(?:\s*(?:[+-]|do)\s*\d{3})*)\s*\)")
TERM_RE = re.compile(r"([+-]?)\s*(\d{3})(?:\s*do\s*(\d{3}))?")


def norm_code(value, width):
    """Cells hold '001' as text or 110.0 as float; return zero-padded text or None."""
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = str(int(value))
    value = str(value).strip()
    return value.zfill(width) if value.isdigit() else None


def norm_konto(value):
    if isinstance(value, float):
        return str(int(value)).zfill(2)
    return " ".join(str(value).split())


def parse_formula(text):
    """'(057+060-069)' -> [(+1,'057'), (+1,'060'), (-1,'069')]; 'do' ranges are expanded."""
    terms = []
    for sign, start, end in TERM_RE.findall(text):
        coef = -1 if sign == "-" else 1
        codes = range(int(start), int(end) + 1) if end else [int(start)]
        terms += [(coef, f"{c:03d}") for c in codes]
    return terms


def extract(xls_path):
    wb = xlrd.open_workbook(xls_path)
    rows = []
    for sheet, statement in SHEETS.items():
        sh = wb.sheet_by_name(sheet)
        for r in range(sh.nrows):
            cells = sh.row_values(r)
            aop = norm_code(cells[COL_AOP], 3)
            label = " ".join(str(cells[COL_LABEL]).split())
            # Skips non-data rows, incl. the column-number header row ("1 2 3 4 5").
            if aop is None or not re.search(r"[^\W\d_]", label):
                continue
            match = FORMULA_RE.search(label)
            formula = match.group(1).replace(" ", "") if match else ""
            rows.append({
                "statement": statement,
                "aop": aop,
                "numbering": str(cells[COL_NUMBERING]).strip(),
                "label": FORMULA_RE.sub("", label).strip() if match else label,
                "formula": formula,
                "konto_groups": norm_konto(cells[COL_KONTO]),
                "paired_with": PAIRS.get(aop) or next((p for p, l in PAIRS.items() if l == aop), ""),
            })
    return rows


def validate(rows):
    """Raise on any structural problem; return a short report."""
    by_aop = {}
    for row in rows:
        if row["aop"] in by_aop:
            raise ValueError(f"duplicate AOP {row['aop']}")
        by_aop[row["aop"]] = row

    for row in rows:
        for _, ref in parse_formula(row["formula"]):
            if ref not in by_aop:
                raise ValueError(f"AOP {row['aop']} references missing AOP {ref}")

    def leaves(aop, coef=1):
        """Signed leaf coefficients reached from aop by expanding formulas."""
        if aop in RESULT_LOSS_LINES:
            return {}
        terms = parse_formula(by_aop[aop]["formula"])
        if not terms:
            return {aop: coef}
        out = {}
        for c, ref in terms:
            for leaf, lc in leaves(ref, coef * c).items():
                out[leaf] = out.get(leaf, 0) + lc
        return out

    report = {}
    for statement, roots in ROOTS.items():
        reached = set()
        for root in roots:
            coefs = leaves(root)
            # Each leaf must be counted exactly once (+1 or -1) in each total.
            bad = {a: c for a, c in coefs.items() if abs(c) != 1}
            if bad:
                raise ValueError(f"AOP {root}: leaves counted more than once or cancelled: {bad}")
            report[root] = len(coefs)
            reached |= set(coefs)
        # Every amount line must feed a total, unless it is known to sit outside them.
        all_leaves = {r["aop"] for r in rows if r["statement"] == statement and not r["formula"]}
        orphans = all_leaves - reached - OUTSIDE_TOTALS - RESULT_LOSS_LINES
        if orphans:
            raise ValueError(f"{statement}: lines not in any total: {sorted(orphans)}")
    return report


def main(xls_path, csv_path):
    rows = extract(xls_path)
    report = validate(rows)

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    source = {
        "source_url": SOURCE_URL,
        "source_file": Path(xls_path).name,
        "sha256": hashlib.sha256(Path(xls_path).read_bytes()).hexdigest(),
        "rows": len(rows),
        "leaves_per_total": report,
    }
    csv_path.with_suffix(".source.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(source, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:3])
