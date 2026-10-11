"""Checks on a wrangled TB and on mapped statements (see CONTEXT.md, Wrangling).

Each check returns a list of problems; an empty list means it passed.
"""

import csv
from collections import Counter
from decimal import Decimal

from argus.mapping import RESULT_AOP


def load_filed(path, year):
    """Filed monetary AOP figures for one year, in integer cents (EUR decimals)."""
    amounts = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if int(row["year"]) != year or row["aop"] in {"188", "189"}:
                continue
            amount = Decimal(row["amount"]) * 100
            if not amount.is_finite() or amount != amount.to_integral_value():
                raise ValueError(f"AOP {row['aop']}: not a 2-decimal amount")
            amounts[row["aop"]] = int(amount)
    if not amounts:
        raise ValueError(f"no filed monetary figures for {year}")
    return amounts


# "Od tega" memo lines (interest already included in II. and III.): a konto-level TB cannot split them out.
MEMO_AOPS = frozenset({"154", "167"})


def cross_check(mapped, filed, tolerance=0):
    """Verify filed AOP lines a TB can produce (memo lines skipped); amounts in integer cents."""
    from argus.layouts import eur_si

    problems = []
    for aop, amount in filed.items():
        if aop in MEMO_AOPS:
            continue
        actual = mapped.get(aop, 0)
        diff = actual - amount
        if abs(diff) > tolerance:
            problems.append(f"AOP {aop}: TB {eur_si(Decimal(actual))} vs filed {eur_si(Decimal(amount))} (diff {eur_si(Decimal(diff))})")
    return problems


def check_tb(rows):
    problems = []
    for field in ("opening", "closing"):
        total = sum(getattr(r, field) for r in rows)
        if total:
            problems.append(f"{field} balances sum to {total / 100:.2f}, not 0")
    dupes = [k for k, n in Counter(r.konto for r in rows).items() if n > 1]
    if dupes:
        problems.append(f"konti listed more than once: {dupes}")
    for r in rows:
        if r.opening + r.debit - r.credit != r.closing:
            problems.append(f"{r.konto}: opening + debit - credit != closing")
    return problems


def check_continuity(prev_rows, rows, chart, tree):
    """Year N (pre-closing) -> year N+1 (opening, post-closing).

    Balance sheet konti carry over unchanged, except that the current-year result
    konto opens with last year's net P&L. P&L konti open at zero.
    """
    problems = []
    prev = {r.konto: r.closing for r in prev_rows}
    pnl_konti = {k for k, a in chart.items() if tree.lines[a.aop].statement == "income_statement"}
    prev_net_pnl = -sum(v for k, v in prev.items() if k in pnl_konti)
    for r in rows:
        if r.konto in pnl_konti:
            expected = 0
        elif chart[r.konto].aop == RESULT_AOP:
            expected = prev.get(r.konto, 0) - prev_net_pnl
        else:
            expected = prev.get(r.konto, 0)
        if r.opening != expected:
            problems.append(f"{r.konto}: opening {r.opening / 100:.2f} != expected {expected / 100:.2f}")
    return problems


def check_ajpes_controls(statements, extras):
    """Subset of AJPES's own controls for the company form (amounts in cents).

    Source: https://www.ajpes.si/Drugo/Aplikacije/Letna_porocila/2024/kontrole
    """
    s = {**statements, **extras}
    problems = []

    def rule(ok, text):
        if not ok:
            problems.append(text)

    rule(s["055"] == s["001"], "055 must equal 001")
    for a, b in (("070", "071"), ("121", "122")):
        rule(not (s[a] > 0 and s[b] > 0), f"{a} and {b} cannot both be > 0")
    rule(not (s["070"] > 0 and s["069"] + s["071"] > 0), "if 070 > 0, 069 + 071 must be 0")
    rule((s["140"] > 0) == (s["188"] > 0), "140 > 0 if and only if 188 > 0")
    rule(not s["140"] > 0 or s["141"] > 0, "if 140 > 0, 141 must be > 0")
    rule((s["141"] > 0) == (s["142"] > 0), "141 > 0 if and only if 142 > 0")
    rule(s["154"] <= s["160"] + s["163"], "154 must be <= 160 + 163")
    rule(s["167"] <= s["169"] + s["174"], "167 must be <= 169 + 174")
    rule(s["058"] >= 7_500_00, "share capital 058 below the 7,500 EUR minimum")
    if s["188"]:
        wage = s["140"] / 100 / s["188"] / 12
        rule(300 <= wage <= 8_000, f"average monthly wage {wage:,.0f} EUR outside 300-8,000")
    return problems


def check_statements(statements):
    if statements["001"] != statements["055"]:
        return [f"assets 001 ({statements['001'] / 100:.2f}) != liabilities and equity 055 ({statements['055'] / 100:.2f})"]
    return []
