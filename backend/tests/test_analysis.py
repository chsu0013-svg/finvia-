"""Pure analysis tests (no web server needed)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis  # noqa: E402


def write(tmp_path, name, text, enc="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(enc))
    return p


@pytest.mark.parametrize("text", [
    "Date,Description,Debit,Credit,Balance\n01/09/2026,Sales,,12000,52000\n05/09/2026,Laptop,2400,,49600\n",
    "Date,Description,Type,Amount,Balance\n2026-09-01,Sales,Credit,12000,52000\n2026-09-05,Laptop,Debit,2400,49600\n",
    "Transaction Date;Details;Money Out;Money In;Balance\n01/09/2026;Sales;;\"12,000.00\";\"52,000.00\"\n05/09/2026;Laptop;\"2,400.00\";;\"49,600.00\"\n",
    "Bank of X statement\nAccount 123\n\nDate,Narration,Amount,Balance\n01-09-2026,Sales,RM 12000,52000\n05-09-2026,Laptop,(2400),49600\n",
    "日期,摘要,支出,存入,餘額\n2026/09/01,貨款,,12000,52000\n2026/09/05,Laptop,2400,,49600\n",
])
def test_many_formats_parse(tmp_path, text):
    df = analysis._read_table(write(tmp_path, "s.csv", text))
    assert len(df) == 2
    assert df["amount"].tolist() == [12000, -2400]


def test_big5_and_bom(tmp_path):
    t = "日期,摘要,支出,存入\n2026/09/01,貨款,,500\n"
    assert len(analysis._read_table(write(tmp_path, "a.csv", t, "cp950"))) == 1
    assert len(analysis._read_table(write(tmp_path, "b.csv", t, "utf-8-sig"))) == 1


def test_forecast_uses_recurring_payments_and_is_not_flat(tmp_path):
    import datetime as dt
    rows, bal = ["Date,Description,Debit,Credit,Balance"], 40000
    for i in range(90):
        d = dt.date(2026, 6, 1) + dt.timedelta(days=i)
        if d.day == 25:
            bal -= 9500; rows.append(f"{d:%d/%m/%Y},Payroll,9500,,{bal}")
        if d.weekday() == 1:
            bal += 4000; rows.append(f"{d:%d/%m/%Y},Customer payment,,4000,{bal}")
    df = analysis._read_table(write(tmp_path, "r.csv", "\n".join(rows)))
    dash = analysis._from_df(df, [], [])
    assert any(e[2].lower().startswith("payroll") for e in dash["events"])
    assert len(set(round(v) for v in dash["balances"])) > 5
    assert len(dash["balances"]) == len(dash["band_low"]) == len(dash["band_high"]) == 31
    assert set(dash["windows"]) == {"7", "14", "30"}
    assert dash["cash"]["history"] and dash["cash"]["recent"]


def test_garbage_file_returns_message_not_exception(tmp_path):
    p = write(tmp_path, "x.csv", "foo,bar\n1,2\n")
    res = analysis.analyse_upload(p, "x.csv", analysis.new_state())
    assert res["ok"] is False and "Could not analyse" in res["message"]


def test_demo_dashboard_has_cash_detail():
    d = analysis.build_demo_dashboard(analysis.new_state())
    assert min(d["balances"]) == 11150 and d["cash"]["categories"] and d["cash"]["recent"]
