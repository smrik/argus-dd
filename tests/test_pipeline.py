import csv
import json
import shutil
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest

from argus.aop import AopTree
from argus.chart import Account, load_chart
from argus.checks import cross_check, load_filed
from argus.layouts import write_all
from argus.mapping import rollup, statements_from_tb
from argus.pdf import pdftotext
from argus.synth import generate
from argus.tb import TbRow, column
from argus.wrangle import main, wrangle

FORMATS = ("minimax_pdf", "analitika_pdf", "furs_pdf", "monthly_xlsx",
           "quirky_xlsx", "tab_csv", "erp", "export")


@pytest.fixture(scope="module", params=[("trading", 1), ("services", 7), ("trading", 3)])
def rendered(request, tmp_path_factory):
    company = generate(*request.param)
    out = tmp_path_factory.mktemp("pipeline")
    write_all(company, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {e["format"] for e in manifest.values()} == {*FORMATS, "tidy", "numeric_konto_xlsx"}
    return company, out, manifest


@pytest.mark.parametrize("fmt", FORMATS)
def test_pipeline(rendered, tmp_path, fmt):
    if fmt.endswith("_pdf") and pdftotext() is None:
        pytest.skip("xpdf -table unavailable")
    company, out, manifest = rendered
    chart, tree = load_chart(), AopTree.load()
    entries = [(name, entry) for name, entry in manifest.items() if entry["format"] == fmt]
    assert entries
    for name, entry in entries:
        neutral = tmp_path / ("input" + (out / name).suffix)
        shutil.copyfile(out / name, neutral)
        result = wrangle(neutral)
        results = result if isinstance(result, dict) else {result.year: result}
        years = entry["year"] if isinstance(entry["year"], list) else [entry["year"]]
        assert set(results) == set(years)
        for year, result in results.items():
            rows, problems = rollup(result.rows, chart)
            assert problems == []
            expected = next(y.rows for y in company.years if y.year == year)
            # FURS omits zero closings; monthly exports retain only net movement.
            assert {r.konto: r.closing for r in rows if r.closing} == {
                r.konto: r.closing for r in expected if r.closing}
            mapped = statements_from_tb(column(rows, "closing"), chart, tree)
            assert cross_check(mapped, load_filed(out / "statements_filed.csv", year)) == []


def test_tidy_rollup_and_cent_variance(rendered):
    company, out, _ = rendered
    chart, tree = load_chart(), AopTree.load()
    results = wrangle(out / "tb_tidy.csv")
    for year in company.years:
        rows, problems = rollup(results[year.year].rows, chart)
        assert problems == []
        assert rows == year.rows
        target = next(r for r in rows if chart[r.konto].aop == "112")
        changed = [replace(r, closing=r.closing - 1) if r == target else r for r in rows]
        mapped = statements_from_tb(column(changed, "closing"), chart, tree)
        problems = cross_check(mapped, load_filed(out / "statements_filed.csv", year.year))
        assert problems
        assert any(p.startswith("AOP 110:") for p in problems)
        assert any(p.startswith("AOP 112:") for p in problems)
        assert all(p.startswith("AOP ") and "diff" in p for p in problems)


def test_numeric_konto_requires_judgement(rendered, tmp_path):
    _, out, manifest = rendered
    for name, entry in manifest.items():
        if entry["format"] != "numeric_konto_xlsx":
            continue
        source = tmp_path / "input.xlsx"
        shutil.copyfile(out / name, source)
        result = wrangle(source)
        assert result.format == "numeric_konto_xlsx"
        assert any("konto stored as number" in p for p in result.problems)


def test_longest_prefix_and_unknown():
    chart = {k: Account(k, f"chart {k}", "110", Fraction(1)) for k in ("12", "120", "1200")}
    rows = [TbRow(k, "analytic", 1, 2, 3, 0) for k in ("1200", "12001", "120000")]
    rows += [TbRow("1201", "other", 4, 5, 6, 3), TbRow("77777", "unknown", 9, 9, 9, 9)]
    actual, problems = rollup(rows, chart)
    assert actual == [TbRow("120", "chart 120", 4, 5, 6, 3),
                      TbRow("1200", "chart 1200", 3, 6, 9, 0)]
    assert len(problems) == 1 and "77777" in problems[0]


def test_cross_check_format_and_tolerance():
    mapped, filed = {"110": 123456, "001": 999}, {"110": 120000}
    assert cross_check(mapped, filed) == [
        "AOP 110: TB 1.234,56 vs filed 1.200,00 (diff 34,56)"]
    assert cross_check(mapped, filed, tolerance=3456) == []
    assert cross_check({"110": 119999}, filed) == [
        "AOP 110: TB 1.199,99 vs filed 1.200,00 (diff -0,01)"]
    assert cross_check({"110": 10**18 + 1}, {"110": 10**18}) == [
        "AOP 110: TB 10.000.000.000.000.000,01 vs filed 10.000.000.000.000.000,00 (diff 0,01)"]


def test_load_filed(tmp_path):
    path = tmp_path / "filed.csv"
    path.write_text("year,statement,aop,label,amount\n"
                    "2024,balance_sheet,001,Assets,1234.56\n"
                    "2024,income_statement,110,Sales,-0.01\n"
                    "2024,income_statement,188,Headcount,3.5\n"
                    "2024,income_statement,189,Months,12\n"
                    "2023,balance_sheet,001,Assets,1.00\n", encoding="utf-8")
    assert load_filed(path, 2024) == {"001": 123456, "110": -1}
    with pytest.raises(ValueError, match="no filed"):
        load_filed(path, 2022)
    path.write_text("year,statement,aop,label,amount\n2024,income_statement,110,Sales,1.234\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="2-decimal"):
        load_filed(path, 2024)


def test_cli_filed(rendered, tmp_path, capsys):
    company, out, manifest = rendered
    for fmt in ("tab_csv", "quirky_xlsx", "monthly_xlsx"):
        name = next(n for n, e in manifest.items() if e["format"] == fmt)
        source = tmp_path / ("input" + (out / name).suffix)
        shutil.copyfile(out / name, source)
        assert main([str(source), "--filed", str(out / "statements_filed.csv")]) == 0
        output = capsys.readouterr().out
        for aop in ("001", "110", "186", "187"):
            assert f"AOP {aop}" in output
        count = len(company.years) if fmt == "quirky_xlsx" else 1
        assert output.count("Cross-check: OK") == count


def test_cli_problems(rendered, tmp_path, capsys):
    _, out, _ = rendered
    source = tmp_path / "input.csv"
    shutil.copyfile(out / "tb_tidy.csv", source)
    with source.open(encoding="utf-8", newline="") as f:
        records = list(csv.reader(f))
    records[1][1] = "99999"
    with source.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(records)
    assert main([str(source), "--map"]) == 1
    assert "99999" in capsys.readouterr().out
    shutil.copyfile(out / "tb_tidy.csv", source)
    filed = tmp_path / "filed.csv"
    with (out / "statements_filed.csv").open(encoding="utf-8", newline="") as f:
        records = list(csv.reader(f))
    target = next(r for r in records[1:] if r[2] == "110")
    target[4] = str(Decimal(target[4]) + Decimal("0.01"))
    with filed.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(records)
    assert main([str(source), "--filed", str(filed)]) == 1
    assert "AOP 110:" in capsys.readouterr().out
