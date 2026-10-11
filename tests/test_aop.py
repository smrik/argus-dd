from argus.aop import AopTree, parse_formula

tree = AopTree.load()


def test_form_is_complete():
    bs = {a for a, l in tree.lines.items() if l.statement == "balance_sheet"}
    ipi = {a for a, l in tree.lines.items() if l.statement == "income_statement"}
    assert bs == {f"{i:03d}" for i in range(1, 97)} | {"301"}
    assert ipi == {f"{i:03d}" for i in range(110, 190)}


def test_formula_ranges_and_minus_terms():
    assert parse_formula("005do008") == ((1, "005"), (1, "006"), (1, "007"), (1, "008"))
    assert parse_formula("058-059") == ((1, "058"), (-1, "059"))


def test_profit_case_counts_tax_once():
    # pre-tax profit 100, tax 20 -> net profit 80 (not 60, see the checkpoint in the log)
    st = tree.evaluate({"180": 100_00, "184": 20_00})
    assert (st["182"], st["183"], st["186"], st["187"]) == (100_00, 0, 80_00, 0)


def test_loss_case_adds_tax_to_loss():
    st = tree.evaluate({"181": 50_00, "184": 5_00})
    assert (st["182"], st["183"], st["186"], st["187"]) == (0, 50_00, 0, 55_00)


def test_negative_retained_earnings_move_to_loss_side():
    st = tree.evaluate({"068": -30_00})
    assert (st["068"], st["069"], st["056"]) == (0, 30_00, -30_00)


def test_balance_signs():
    assert tree.balance_signs["052"] == 1  # cash: debit balance
    assert tree.balance_signs["093"] == -1  # payables: credit balance
    assert tree.balance_signs["059"] == 1  # uncalled capital is deducted from equity: debit
    assert tree.balance_signs["112"] == -1  # revenue: credit
    assert tree.balance_signs["140"] == 1  # wages: debit
