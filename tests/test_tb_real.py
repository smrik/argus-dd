import csv
import json
import re
from decimal import Decimal
from pathlib import Path

from argus.checks import check_tb
from argus.tb import TbRow

DATA = Path(__file__).resolve().parents[1] / "data" / "tb_real"


def test_litija_real_tb():
    source = json.loads((DATA / "svc_litija_2021.source.json").read_text(encoding="utf-8"))
    with (DATA / "svc_litija_2021.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["year", "konto", "name", "opening", "debit", "credit", "closing"]
        rows = []
        for row in reader:
            assert row["year"] == "2021"
            assert row["name"] == ""
            amounts = []
            for field in ("opening", "debit", "credit", "closing"):
                assert re.fullmatch(r"-?[0-9]+\.[0-9]{2}", row[field])
                amounts.append(int(Decimal(row[field]) * 100))
            rows.append(TbRow(row["konto"], row["name"], *amounts))
    assert check_tb(rows) == []
    assert len(rows) == source["rows"] == 95
    assert [r.konto for r in rows] == sorted(r.konto for r in rows)
    assert all(re.fullmatch(r"[0-9]{4,7}", r.konto) or (
        re.fullmatch(r"[0-9]{3}", r.konto) and r.konto in source["short_leaf_konti"]
    ) for r in rows)
    assert all(r.closing == 0 for r in rows if r.konto[0] in "478")
