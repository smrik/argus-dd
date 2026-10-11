"""AOP tree of the AJPES company form, loaded from data/aop/gd_2024.csv.

Amounts are integer cents. Leaf values are what the form reports (non-negative for
paired lines such as 068/069); totals are computed from the formulas in the form.
"""

import csv
import re
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TERM_RE = re.compile(r"([+-]?)(\d{3})(?:do(\d{3}))?")

# Sign that turns a debit-positive TB balance into the amount of each total:
# assets = +balances, liabilities and equity = -balances, net profit = -P&L balances.
ROOTS = {"001": 1, "055": -1, "186": -1}


def parse_formula(text):
    """'057+060-069' -> ((1, '057'), (1, '060'), (-1, '069')); 'do' ranges are expanded."""
    terms = []
    for sign, start, end in TERM_RE.findall(text):
        coef = -1 if sign == "-" else 1
        codes = range(int(start), int(end) + 1) if end else [int(start)]
        terms += [(coef, f"{c:03d}") for c in codes]
    return tuple(terms)


def parse_groups(text):
    """'del 00, 02, del 13' -> {'00', '02', '13'} (2-digit konto groups that may feed a line)."""
    return frozenset(g.replace("del", "").strip() for g in text.split(",") if g.strip())


@dataclass(frozen=True)
class Line:
    statement: str
    aop: str
    label: str
    formula: tuple
    konto_groups: frozenset
    paired_with: str


class AopTree:
    def __init__(self, lines):
        self.lines = {line.aop: line for line in lines}

    @classmethod
    def load(cls, path=DATA_DIR / "aop" / "gd_2024.csv"):
        with open(path, encoding="utf-8", newline="") as f:
            return cls(
                Line(
                    statement=r["statement"],
                    aop=r["aop"],
                    label=r["label"],
                    formula=parse_formula(r["formula"]),
                    konto_groups=parse_groups(r["konto_groups"]),
                    paired_with=r["paired_with"],
                )
                for r in csv.DictReader(f)
            )

    def is_loss_side(self, aop):
        """In a pair (e.g. 070/071) the higher code is the loss / decrease side."""
        pair = self.lines[aop].paired_with
        return bool(pair) and aop > pair

    def leaves(self, aop):
        """Signed leaf coefficients of a line. Loss-side result lines (152, 183, 187)
        add nothing: their profit side's formula is already the net amount."""
        line = self.lines[aop]
        if not line.formula:
            return {aop: 1}
        if self.is_loss_side(aop):
            return {}
        out = {}
        for coef, ref in line.formula:
            for leaf, c in self.leaves(ref).items():
                out[leaf] = out.get(leaf, 0) + coef * c
        return out

    @cached_property
    def balance_signs(self):
        """leaf AOP -> sign that converts a debit-positive TB balance into the leaf amount."""
        signs = {}
        for root, root_sign in ROOTS.items():
            for leaf, coef in self.leaves(root).items():
                signs[leaf] = root_sign * coef
        return signs

    def evaluate(self, values):
        """Full statement (every line) from leaf values.

        Paired leaves may be given net on the profit side (e.g. a negative 068); they
        are split so that only one side is non-zero, as on the form.
        """
        leaves = dict(values)
        for aop in list(leaves):
            line = self.lines[aop]
            if line.paired_with and not self.is_loss_side(aop) and leaves[aop] < 0:
                leaves[line.paired_with] = leaves.get(line.paired_with, 0) - leaves[aop]
                leaves[aop] = 0

        @cache
        def net(aop):
            line = self.lines[aop]
            if not line.formula:
                return leaves.get(aop, 0)
            if self.is_loss_side(aop):
                return 0
            return sum(coef * net(ref) for coef, ref in line.formula)

        out = {}
        for aop, line in self.lines.items():
            if not line.formula:
                out.setdefault(aop, leaves.get(aop, 0))
            elif not self.is_loss_side(aop):
                amount = net(aop)
                if line.paired_with:
                    out[aop], out[line.paired_with] = max(amount, 0), max(-amount, 0)
                else:
                    out[aop] = amount
        return out
