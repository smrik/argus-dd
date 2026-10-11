"""Synthetic companies: AOP statements first, then a TB that maps back to them exactly.

All data is fake (ADR 0004). Amounts are integer cents; TB balances are debit positive.
The TB is pre-closing: P&L konti are open and the current-year result konto is zero.
"""

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

from argus.aop import AopTree
from argus.chart import accounts_by_aop, load_chart, validate_chart
from argus.mapping import RESULT_AOP
from argus.tb import TbRow

CIT_RATE = 0.22
PENSION_RATE = 0.0885
OTHER_SOCIAL_RATE = 0.0725
AVG_MONTHLY_WAGE_EUR = 2300  # only used to derive headcount (AOP 188)
GOODS_REVENUE = ("114", "117", "120")
PURCHASE_COSTS = ("129", "131", "132", "135", "136", "138")

# Turnover per year as a multiple of the balance, by konto class (first digit).
ACTIVITY = {"0": (0.02, 0.3), "1": (2, 6), "2": (2, 6), "3": (1, 3), "6": (1, 3), "9": (0, 0.05)}
DEFAULT_ACTIVITY = (0, 0.02)  # P&L konti: occasional corrections only


@dataclass(frozen=True)
class Profile:
    company_name: str
    revenue_mix: dict  # revenue AOP -> share of revenue
    cogs_ratio: float  # cost of goods sold (129) / goods revenue
    cost_ratios: dict  # cost AOP -> share of revenue
    wage_ratio: float  # gross wages (140) / revenue
    asset_ratios: dict  # non-working-capital asset AOP -> multiple of revenue
    dso: int
    dio: int
    dpo: int
    debt_ratio: float  # bank debt / revenue
    share_capital_eur: int


PROFILES = {
    "services": Profile(
        company_name="SINTETIKA STORITVE d.o.o.",
        revenue_mix={"112": 0.75, "116": 0.25},
        cogs_ratio=0.0,
        cost_ratios={"131": 0.01, "132": 0.01, "135": 0.005, "136": 0.04, "137": 0.02, "138": 0.2, "150": 0.005},
        wage_ratio=0.45,
        asset_ratios={"005": 0.02, "014": 0.06, "053": 0.005},
        dso=60, dio=0, dpo=30,
        debt_ratio=0.05,
        share_capital_eur=7_500,
    ),
    "trading": Profile(
        company_name="SINTETIKA TRGOVINA d.o.o.",
        revenue_mix={"114": 0.6, "117": 0.25, "112": 0.15},
        cogs_ratio=0.8,
        cost_ratios={"131": 0.005, "132": 0.01, "135": 0.025, "136": 0.02, "137": 0.005, "138": 0.04, "150": 0.003},
        wage_ratio=0.09,
        asset_ratios={"011": 0.03, "012": 0.08, "014": 0.03, "016": 0.005, "053": 0.003},
        dso=55, dio=50, dpo=45,
        debt_ratio=0.12,
        share_capital_eur=50_000,
    ),
}


@dataclass(frozen=True)
class YearData:
    year: int
    rows: list  # TbRow, sorted by konto
    statements: dict  # AOP -> cents, every line (what the company files with AJPES)
    extras: dict  # lines not derivable from a TB: 154/167 memo interest (cents), 188 headcount, 189 months


@dataclass(frozen=True)
class Company:
    name: str
    profile: str
    seed: int
    years: list  # YearData, oldest first


def statement_leaves(p, revenue_c, rng, tree, prev):
    """Leaf AOP amounts (cents) for one year. Pairs are net on the profit side (068, 070)."""

    def jitter():
        return rng.uniform(0.9, 1.1)

    ipi = {aop: round(revenue_c * share) for aop, share in p.revenue_mix.items()}
    if p.cogs_ratio:
        goods = sum(ipi.get(a, 0) for a in GOODS_REVENUE)
        ipi["129"] = round(goods * p.cogs_ratio * jitter())
    for aop, ratio in p.cost_ratios.items():
        ipi[aop] = round(revenue_c * ratio * jitter())
    wages = round(revenue_c * p.wage_ratio * jitter())
    ipi["140"] = wages
    ipi["141"] = round(wages * PENSION_RATE)
    ipi["142"] = round(wages * OTHER_SOCIAL_RATE)
    ipi["143"] = round(wages * 0.06 * jitter())
    ipi["125"] = round(revenue_c * 0.004 * jitter())
    ipi["165"] = round(revenue_c * 0.0005 * jitter())
    ipi["180"] = round(revenue_c * 0.001 * jitter())
    ipi["181"] = round(revenue_c * 0.0015 * jitter())

    bs = {aop: round(revenue_c * ratio * jitter()) for aop, ratio in p.asset_ratios.items()}
    depreciable = sum(bs.get(a, 0) for a in ("005", "012", "013", "014"))
    ipi["145"] = round(depreciable * 0.12 * jitter())
    debt = round(revenue_c * p.debt_ratio * jitter())
    bs["078"] = round(debt * 0.7)
    bs["089"] = debt - bs["078"]
    ipi["171"] = round(debt * 0.05 * jitter())

    pre_tax = tree.evaluate(ipi)
    pre_tax_result = pre_tax["182"] - pre_tax["183"]
    ipi["184"] = round(max(pre_tax_result, 0) * CIT_RATE)

    bs["050"] = round(revenue_c * p.dso / 365 * jitter())
    if p.dio:
        bs["038"] = round(ipi["129"] * p.dio / 365 * jitter())
    purchases = sum(ipi.get(a, 0) for a in PURCHASE_COSTS)
    bs["093"] = round(purchases * p.dpo / 365 * jitter())
    bs["051"] = round(revenue_c * 0.01 * jitter())
    bs["094"] = round(wages / 12 * 1.4 * jitter())  # last month's wages and taxes
    bs["095"] = round(revenue_c * 0.005 * jitter())
    bs["073"] = round(wages * 0.03 * jitter())
    bs["058"] = p.share_capital_eur * 100
    bs["062"] = round(bs["058"] * 0.1)
    bs[RESULT_AOP] = pre_tax_result - ipi["184"]

    # Retained earnings roll forward (half of last year's profit paid out); cash balances the sheet.
    assets = set(tree.leaves("001"))
    funding = tree.leaves("055")
    assets_ex_cash = sum(v for a, v in bs.items() if a in assets)
    if prev is None:
        bs["068"] = 0
        target_cash = round(revenue_c * rng.uniform(0.04, 0.10))
        funded = sum(funding.get(a, 0) * v for a, v in bs.items())
        bs["068"] = assets_ex_cash + target_cash - funded
    else:
        dividend = max(prev[RESULT_AOP], 0) // 2
        bs["068"] = prev["068"] + prev[RESULT_AOP] - dividend
    cash = sum(funding.get(a, 0) * v for a, v in bs.items()) - assets_ex_cash
    min_cash = round(revenue_c * 0.01)
    if cash < min_cash:  # short of cash: draw more on the bank line
        bs["089"] += min_cash - cash
        cash = min_cash
    bs["052"] = cash

    # Lines a TB cannot produce: memo interest lines (already inside 160/163 and 169/174),
    # headcount (two decimals per the form) and months of operation.
    extras = {
        "154": ipi["165"],
        "167": ipi["171"],
        "188": round(wages / 100 / (AVG_MONTHLY_WAGE_EUR * 12), 2),
        "189": 12,
    }
    return {**bs, **ipi}, extras


def allocate(amount, accounts):
    """Split an AOP amount over konti by weight; rounding remainder goes to the largest weight."""
    parts = {acc.konto: round(amount * acc.weight) for acc in accounts}
    main = max(accounts, key=lambda acc: acc.weight).konto
    parts[main] += amount - sum(parts.values())
    return parts


def konto_balances(leaves, by_aop, tree):
    balances = {}
    for aop, amount in leaves.items():
        if amount == 0:
            continue
        if aop not in by_aop:
            raise KeyError(f"no synthetic konto for AOP {aop}")
        sign = tree.balance_signs[aop]
        for konto, part in allocate(amount, by_aop[aop]).items():
            balances[konto] = part * sign
    return balances


def tb_rows(opening, closing, chart, rng):
    rows = []
    for konto in sorted(set(opening) | set(closing)):
        o, c = opening.get(konto, 0), closing.get(konto, 0)
        low, high = ACTIVITY.get(konto[0], DEFAULT_ACTIVITY)
        activity = round(max(abs(o), abs(c)) * rng.uniform(low, high))
        delta = c - o
        debit = max(delta, 0) + activity
        rows.append(TbRow(konto, chart[konto].name, o, debit, debit - delta, c))
    return rows


def generate(profile="services", seed=1, first_year=2022, last_year=2024, revenue_eur=2_000_000):
    p = PROFILES[profile]
    rng = random.Random(seed)
    tree = AopTree.load()
    chart = load_chart()
    problems = validate_chart(chart, tree)
    if problems:
        raise ValueError(f"synthetic chart invalid: {problems}")
    by_aop = accounts_by_aop(chart)

    growth = rng.uniform(0.03, 0.12)
    calendar = range(first_year - 1, last_year + 1)  # the extra first year only supplies openings
    prev = None
    years = []
    for i, year in enumerate(calendar):
        revenue_c = revenue_eur * 100 * (1 + growth) ** (i - len(calendar) + 1) * rng.uniform(0.95, 1.05)
        leaves, extras = statement_leaves(p, revenue_c, rng, tree, prev)
        if prev is not None:
            bs_prev = {a: v for a, v in prev.items() if tree.lines[a].statement == "balance_sheet"}
            opening = konto_balances(bs_prev, by_aop, tree)  # post-closing: result on 933
            closing = konto_balances({**leaves, RESULT_AOP: 0}, by_aop, tree)  # pre-closing
            years.append(YearData(year, tb_rows(opening, closing, chart, rng), tree.evaluate(leaves), extras))
        prev = leaves
    return Company(p.company_name, profile, seed, years)


def main(argv=None):
    from argus.checks import check_continuity, check_statements, check_tb
    from argus.layouts import write_all
    from argus.mapping import statements_from_tb
    from argus.tb import column

    parser = argparse.ArgumentParser(description="Generate a synthetic company: TBs + filed AOP statements.")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="services")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--first-year", type=int, default=2022)
    parser.add_argument("--last-year", type=int, default=2024)
    parser.add_argument("--revenue", type=int, default=2_000_000, help="last-year revenue in EUR")
    parser.add_argument("--out", type=Path, default=Path("out/synth"))
    args = parser.parse_args(argv)

    company = generate(args.profile, args.seed, args.first_year, args.last_year, args.revenue)
    out_dir = args.out / f"{args.profile}_seed{args.seed}"
    write_all(company, out_dir)

    tree, chart = AopTree.load(), load_chart()
    prev = None
    for y in company.years:
        mapped = statements_from_tb(column(y.rows, "closing"), chart, tree)
        problems = check_tb(y.rows) + check_statements(mapped)
        problems += [f"AOP {a}: TB gives {mapped[a]}, filed {v}" for a, v in y.statements.items() if mapped[a] != v]
        if prev is not None:
            problems += check_continuity(prev.rows, y.rows, chart, tree)
        print(f"{y.year}: {len(y.rows)} konti, revenue {y.statements['110'] / 100:,.0f} EUR, "
              f"net result {(y.statements['186'] - y.statements['187']) / 100:,.0f} EUR, "
              f"checks {'OK' if not problems else problems}")
        prev = y
    print(f"written to {out_dir}")


if __name__ == "__main__":
    main()
