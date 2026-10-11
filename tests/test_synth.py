from dataclasses import replace

import pytest

from argus.aop import AopTree
from argus.chart import load_chart, validate_chart
from argus.checks import check_ajpes_controls, check_continuity, check_statements, check_tb
from argus.mapping import statements_from_tb
from argus.synth import PROFILES, generate
from argus.tb import TbRow, column

tree = AopTree.load()
chart = load_chart()
COMPANIES = [generate(profile, seed) for profile in sorted(PROFILES) for seed in (1, 2, 3)]


def test_synthetic_chart_respects_the_form():
    assert validate_chart(chart, tree) == []


@pytest.mark.parametrize("company", COMPANIES, ids=lambda c: f"{c.profile}-{c.seed}")
def test_tb_maps_back_to_filed_statements(company):
    prev = None
    for y in company.years:
        assert check_tb(y.rows) == []
        closing = statements_from_tb(column(y.rows, "closing"), chart, tree)
        assert check_statements(closing) == []
        assert closing == y.statements
        if prev is not None:
            opening = statements_from_tb(column(y.rows, "opening"), chart, tree)
            bs = [a for a, l in tree.lines.items() if l.statement == "balance_sheet"]
            assert {a: opening[a] for a in bs} == {a: prev.statements[a] for a in bs}
            assert check_continuity(prev.rows, y.rows, chart, tree) == []
        prev = y


@pytest.mark.parametrize("company", COMPANIES, ids=lambda c: f"{c.profile}-{c.seed}")
def test_filed_statements_pass_ajpes_controls(company):
    # The round trip above only shows TB and statements agree with each other;
    # AJPES's published controls are an outside reference for "looks like a real filing".
    for y in company.years:
        assert check_ajpes_controls(y.statements, y.extras) == []


def test_generation_is_reproducible():
    assert generate("trading", 5) == generate("trading", 5)


# The checks must catch what sum-to-zero alone misses (CONTEXT.md, Wrangling).

def _year(i=1):
    return COMPANIES[0].years[i]


def test_grand_total_row_included_as_data_is_caught():
    y = _year()
    total = TbRow("SKUPAJ", "", 0, sum(r.debit for r in y.rows), sum(r.credit for r in y.rows), 0)
    assert check_tb(y.rows + [total]) == []  # nets to zero, so the TB checks miss it...
    with pytest.raises(KeyError, match="SKUPAJ"):  # ...but it is not a konto, so mapping rejects it
        statements_from_tb(column(y.rows + [total], "closing"), chart, tree)


def test_duplicated_konto_is_caught():
    y = _year()
    assert any("more than once" in p for p in check_tb(y.rows + [y.rows[0]]))


def test_swapped_opening_and_closing_is_caught():
    prev, y = COMPANIES[0].years[0], _year()
    swapped = [replace(r, opening=r.closing, closing=r.opening, debit=r.credit, credit=r.debit) for r in y.rows]
    assert check_tb(swapped) == []  # still balanced and rolls forward...
    assert check_continuity(prev.rows, swapped, chart, tree)  # ...but no longer follows last year


def test_flipped_sign_is_caught_by_cross_check():
    y = _year()
    flipped = [replace(r, opening=-r.opening, closing=-r.closing, debit=r.credit, credit=r.debit) for r in y.rows]
    assert check_tb(flipped) == []  # sums to zero either way
    assert statements_from_tb(column(flipped, "closing"), chart, tree) != y.statements


def test_unmapped_konto_is_reported():
    with pytest.raises(KeyError, match="123"):
        statements_from_tb({"123": 100, "110": -100}, chart, tree)
