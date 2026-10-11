"""Content-driven TB extraction. wrangle_all always returns {year: Wrangled}.

wrangle unwraps single-year inputs; multi-year workbooks/CSVs return that dict.
Amounts and classification use integer cents throughout.
"""

import argparse
import csv
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from openpyxl import load_workbook

from argus.checks import check_tb
from argus.pdf import pdf_lines
from argus.tb import TbRow

FIELDS = ("opening", "debit", "credit", "closing")
NUMBER = re.compile(r"(?<![\w.,])\(?-?\d+(?:(?:[. \u00a0\u202f])\d{3})*,\d+\)?-?(?![\w.,])")
CODE = re.compile(r"^(\d+)(?:\s+-?\s*(.*))?$")


@dataclass(frozen=True)
class Wrangled:
    format: str
    rows: list
    dropped: list
    problems: list
    net_only: bool
    year: int


@dataclass(frozen=True)
class Printed:
    """A numeric konto or a label total, with its source line/sheet reference."""
    row: TbRow
    line_ref: str | int
    opening_sides: tuple | None = None


def cents(value):
    if value is None or value == "":
        return 0
    if isinstance(value, float):
        value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif not isinstance(value, (Decimal, int)):
        text = str(value).strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
        negative = text.endswith("-") or text.startswith("(")
        text = text.strip("()")
        if text.endswith("-"):
            text = text[:-1]
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        value = Decimal(text) * (-1 if negative else 1)
    value = Decimal(value)
    if value != value.quantize(Decimal("0.01")):  # "1.234" or "1,234.56" would otherwise truncate silently
        raise ValueError(f"not a 2-decimal amount: {value}")
    return int(value * 100)


def vector(row):
    return tuple(getattr(row, f) for f in FIELDS)


def summed(rows):
    return tuple(sum(getattr(r, f) for r in rows) for f in FIELDS)


def classify(rows):
    """Keep both total/leaf interpretations until global reconciliation.

    States carry integer sum signatures; equivalent sums retain ambiguity and
    the maximal-removal representative. Bound distinct signatures per subtree.
    On overflow that entire unresolved subtree is retained as leaves.
    """
    numeric = [i for i, p in enumerate(rows) if p.row.konto.isdigit()]
    numeric_set = set(numeric)
    labels = [i for i in range(len(rows)) if i not in numeric_set]
    gross_opening = bool(numeric) and all(p.opening_sides is not None for p in rows)
    problems = []
    state_limit = 4096

    def signature(i):
        return vector(rows[i].row) + (rows[i].opening_sides if gross_opening else ())

    signatures = {i: signature(i) for i in range(len(rows))}
    zero = (0,) * (6 if gross_opening else 4)
    children = {i: [] for i in numeric}
    by_code = {rows[i].row.konto: i for i in numeric}
    roots = []
    for i in numeric:
        code = rows[i].row.konto
        parent = next((by_code[code[:n]] for n in range(len(code) - 1, 0, -1)
                       if code[:n] in by_code), None)
        if parent is None:
            roots.append(i)
        else:
            children[parent].append(i)

    def add(a, b):
        return tuple(x + y for x, y in zip(a, b))

    grands = [i for i in labels if rows[i].row.konto.upper() == "SKUPAJ"]
    # Bound feasible subtree sums in each column. An ancestor outside its
    # children's range cannot be a total, so its amount is mandatory. These
    # bounds prune only alternatives that cannot satisfy the grand total.
    lower = {}
    upper_bounds = {}

    def minimum(i):
        if not children[i]:
            lower[i] = signatures[i]
            upper_bounds[i] = signatures[i]
        else:
            low, high = zero, zero
            for j in children[i]:
                low = add(low, minimum(j))
                high = add(high, upper_bounds[j])
            optional = all(lo <= own <= hi for lo, own, hi in zip(low, signatures[i], high))
            lower[i] = add(low, tuple(min(0, v) if optional else v for v in signatures[i]))
            upper_bounds[i] = add(high, tuple(max(0, v) if optional else v for v in signatures[i]))
        return lower[i]

    global_lower = zero
    for i in roots:
        global_lower = add(global_lower, minimum(i))
    bounds = {i: tuple(g - all_min + local_min for g, all_min, local_min in
                       zip(signatures[grands[0]], global_lower, lower[i]))
              for i in numeric} if grands else {}

    # State: signature, selected leaves, removed totals, disputed rows.
    def compact(options):
        groups = {}
        for key, leaves, totals, ties in options:
            if key in groups:
                _, old_l, old_t, old_a = groups[key]
                changed = old_l ^ leaves
                chosen_l, chosen_t = (leaves, totals) if len(totals) > len(old_t) else (old_l, old_t)
                groups[key] = (key, chosen_l, chosen_t, old_a | ties | changed)
            else:
                if len(groups) == state_limit:
                    raise OverflowError
                groups[key] = (key, leaves, totals, ties)
        return list(groups.values())

    def combine(options, limit=None):
        states = [(zero, set(), set(), set())]
        if any(not group for group in options):
            return []
        columns = range(len(zero))
        remaining = [sum(min(s[0][k] for s in group) for group in options) for k in columns]
        for group in options:
            for k in columns:
                remaining[k] -= min(s[0][k] for s in group)

            def merged():
                for x, a, b, c in states:
                    for y, d, e, f in group:
                        key = add(x, y)
                        if limit is None or all(key[k] + remaining[k] <= limit[k] for k in columns):
                            yield key, a | d, b | e, c | f

            states = compact(merged())
        return states

    def unresolved(indices, prefix):
        problems.append(f"classification search limit reached; totals unresolved under {prefix}")
        key = zero
        for j in indices:
            key = add(key, signatures[j])
        return [(key, set(indices), set(), set())]

    def visit(i):
        if not children[i]:
            return [(signatures[i], {i}, set(), set())]
        options = [visit(j) for j in children[i]]
        try:
            limit = tuple(v - min(0, own) for v, own in zip(bounds[i], signatures[i])) if bounds else None
            states = combine(options, limit)
            matching = [(key, l, t | {i}, a) for key, l, t, a in states if key == signatures[i]]
            candidates = matching + [(add(key, signatures[i]), l | {i}, t, a)
                                     for key, l, t, a in states]
            return compact(s for s in candidates if not bounds or
                           all(v <= cap for v, cap in zip(s[0], bounds[i])))
        except OverflowError:
            subtree = [j for j in numeric if rows[j].row.konto.startswith(rows[i].row.konto)]
            return unresolved(subtree, rows[i].row.konto)

    options = [visit(i) for i in roots]
    try:
        states = combine(options, signatures[grands[0]] if grands else None)
        if not states:
            # An inconsistent printed grand total must still yield account
            # rows and diagnostics, rather than erase the extracted table.
            bounds = {}
            states = combine([visit(i) for i in roots])
    except OverflowError:
        states = unresolved(numeric, "<root>")
    valid = [s for s in states if
             (all(s[0] == signatures[i] for i in grands) if grands else
              s[0][0] == s[0][3] == 0)]
    if valid:
        states = valid
    else:
        problems.append("no globally consistent total/leaf classification")
    _, leaves, totals, ties = max(states, key=lambda s: len(s[2]))
    ties = set(ties)
    for _, l, _, a in states:
        ties |= leaves ^ l | a
    if ties:
        problems.append("ambiguous total/leaf: " + ", ".join(rows[i].row.konto for i in sorted(ties)))
    output = sorted([rows[i].row for i in leaves], key=lambda r: r.konto)
    for i in sorted(totals):
        descendants = [r for r in output if r.konto.startswith(rows[i].row.konto)]
        if summed(descendants) != vector(rows[i].row):
            problems.append(f"{rows[i].row.konto}: total does not equal selected leaf sums")
    dropped = [(rows[i].line_ref, rows[i].row.konto, "prefix total") for i in sorted(totals)]
    for i in labels:
        label = rows[i].row.konto
        match = re.fullmatch(r"Skupaj razred (\d+)", label, re.I)
        covered = [r for r in output if not match or r.konto.startswith(match[1])]
        if summed(covered) != vector(rows[i].row):
            problems.append(f"{rows[i].line_ref}: {label} does not equal leaf sums")
        dropped.append((rows[i].line_ref, label, "class total" if match else "grand total"))
    return output, dropped, problems


def year_of(text):
    # Period dates take precedence over later printing dates.
    for words in (("temeljnice", "obdob", "za leto"), ("bilanca",)):
        for line in text.splitlines():
            if any(word in line.lower() for word in words):
                match = re.search(r"\b(20\d{2}|19\d{2})\b", line)
                if match:
                    return int(match[1])
    return 0


def finish(fmt, year, printed, problems, net_only=False):
    rows, dropped, issues = classify(printed)
    if not year:
        problems.append("reporting year not found; using year 0")
    if not rows:
        problems.append("no account rows extracted")
    return Wrangled(fmt, rows, dropped, problems + issues + check_tb(rows), net_only, year)


def read_pdf(path):
    return read_pdf_lines(pdf_lines(path))


def read_pdf_lines(lines):
    """Parse extracted table lines without inspecting a PDF or companion files."""
    text = "\n".join(lines)
    upper = text.upper()
    minimax_headers = all(word in upper for word in ("ZACETNO", "PROMET", "SKUPAJ", "KONCNO"))
    minimax_columns = any(re.match(r"^\s*SKUPAJ\s+", line) and len(NUMBER.findall(line)) == 8
                          for line in lines)
    if minimax_headers and minimax_columns:
        fmt = "minimax_pdf"
    elif "predizdelana" in text.lower():
        fmt = "furs_pdf"
    elif "Analitika" in text or "DENAR" in text:
        fmt = "analitika_pdf"
    else:
        raise ValueError("unknown PDF format")
    printed, problems = [], []
    in_table = False
    owner = None
    for n, line in enumerate(lines, 1):
        if "\f" in line:
            in_table, owner = False, None
            line = line.replace("\f", "")
        if re.match(r"^\s*Konto\s+Naziv", line, re.I):
            in_table = True
            owner = None
            continue
        if any(s in line for s in ("Izpisano:", "Stran:", "www.minimax.si")):
            in_table = False
            owner = None
            continue
        # Repeated column furniture cannot own or extend an account name.
        if re.match(r"^\s*(?:Otvoritev\s+Promet\s+Saldo|(?:DB\s+KR\s*)+|"
                    r"(?:Debet\s+Kredit\s*)+|KONTO\b|ZACETNO\b)", line, re.I):
            owner = None
            continue
        match = re.match(r"^\s*(\d+|SKUPAJ)\s+", line)
        if not match:
            if in_table and owner is not None and line.strip() and not NUMBER.search(line):
                p = printed[owner]
                printed[owner] = replace(p, row=replace(p.row, name=p.row.name + " " + " ".join(line.split())))
            continue
        code, rest = match[1], line[match.end():]
        owner = None
        # Analitika totals may also print a labelled net difference (Razlika).
        if fmt == "analitika_pdf" and "Razlika" in text:
            difference = re.search(NUMBER.pattern + r"\s+[DK]\s*$", rest)
            if difference:
                rest = rest[:difference.start()]
        amounts = list(NUMBER.finditer(rest))
        try:
            if not amounts:
                raise ValueError("no amount tokens")
            # The full amount suffix must consist of complete tokens and spaces.
            end = amounts[0].start()
            for amount in amounts:
                if rest[end:amount.start()].strip():
                    raise ValueError("unparsed amount text")
                end = amount.end()
            if rest[end:].strip():
                raise ValueError("unparsed amount text")
            v = [cents(m[0]) for m in amounts]
        except (InvalidOperation, ValueError) as e:
            problems.append(f"line {n}: {code}: invalid amounts ({e})")
            continue
        name = "" if fmt == "minimax_pdf" else " ".join(rest[:amounts[0].start()].split())
        if fmt == "minimax_pdf":
            if len(v) not in ((8,) if code == "SKUPAJ" else (6, 7)):
                problems.append(f"line {n}: {code}: wrong amount count")
                continue
            closing = v[4] - v[5]
            if v[0] + v[2] != v[4] or v[1] + v[3] != v[5]:
                problems.append(f"line {n}: {code}: gross cross-foot mismatch")
            if code != "SKUPAJ" and v[6:] != ([abs(closing)] if closing else []):
                problems.append(f"line {n}: {code}: printed closing mismatch")
            if code == "SKUPAJ" and v[6] - v[7] != closing:
                problems.append(f"line {n}: SKUPAJ: closing mismatch")
        elif fmt == "analitika_pdf" and len(v) in (4, 5):
            net = v[0] - v[1] + v[2] - v[3]
            saldo = v[4] if len(v) == 5 else 0
            closing = saldo if net >= 0 else -saldo
            if saldo != abs(net):
                problems.append(f"line {n}: {code}: printed closing mismatch")
        else:
            if len(v) != 6:
                problems.append(f"line {n}: {code}: wrong amount count")
                continue
            closing = v[4] - v[5]
        printed.append(Printed(TbRow(code, name, v[0] - v[1], v[2], v[3], closing), n, (v[0], v[1])))
        if code.isdigit():
            owner = len(printed) - 1
    year = year_of(text)
    return {year: finish(fmt, year, printed, problems)}


def read_table(table, fmt, year, ref=""):
    printed, problems = [], []
    for n, cells in enumerate(table, 1):
        cells = list(cells)
        numeric_code = bool(ref and cells and isinstance(cells[0], (int, float)))
        if numeric_code:
            cells[0] = str(int(cells[0]))
        label = str(cells[0] or "").strip() if cells else ""
        match = CODE.fullmatch(label)
        total = label.upper() == "SKUPAJ" or re.fullmatch(r"Skupaj razred \d+", label, re.I)
        if not match and not total:
            continue
        if numeric_code:
            warning = (f"konto stored as number in {ref}: leading zeros may be lost "
                       "(e.g. 400 may be 0400); fix the export or map manually")
            if warning not in problems:
                problems.append(warning)
        line_ref = f"{ref}:{n}" if ref else n
        try:
            if fmt in ("quirky_xlsx", "erp"):
                code, name = (match[1], match[2] or "") if match else (label, "")
                v = [cents(c) for c in cells[1:]]
            else:
                code, name = label, str(cells[1] or "")
                v = [cents(c) for c in cells[2:]]
            if fmt == "monthly_xlsx":
                if len(v) != 15:
                    raise ValueError("wrong amount count")
                net = sum(v[1:13])
                if net != v[13]:
                    problems.append(f"{line_ref}: {code}: monthly sum != printed movement")
                values = (v[0], max(net, 0), max(-net, 0), v[14])
            elif fmt == "erp":
                if len(v) != 6:
                    raise ValueError("wrong amount count")
                values = (v[0] - v[1], v[2], v[3], v[4] - v[5])
            else:
                if len(v) != 4:
                    raise ValueError("wrong amount count")
                values = v
            printed.append(Printed(TbRow(code, name, *values), line_ref))
        except (InvalidOperation, ValueError, TypeError, IndexError) as e:
            problems.append(f"{line_ref}: {label}: invalid amounts ({e})")
    return finish(fmt, year, printed, problems, fmt == "monthly_xlsx")


def wrangle_all(path):
    """Return {year: Wrangled}; inspect only input content, never companions."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    if path.suffix.lower() == ".xlsx":
        wb = load_workbook(path, data_only=True)
        results = {}
        try:
            for ws in wb:
                table = list(ws.values)
                text = "\n".join(" ".join(str(c or "") for c in r) for r in table)
                if "Skupaj promet" in text and "Jan" in text:
                    fmt = "monthly_xlsx"
                elif "Saldo začetni" in text and "Konto - Naziv" in text:
                    fmt = "quirky_xlsx"
                elif "Otvoritev" in text and "Breme" in text and "Končno stanje" in text:
                    fmt = "erp"
                elif any(tuple(r[:6]) == ("Konto", "Naziv", "Otvoritev", "Promet D", "Promet K", "Saldo")
                         for r in table):
                    fmt = "numeric_konto_xlsx"
                else:
                    raise ValueError("unknown workbook format")
                year = year_of(text)
                result = read_table(table, fmt, year, ws.title)
                if year in results:
                    result = replace(result, rows=results[year].rows + result.rows,
                                     problems=results[year].problems + result.problems + ["duplicate year sheets"])
                results[year] = result
        finally:
            wb.close()
        return results
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250")
    delimiter = "\t" if "\t" in text else ";" if ";" in text else ","
    table = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if table and table[0] == ["year", "konto", "name", *FIELDS]:
        grouped, problems = {}, []
        for n, r in enumerate(table[1:], 2):
            if r == table[0] or not r:
                continue
            try:
                year = int(r[0])
                grouped.setdefault(year, []).append(Printed(TbRow(r[1], r[2], *(cents(v) for v in r[3:])), n))
            except (ValueError, InvalidOperation, TypeError, IndexError) as e:
                problems.append(f"line {n}: invalid tidy row ({e})")
        return {y: finish("tidy", y, r, list(problems)) for y, r in (grouped or {0: []}).items()}
    if delimiter == "\t" and "Promet D" in text and "Konto" in text:
        fmt = "tab_csv"
    elif delimiter == ";" and "Otvoritveni saldo" in text:
        fmt = "export"
    else:
        raise ValueError("unknown text format")
    year = year_of(text)
    return {year: read_table(table, fmt, year)}


def wrangle(path):
    results = wrangle_all(path)
    return next(iter(results.values())) if len(results) == 1 else results


def main(argv=None):
    from argus.aop import AopTree
    from argus.chart import load_chart
    from argus.checks import MEMO_AOPS, cross_check, load_filed
    from argus.layouts import eur_si
    from argus.mapping import rollup, statements_from_tb
    from argus.tb import column

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    parser.add_argument("--out")
    parser.add_argument("--map", action="store_true", help="roll up and map closing balances to AOP")
    parser.add_argument("--filed", help="cross-check filed CSV (implies --map)")
    args = parser.parse_args(argv)
    results = wrangle_all(args.file)
    problems = []
    if args.map or args.filed:
        chart, tree = load_chart(), AopTree.load()
    for year, result in results.items():
        print(f"{year}: {result.format}, rows={len(result.rows)}, dropped={len(result.dropped)}, net_only={result.net_only}")
        if result.net_only:
            print("NET ONLY: gross debit/credit not recoverable")
        for problem in result.problems:
            print(problem)
        problems.extend(result.problems)
        if args.map or args.filed:
            rows, issues = rollup(result.rows, chart)
            mapped = statements_from_tb(column(rows, "closing"), chart, tree)
            for aop, label in (("001", "total assets"), ("110", "net sales"),
                               ("186", "net profit"), ("187", "net loss")):
                print(f"AOP {aop} {label}: {eur_si(Decimal(mapped[aop]))}")
            if args.filed:
                try:
                    issues.extend(cross_check(mapped, load_filed(args.filed, year)))
                except (ValueError, InvalidOperation) as e:
                    issues.append(str(e))
                print("Cross-check: problems" if issues else "Cross-check: OK")
                print(f"Not checked (memo lines): {', '.join(sorted(MEMO_AOPS))}")
            for problem in issues:
                print(problem)
            problems.extend(issues)
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["year", "konto", "name", *FIELDS])
            for year, result in sorted(results.items()):
                for r in result.rows:
                    writer.writerow([year, r.konto, r.name, *(format(Decimal(v) / 100, ".2f") for v in vector(r))])
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
