import csv
import json
import shutil
from dataclasses import replace
from time import perf_counter
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from argus.layouts import write_all
from argus.pdf import pdftotext
from argus.synth import generate
from argus.tb import TbRow
from argus.wrangle import Printed, cents, classify, main, read_pdf_lines, wrangle, wrangle_all

FIELDS = ("opening", "debit", "credit", "closing")
DATA = Path(__file__).resolve().parents[1] / "data"


def truth(path):
    grouped = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            grouped.setdefault(int(r["year"]), []).append(
                TbRow(r["konto"], r["name"], *(int(Decimal(r[k]) * 100) for k in FIELDS)))
    return grouped


@pytest.fixture(scope="module", params=[("trading", 1), ("services", 7)])
def rendered(request, tmp_path_factory):
    out = tmp_path_factory.mktemp("wrangle")
    write_all(generate(*request.param), out)
    return out, json.loads((out / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fmt", ["minimax_pdf", "analitika_pdf", "furs_pdf", "monthly_xlsx",
                                "quirky_xlsx", "tab_csv", "erp", "export", "tidy"])
def test_fixtures(rendered, tmp_path, fmt):
    if fmt.endswith("_pdf") and pdftotext() is None:
        pytest.skip("xpdf -table unavailable")
    out, manifest = rendered
    for name, entry in manifest.items():
        if entry["format"] != fmt:
            continue
        source = out / name
        neutral = tmp_path / ("input" + source.suffix)
        shutil.copyfile(source, neutral)
        actual = wrangle_all(neutral)
        expected = truth(out / entry["truth_file"])
        assert actual.keys() == expected.keys()
        unwrapped = wrangle(neutral)
        assert isinstance(unwrapped, dict) == (len(expected) > 1)
        for year, target in expected.items():
            r = actual[year]
            assert r.format == fmt
            assert r.net_only == (fmt == "monthly_xlsx")
            if fmt == "monthly_xlsx":
                net = lambda row: (row.konto, row.name, row.opening, row.debit - row.credit, row.closing)
                assert list(map(net, r.rows)) == list(map(net, target))
            elif fmt == "furs_pdf":
                assert r.rows == [row for row in target if row.closing]
                assert any("opening" in p for p in r.problems)
                assert sum(row.closing for row in r.rows) == 0
            else:
                assert r.rows == target
            if fmt != "furs_pdf":
                assert r.problems == []


def test_litija(tmp_path):
    if pdftotext() is None:
        pytest.skip("xpdf -table unavailable")
    neutral = tmp_path / "input.pdf"
    shutil.copyfile(DATA / "tb_web" / "litija_bruto_bilanca.pdf", neutral)
    r = wrangle(neutral)
    assert r.format == "minimax_pdf"
    assert r.rows == truth(DATA / "tb_real" / "svc_litija_2021.csv")[2021]
    assert r.problems == []
    assert len(r.dropped) == 102 + 1


def printed(code, opening, debit=0, credit=0):
    return Printed(TbRow(code, "", opening, debit, credit, opening + debit - credit), code)


def test_prefix_parent_reconciliation():
    rows = [printed("120", 200), printed("1200", 100), printed("12001", 100),
            printed("220", -200), printed("SKUPAJ", 0)]
    leaves, dropped, problems = classify(rows)
    assert [r.konto for r in leaves] == ["1200", "12001", "220"]
    assert {d[1] for d in dropped} == {"120", "SKUPAJ"}
    assert problems == []


def test_prefix_ambiguity():
    leaves, _, problems = classify([printed("1200", 0), printed("12001", 0), printed("SKUPAJ", 0)])
    assert [r.konto for r in leaves] == ["12001"]
    assert any("ambiguous total/leaf: 1200" in p for p in problems)


def test_competing_nonzero_classifications():
    rows = [printed("120", 300), printed("1200", 100), printed("12001", 100),
            printed("1202", 100), printed("12021", 100), printed("220", -300), printed("SKUPAJ", 0)]
    leaves, _, problems = classify(rows)
    assert {"12001", "12021"} <= {r.konto for r in leaves}
    assert any("ambiguous total/leaf:" in p and "1200" in p and "1202" in p for p in problems)


@pytest.mark.parametrize("value", ["-1.234,56", "1.234,56-", "(1.234,56)", "-1\u00a0234,56"])
def test_negative_amounts(value):
    assert cents(value) == -123456


def test_float_amount():
    assert cents(12.349) == 1235
    assert cents(2.675) == 268
    assert cents(-2.675) == -268


@pytest.mark.parametrize("value", ["1.234", "1,234.56", "1,2345"])
def test_ambiguous_amounts_rejected(value):
    with pytest.raises(ValueError):
        cents(value)


def test_missing_year_is_data_problem(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("Konto;Naziv konta;Otvoritveni saldo;Promet breme;Promet dobro;Končni saldo\n120;Test;0,00;0,00;0,00;0,00\n", encoding="utf-8")
    assert any("reporting year" in p for p in wrangle(path).problems)


def test_bad_tidy_returns_problems(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("year,konto,name,opening,debit,credit,closing\nwrong,120,Test,0,0,0,0\n", encoding="utf-8")
    assert any("invalid tidy row" in p for p in wrangle(path).problems)


def test_cli(rendered, tmp_path, capsys):
    out, manifest = rendered
    for fmt, status in [("tab_csv", 0), ("monthly_xlsx", 0), ("furs_pdf", 1)]:
        if fmt.endswith("_pdf") and pdftotext() is None:
            continue
        name = next(n for n, e in manifest.items() if e["format"] == fmt)
        neutral = tmp_path / ("input" + Path(name).suffix)
        shutil.copyfile(out / name, neutral)
        target = tmp_path / "tidy.csv"
        assert main([str(neutral), "--out", str(target)]) == status
        expected = {year: result.rows for year, result in wrangle_all(neutral).items()}
        assert truth(target) == expected
        output = capsys.readouterr().out
        assert fmt in output and "rows=" in output and "dropped=" in output
        if fmt == "monthly_xlsx":
            assert "NET ONLY: gross debit/credit not recoverable" in output


def test_bad_data_returns_problems(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text('Bruto bilanca za leto 2021\nKonto;Naziv konta;Otvoritveni saldo;Promet breme;Promet dobro;Končni saldo\n120;Test;bad;0,00;0,00;0,00\n', encoding="utf-8")
    assert any("invalid amounts" in p for p in wrangle(path).problems)


def test_label_totals_checked(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text('Bruto bilanca za leto 2021\nKonto;Naziv konta;Otvoritveni saldo;Promet breme;Promet dobro;Končni saldo\n120;Test;0,00;1,00;1,00;0,00\nSkupaj;;0,00;2,00;2,00;0,00\n', encoding="utf-8")
    r = wrangle(path)
    assert len(r.dropped) == 1
    assert any("does not equal leaf sums" in p for p in r.problems)


def test_classification_search_is_bounded():
    rows = []
    for i in range(1000):
        code = f"{i:04d}"
        v = 2**i if i < 25 else 0
        rows.extend([printed(code, 0, v, v), printed(code + "0", 0, v, v)])
    started = perf_counter()
    leaves, dropped, problems = classify(rows)
    elapsed = perf_counter() - started
    assert elapsed < 1
    assert len(leaves) == 2000
    assert dropped == []
    assert any("classification search limit reached; totals unresolved under" in p for p in problems)


def test_global_resolution_keeps_locally_equal_leaf():
    rows = [printed(code, amount) for code, amount in
            [("1", 400), ("120", 200), ("1200", 100), ("1201", 100), ("220", -400), ("SKUPAJ", 0)]]
    leaves, dropped, problems = classify(rows)
    assert [r.konto for r in leaves] == ["120", "1200", "1201", "220"]
    assert {d[1] for d in dropped} == {"1", "SKUPAJ"}
    assert problems == []


def test_globally_indistinguishable_leaf_sets_are_reported():
    rows = [printed(code, amount) for code, amount in
            [("120", 200), ("1200", 100), ("1201", 100), ("220", -200),
             ("2200", -100), ("2201", -100), ("SKUPAJ", 0)]]
    leaves, dropped, problems = classify(rows)
    assert [r.konto for r in leaves] == ["1200", "1201", "2200", "2201"]
    assert {d[1] for d in dropped} == {"120", "220", "SKUPAJ"}
    assert any("ambiguous total/leaf:" in p and "120" in p and "220" in p for p in problems)


def analitika_lines(tmp_path, body, header="Bruto bilanca - Analitika 1", period="Temeljnice: 01.01.2021 - 31.12.2021"):
    path = tmp_path / "table.txt"
    path.write_text("\n".join([header, period, "Konto Naziv", "Otvoritev Promet Saldo",
                               "DB KR DB KR DB KR", *body]), encoding="utf-8")
    return path.read_text(encoding="utf-8").splitlines()


def test_numeric_konto_fixtures(rendered, tmp_path):
    out, manifest = rendered
    for name, entry in manifest.items():
        if entry["format"] != "numeric_konto_xlsx":
            continue
        neutral = tmp_path / "input.xlsx"
        shutil.copyfile(out / name, neutral)
        result = wrangle(neutral)
        expected = truth(out / entry["truth_file"])[entry["year"]]
        assert result.format == "numeric_konto_xlsx"
        assert result.rows == sorted([replace(r, konto=str(int(r.konto))) for r in expected],
                                     key=lambda r: r.konto)
        assert result.problems == [
            "konto stored as number in Bruto bilanca: leading zeros may be lost "
            "(e.g. 400 may be 0400); fix the export or map manually"]


@pytest.mark.parametrize("code", [400, 400.5, "0400"])
def test_konto_warning_follows_cell_type(tmp_path, code):
    numeric = isinstance(code, (int, float))
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(["Bruto bilanca za leto 2021"])
    ws.append(["Konto", "Naziv", "Otvoritev", "Promet D", "Promet K", "Saldo"])
    ws.append([code, "Oprema", 0, 1, 1, 0])
    ws.append([4001 if numeric else "04001", "Other", 0, 2, 2, 0])
    path = tmp_path / "input.xlsx"
    wb.save(path)
    result = wrangle(path)
    assert [r.konto for r in result.rows] == (["400", "4001"] if numeric else ["0400", "04001"])
    assert len(result.problems) == int(numeric)
    if numeric:
        assert result.problems == ["konto stored as number in Sheet: leading zeros may be lost "
                                   "(e.g. 400 may be 0400); fix the export or map manually"]


@pytest.mark.parametrize("saldo", ["", "0,00 0,00"])
def test_analitika_one_sided_and_zero_saldo(tmp_path, saldo):
    result = read_pdf_lines(analitika_lines(tmp_path, [
        "0030 Premozenjske pravice 0,00 0,00 972,34 0,00 972,34",
        "003 PREMOZENJSKE PRAVICE 0,00 0,00 972,34 0,00 972,34",
        "0080 Popravek 0,00 0,00 0,00 972,34 972,34",
        f"120 Zero 1,00 0,00 0,00 1,00 {saldo}",
        f"121 Other zero 0,00 1,00 1,00 0,00 {saldo}",
        "SKUPAJ 1,00 1,00 973,34 973,34",
    ]))[2021]
    assert result.rows == [TbRow("0030", "Premozenjske pravice", 0, 97234, 0, 97234),
                           TbRow("0080", "Popravek", 0, 0, 97234, -97234),
                           TbRow("120", "Zero", 100, 0, 100, 0),
                           TbRow("121", "Other zero", -100, 100, 0, 0)]
    assert result.problems == []


@pytest.mark.parametrize("amounts", ["0,00 0,00 1,00 0,00", "0,00 0,00 1,00 0,00 2,00",
                                   "0,00 0,00 0,00 1,00 2,00"])
def test_analitika_bad_printed_saldo(tmp_path, amounts):
    result = read_pdf_lines(analitika_lines(tmp_path, [f"120 Bad {amounts}"]))[2021]
    assert any("120: printed closing mismatch" in p for p in result.problems)


def test_analitika_total_difference_and_wrapped_name(tmp_path):
    result = read_pdf_lines(analitika_lines(tmp_path, [
        "Razlika",
        "0030 Wrapped 0,00 0,00 1,00 0,00 1,00", "name",
        "003 TOTAL 0,00 0,00 1,00 0,00 1,00 1,00 D",
        "0080 Other 0,00 0,00 0,00 1,00 1,00",
        "008 TOTAL 0,00 0,00 0,00 1,00 1,00 1,00 K",
        "SKUPAJ 0,00 0,00 1,00 1,00 1,00 1,00",
    ]))[2021]
    assert result.rows == [TbRow("0030", "Wrapped name", 0, 100, 0, 100),
                           TbRow("0080", "Other", 0, 0, 100, -100)]
    assert result.problems == []


def test_pdf_grouping_spaces_are_complete_amounts(tmp_path):
    lines = analitika_lines(tmp_path, [
        "120 Test 0,00 0,00 1 234,56 1 234,56 0,00 0,00",
        "SKUPAJ 0,00 0,00 1 234,56 1 234,56 0,00 0,00",
    ])
    result = read_pdf_lines(lines)[2021]
    assert result.rows == [TbRow("120", "Test", 0, 123456, 123456, 0)]
    assert result.problems == []


def test_pdf_extra_decimal_digits_are_rejected(tmp_path):
    lines = analitika_lines(tmp_path, [
        "120 Test 0,00 0,00 1,2345 1,2345 0,00 0,00",
        "SKUPAJ 0,00 0,00 0,00 0,00 0,00 0,00",
    ])
    result = read_pdf_lines(lines)[2021]
    assert result.rows == []
    assert any("120: invalid amounts" in p and "not a 2-decimal amount" in p for p in result.problems)


def test_pdf_unparseable_account_is_reported(tmp_path):
    lines = analitika_lines(tmp_path, [
        "120 Test 0,00 0,00 1,00 1,00 0,00 0,00",
        "121 Lost BAD BAD BAD BAD BAD BAD",
        "SKUPAJ 0,00 0,00 1,00 1,00 0,00 0,00",
    ])
    result = read_pdf_lines(lines)[2021]
    assert [r.konto for r in result.rows] == ["120"]
    assert any("121: invalid amounts" in p for p in result.problems)


def test_pdf_generic_word_does_not_select_minimax(tmp_path):
    lines = analitika_lines(tmp_path, [
        "ZACETNO",
        "120 Test 0,00 0,00 1,00 1,00 0,00 0,00",
        "SKUPAJ 0,00 0,00 1,00 1,00 0,00 0,00",
    ])
    result = read_pdf_lines(lines)[2021]
    assert result.format == "analitika_pdf"
    assert result.rows == [TbRow("120", "Test", 0, 100, 100, 0)]
    assert result.problems == []


def test_pdf_period_precedes_print_year(tmp_path):
    lines = analitika_lines(tmp_path, [
        "120 Test 0,00 0,00 1,00 1,00 0,00 0,00",
        "SKUPAJ 0,00 0,00 1,00 1,00 0,00 0,00",
    ], header="Bruto bilanca - Izpis: 15.02.2022\nAnalitika")
    result = read_pdf_lines(lines)
    assert list(result) == [2021]
    assert result[2021].problems == []


def test_pdf_page_headers_do_not_extend_account_names(tmp_path):
    lines = analitika_lines(tmp_path, [
        "120 Banka 0,00 0,00 1,00 1,00 0,00 0,00",
        "Stran: 1/2",
        "Konto Naziv", "Otvoritev Promet Saldo", "DB KR DB KR DB KR",
        "121 Other 0,00 0,00 1,00 1,00 0,00 0,00",
        "SKUPAJ 0,00 0,00 2,00 2,00 0,00 0,00",
    ])
    result = read_pdf_lines(lines)[2021]
    assert [r.name for r in result.rows] == ["Banka", "Other"]
    assert result.problems == []


def test_cli_exports_years_accounts_and_nonzero_amounts(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text(
        "year,konto,name,opening,debit,credit,closing\n"
        "2021,120,Banka,1.00,2.00,0.00,3.00\n"
        "2021,220,Other,-1.00,0.00,2.00,-3.00\n"
        "2022,120,Banka,3.00,4.00,0.00,7.00\n"
        "2022,220,Other,-3.00,0.00,4.00,-7.00\n",
        encoding="utf-8",
    )
    target = tmp_path / "tidy.csv"
    assert main([str(source), "--out", str(target)]) == 0
    assert truth(target) == {
        2021: [TbRow("120", "Banka", 100, 200, 0, 300),
               TbRow("220", "Other", -100, 0, 200, -300)],
        2022: [TbRow("120", "Banka", 300, 400, 0, 700),
               TbRow("220", "Other", -300, 0, 400, -700)],
    }
