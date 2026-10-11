"""TB -> AOP statements (ADR 0001: the TB is the input, AOP is the reporting structure)."""

from argus.tb import TbRow

RESULT_AOP = "070"  # current-year net result (paired with 071)


def rollup(rows, chart):
    """Aggregate analytic konti to their longest chart prefix.

    Distinct chart keys cannot tie: equal-length prefixes of one konto are equal.
    Unmapped rows are reported and excluded. Output is sorted by chart konto.
    """
    totals, unmapped = {}, set()
    for row in rows:
        konto = next((row.konto[:n] for n in range(len(row.konto), 0, -1)
                      if row.konto[:n] in chart), None)
        if konto is None:
            unmapped.add(row.konto)
            continue
        values = totals.setdefault(konto, [0, 0, 0, 0])
        for i, field in enumerate(("opening", "debit", "credit", "closing")):
            values[i] += getattr(row, field)
    output = [TbRow(k, chart[k].name, *totals[k]) for k in sorted(totals)]
    problems = [f"konti without mapping: {sorted(unmapped)}"] if unmapped else []
    return output, problems


def map_balances(balances, chart, tree):
    """Debit-positive konto balances (cents) -> leaf AOP amounts, pairs kept net on the profit side."""
    unmapped = sorted(k for k in balances if k not in chart)
    if unmapped:
        raise KeyError(f"konti without mapping: {unmapped}")
    leaves = {}
    for konto, balance in balances.items():
        aop = chart[konto].aop
        leaves[aop] = leaves.get(aop, 0) + balance * tree.balance_signs[aop]
    return leaves


def statements_from_tb(balances, chart, tree):
    """Full AOP statements from one TB column.

    Current-year result = what sits on result konti (post-closing) + net of open P&L
    konti (pre-closing). One rule covers both, since the other part is zero.
    """
    leaves = map_balances(balances, chart, tree)
    pnl = tree.evaluate({a: v for a, v in leaves.items() if tree.lines[a].statement == "income_statement"})
    leaves[RESULT_AOP] = leaves.get(RESULT_AOP, 0) + pnl["186"] - pnl["187"]
    return tree.evaluate(leaves)
