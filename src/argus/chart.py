"""Chart of accounts: konto -> AOP leaf (+ allocation weight for synthetic data)."""

import csv
from dataclasses import dataclass
from fractions import Fraction

from argus.aop import DATA_DIR


@dataclass(frozen=True)
class Account:
    konto: str
    name: str
    aop: str
    weight: Fraction


def load_chart(path=DATA_DIR / "chart" / "synthetic_chart.csv"):
    with open(path, encoding="utf-8", newline="") as f:
        return {
            r["konto"]: Account(r["konto"], r["name"], r["aop"], Fraction(r["weight"]))
            for r in csv.DictReader(f)
        }


def validate_chart(chart, tree):
    """Return a list of problems (empty if the chart is consistent with the AOP form)."""
    problems = []
    weights = {}
    for acc in chart.values():
        line = tree.lines.get(acc.aop)
        if line is None:
            problems.append(f"{acc.konto}: unknown AOP {acc.aop}")
            continue
        if line.formula:
            problems.append(f"{acc.konto}: AOP {acc.aop} is a total, not a leaf")
        if tree.is_loss_side(acc.aop):
            problems.append(f"{acc.konto}: map pairs to the profit side, not {acc.aop}")
        if acc.konto[:2] not in line.konto_groups:
            problems.append(f"{acc.konto}: group {acc.konto[:2]} not allowed for AOP {acc.aop}")
        weights[acc.aop] = weights.get(acc.aop, 0) + acc.weight
    problems += [f"AOP {aop}: weights sum to {w}, not 1" for aop, w in weights.items() if w != 1]
    return problems


def accounts_by_aop(chart):
    out = {}
    for acc in chart.values():
        out.setdefault(acc.aop, []).append(acc)
    return out
