"""Finvia analysis: demo data, tolerant CSV/XLSX parsing, a recurring-aware 30-day
forecast, cash breakdowns and tax signals.

Prototype note: the forecast is an *estimate* built from the uploaded history
(recurring payments + typical weekday movement). Tax items are signals only.
"""
from __future__ import annotations

import csv
import math
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DEMO_BUFFER = 15000
START = 48600.0
HORIZON = 30

# [day, amount, label, type]
DEMO_EVENTS = [
    [3, -6200, "Supplier invoice", "out"],
    [7, -9500, "Payroll", "out"],
    [11, -6800, "Rent and utilities", "out"],
    [15, -8450, "Stock purchase", "out"],
    [19, -6500, "Quarterly tax instalment", "out"],
    [22, 12000, "Customer payments", "in"],
    [26, 10000, "Customer payments", "in"],
    [29, 9800, "Customer payments", "in"],
]

DEMO_TAX = [
    {"title": "Equipment purchase", "text": "Possible capital allowance signal", "amount": "RM 2,400"},
    {"title": "Software subscriptions", "text": "Possible digital expense signal", "amount": "RM 860"},
]

TAX_RULES = [
    ("Equipment purchase", "Possible capital allowance signal",
     ["equipment", "machine", "machinery", "computer", "laptop", "printer", "furniture"]),
    ("Software subscriptions", "Possible digital expense signal",
     ["software", "subscription", "cloud", "hosting", "saas", "website", "domain"]),
    ("Training and courses", "Possible training expense signal",
     ["training", "course", "workshop", "seminar"]),
    ("Green investment", "Possible green incentive signal",
     ["solar", "energy saving", "electric vehicle"]),
]

CATEGORY_RULES = [
    ("Payroll", ["payroll", "salary", "salaries", "wages", "epf", "socso", "eis", "薪"]),
    ("Rent & utilities", ["rent", "utilities", "electric", "tnb", "water", "internet", "telco", "租"]),
    ("Suppliers & stock", ["supplier", "stock", "inventory", "purchase", "materials", "wholesale", "進貨"]),
    ("Tax", ["tax", "lhdn", "gst", "sst", "稅"]),
    ("Software & tools", ["software", "subscription", "cloud", "hosting", "saas", "domain"]),
    ("Equipment", ["equipment", "machine", "laptop", "computer", "printer", "furniture"]),
]

# Column aliases (English + Traditional Chinese). Order = priority.
ALIASES = {
    "date": ["transaction date", "posting date", "value date", "date", "日期", "交易日"],
    "desc": ["description", "details", "narration", "particulars", "transaction", "memo",
             "remarks", "reference", "payee", "摘要", "說明", "备注", "備註", "交易說明"],
    "amount": ["amount", "金額", "金额"],
    "debit": ["debit", "withdrawal", "money out", "paid out", "dr", "支出", "提款", "提出"],
    "credit": ["credit", "deposit", "money in", "paid in", "cr", "收入", "存入", "存款"],
    "balance": ["running balance", "balance", "餘額", "余额"],
    "type": ["type", "dr/cr", "cr/dr", "類別", "類型"],
}


def new_state():
    """A fresh per-visitor workspace. Kept in memory by the API layer."""
    return {"dashboard": None, "tax": None, "docs": []}


# ---------------------------------------------------------------- helpers
def _f(x, nd=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if (math.isnan(v) or math.isinf(v)) else round(v, nd)


def _rm(n):
    return f"RM {round(n):,}"


def _category(desc: str) -> str:
    d = desc.lower()
    for name, words in CATEGORY_RULES:
        if any(w in d for w in words):
            return name
    return "Other"


def _series(start, events):
    s = [float(start)]
    for day in range(1, HORIZON + 1):
        s.append(s[-1] + sum(e[1] for e in events if e[0] == day))
    return s


# ---------------------------------------------------------------- parsing
def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp950", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("latin-1", errors="replace")


def _raw_grid(path: Path) -> pd.DataFrame:
    """Read the file as a grid of strings with no assumptions about the header."""
    if path.suffix.lower() == ".csv":
        text = _decode(path.read_bytes())
        lines = [ln for ln in text.splitlines() if ln.strip()]
        # Pick the delimiter that yields the most rows with 3+ fields (ignores title lines above the table).
        best, best_score = ",", -1
        for d in (",", ";", "\t", "|"):
            score = sum(1 for r in csv.reader(lines, delimiter=d) if len(r) >= 3)
            if score > best_score:
                best, best_score = d, score
        rows = [[c.strip() for c in r] for r in csv.reader(lines, delimiter=best)]
        width = max((len(r) for r in rows), default=0)
        if width == 0:
            return pd.DataFrame()
        return pd.DataFrame([r + [None] * (width - len(r)) for r in rows], dtype=object)
    return pd.read_excel(path, header=None, dtype=str)


def _match(cell: str, key: str) -> bool:
    c = cell.strip().lower()
    for alias in ALIASES[key]:
        if len(alias) <= 3 and alias.isascii():   # "dr", "cr", "eis"... exact only
            if c == alias:
                return True
        elif alias in c:
            return True
    return False


def _find_header(grid: pd.DataFrame) -> int:
    for i in range(min(len(grid), 25)):
        cells = [str(v) for v in grid.iloc[i].tolist() if isinstance(v, str) or pd.notna(v)]
        has_date = any(_match(c, "date") for c in cells)
        has_money = any(_match(c, k) for c in cells for k in ("amount", "debit", "credit"))
        if has_date and has_money:
            return i
    raise ValueError("Could not find a header row. The file needs a Date column and either "
                     "Amount, or Debit and Credit.")


def _pick(cols: list[str], key: str, taken: set):
    for alias in ALIASES[key]:
        for c in cols:
            if c in taken:
                continue
            cl = c.strip().lower()
            ok = (cl == alias) if (len(alias) <= 3 and alias.isascii()) else (alias in cl)
            if ok:
                return c
    return None


def _num(series: pd.Series) -> pd.Series:
    """'RM 1,200.50', '(300.00)', '1 200,5-', '300 DR' -> floats (negative where marked)."""
    s = series.astype(str).str.strip()
    neg = s.str.contains(r"^\(.*\)$|-\s*$|\bDR\b|^\s*[-−–]", case=False, regex=True)
    s = (s.str.replace("−", "-", regex=False).str.replace("–", "-", regex=False)
          .str.replace(r"(?i)rm|myr|usd|nt\$|\$|dr|cr", "", regex=True)
          .str.replace(r"[,\s()]", "", regex=True).str.replace("-", "", regex=False))
    v = pd.to_numeric(s, errors="coerce").abs()
    return v.where(~neg, -v)


def _dates(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.replace(r"\s+\d{1,2}:\d{2}(:\d{2})?.*$", "", regex=True)
    iso = s.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$").mean() > 0.5
    if iso:
        return pd.to_datetime(s.str.replace(".", "-", regex=False), errors="coerce")
    first = pd.to_numeric(s.str.extract(r"^(\d{1,2})[-/.]")[0], errors="coerce")
    second = pd.to_numeric(s.str.extract(r"^\d{1,2}[-/.](\d{1,2})")[0], errors="coerce")
    dayfirst = not (second.gt(12).any() and not first.gt(12).any())   # default day-first (MY/TW/UK)
    a = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst, format="mixed")
    return a


def _read_table(path: Path) -> pd.DataFrame:
    grid = _raw_grid(path).dropna(how="all")
    if grid.empty:
        raise ValueError("The file is empty.")
    h = _find_header(grid.reset_index(drop=True))
    grid = grid.reset_index(drop=True)
    cols = [str(c).strip() if pd.notna(c) else f"col{j}" for j, c in enumerate(grid.iloc[h].tolist())]
    body = grid.iloc[h + 1:].copy()
    body.columns = cols

    taken: set = set()
    date_c = _pick(cols, "date", taken); taken.add(date_c)
    amt_c = _pick(cols, "amount", taken); taken.add(amt_c)
    deb_c = _pick(cols, "debit", taken); taken.add(deb_c)
    cre_c = _pick(cols, "credit", taken); taken.add(cre_c)
    bal_c = _pick(cols, "balance", taken); taken.add(bal_c)
    typ_c = _pick(cols, "type", taken); taken.add(typ_c)
    desc_c = _pick(cols, "desc", taken)

    if not date_c:
        raise ValueError("No Date column found.")
    if amt_c:
        amount = _num(body[amt_c])
        if typ_c:   # e.g. Type = Debit/Credit with unsigned amounts
            t = body[typ_c].astype(str).str.lower()
            is_out = t.str.contains(r"debit|\bdr\b|out|withdraw|expense|支出|提")
            amount = amount.abs().where(~is_out, -amount.abs())
    elif deb_c or cre_c:
        d = _num(body[deb_c]).abs().fillna(0) if deb_c else 0
        c = _num(body[cre_c]).abs().fillna(0) if cre_c else 0
        amount = c - d
    else:
        raise ValueError("No amount column found. Add Amount, or Debit and Credit.")

    out = pd.DataFrame({
        "date": _dates(body[date_c]),
        "desc": body[desc_c].astype(str).str.strip() if desc_c else "",
        "amount": amount,
        "balance": _num(body[bal_c]) if bal_c else float("nan"),
    }).dropna(subset=["date", "amount"])
    out = out[out["amount"] != 0].sort_values("date", kind="stable").reset_index(drop=True)
    if out.empty:
        raise ValueError("No usable rows found. Check the Date and Amount columns contain values.")
    out["desc"] = out["desc"].replace({"nan": "", "None": ""})
    return out


def _tax_items(df):
    items = []
    spend = df[df["amount"] < 0]
    for title, text, words in TAX_RULES:
        pattern = r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b"
        hit = spend[spend["desc"].str.lower().str.contains(pattern, regex=True, na=False)]
        total = -hit["amount"].sum()
        if total > 0:
            items.append({"title": title, "text": text, "amount": _rm(total)})
    return items


# ---------------------------------------------------------------- forecast
def _norm_key(desc: str) -> str:
    return re.sub(r"[\d\W_]+", " ", desc.lower()).strip()[:24]


def _recurring(df, anchor):
    """Find payments that repeat on a weekly / fortnightly / monthly rhythm."""
    events, used = [], set()
    d = df.assign(key=df["desc"].map(_norm_key))
    d = d[d["key"] != ""]
    for (key, sign), g in d.groupby(["key", d["amount"] > 0]):
        if len(g) < 2:
            continue
        gaps = g["date"].diff().dt.days.dropna()
        gap = float(gaps.median())
        if not 6 <= gap <= 35:
            continue
        gap = int(round(gap))
        amt = float(g["amount"].median())
        nxt = g["date"].max() + timedelta(days=gap)
        label = g["desc"].iloc[-1][:32].title() or ("Expected payment in" if sign else "Expected payment")
        while (nxt - anchor).days <= HORIZON:
            off = (nxt - anchor).days
            if off >= 1:
                events.append([off, round(amt, 2), label, "in" if amt > 0 else "out"])
            nxt += timedelta(days=gap)
        used.update(g.index.tolist())
    return events, used


def _forecast(df):
    anchor = df["date"].max().normalize()
    first = df["date"].min().normalize()
    span = max((anchor - first).days + 1, 1)

    if df["balance"].notna().any():
        start = float(df["balance"].dropna().iloc[-1])
    else:
        start = float(df["amount"].sum())

    events, used = _recurring(df, anchor)
    rest = df.drop(index=list(used))

    # Fallback: nothing recurring -> surface the largest historic flows as estimated events.
    if not events:
        big_in = rest[rest["amount"] > 0].nlargest(3, "amount")
        big_out = rest[rest["amount"] < 0].nsmallest(4, "amount")
        for day, (_, r) in zip([8, 18, 27], big_in.iterrows()):
            events.append([day, round(float(r["amount"]), 2), (r["desc"][:32].title() or "Expected customer payment"), "in"])
        for day, (_, r) in zip([5, 12, 19, 26], big_out.iterrows()):
            events.append([day, round(float(r["amount"]), 2), (r["desc"][:32].title() or "Expected payment"), "out"])
        rest = rest.drop(index=list(big_in.index) + list(big_out.index))

    # Baseline: typical money in / money out per weekday from the non-scheduled history.
    full = pd.date_range(first, anchor, freq="D")
    norm = rest["date"].dt.normalize()
    pos, neg = rest["amount"] > 0, rest["amount"] < 0
    d_in = rest.loc[pos, "amount"].groupby(norm[pos]).sum().reindex(full, fill_value=0.0)
    d_out = (-rest.loc[neg, "amount"]).groupby(norm[neg]).sum().reindex(full, fill_value=0.0)
    w = min(1.0, span / 56.0)                       # trust weekday pattern only with enough history

    def weekday_profile(daily):
        overall = float(daily.mean())
        wd = daily.groupby(daily.index.dayofweek).mean().reindex(range(7)).fillna(overall)
        return {k: w * float(wd[k]) + (1 - w) * overall for k in range(7)}

    base_in, base_out = weekday_profile(d_in), weekday_profile(d_out)
    net_hist = d_in - d_out
    sd = float(net_hist.std()) if len(net_hist) > 2 else 0.0

    series, lo, hi = [start], [start], [start]
    flows_in, flows_out = [0.0], [0.0]
    for d in range(1, HORIZON + 1):
        day = anchor + timedelta(days=d)
        ev_in = sum(e[1] for e in events if e[0] == d and e[1] > 0)
        ev_out = -sum(e[1] for e in events if e[0] == d and e[1] < 0)
        fin, fout = base_in[day.dayofweek] + ev_in, base_out[day.dayofweek] + ev_out
        flows_in.append(fin); flows_out.append(fout)
        series.append(series[-1] + fin - fout)
        band = 0.77 * sd * math.sqrt(d)             # widening uncertainty band (about 80%)
        lo.append(series[-1] - band)
        hi.append(series[-1] + band)

    events = sorted(events, key=lambda e: e[0])[:16]
    return start, events, series, (lo, hi), anchor, (flows_in, flows_out)


# ---------------------------------------------------------------- dashboard payload
def _window_stats(series, events, n, buffer, flows=None):
    vals = series[: n + 1]
    low = min(vals)
    if flows:
        inflow, outflow = sum(flows[0][1: n + 1]), sum(flows[1][1: n + 1])
    else:
        inflow = sum(e[1] for e in events if e[0] <= n and e[1] > 0)
        outflow = -sum(e[1] for e in events if e[0] <= n and e[1] < 0)
    below = next((i for i, v in enumerate(vals) if v < buffer), None)
    return {
        "days": n, "low": _f(low), "low_day": vals.index(low), "end": _f(vals[-1]),
        "net": _f(vals[-1] - vals[0]), "inflow": _f(inflow), "outflow": _f(outflow),
        "first_below": below,
    }


def _signals(series, tax_items, buffer):
    out = []
    below = [i for i, v in enumerate(series) if v < buffer]
    if below:
        out.append({"type": "warn", "title": "Balance drops below buffer",
                    "text": f"Expected around day {below[0]}.", "amount": ""})
    for t in tax_items[:2]:
        out.append({"type": "tax", "title": t["title"], "text": t["text"], "amount": t["amount"]})
    return out


def _dashboard(*, start, events, series, band, tax_items, docs, buffer, anchor, method, note,
               avg_in, avg_out, categories, recent, history, tx_count, flows=None, demo=False):
    burn = max(0.0, avg_out - avg_in)
    return {
        "start": _f(start),
        "buffer": _f(buffer, 0),
        "as_of": (anchor.date() if hasattr(anchor, "date") else anchor).isoformat(),
        "demo": demo,
        "tx_count": tx_count,
        "forecast_method": method,
        "forecast_note": note,
        "balances": [_f(v) for v in series],
        "band_low": [_f(v) for v in band[0]],
        "band_high": [_f(v) for v in band[1]],
        "events": [[e[0], _f(e[1]), e[2], e[3]] for e in events],
        "windows": {str(n): _window_stats(series, events, n, buffer, flows) for n in (7, 14, 30)},
        "cash": {
            "avg_daily_in": _f(avg_in), "avg_daily_out": _f(avg_out),
            "runway_days": (int(start // burn) if burn > 0 and start > 0 else None),
            "safe_to_spend": _f(max(0.0, start - buffer)),
            "categories": categories, "recent": recent, "history": [_f(v) for v in history],
        },
        "signals": _signals(series, tax_items, buffer),
        "documents": docs,
    }


def _default_docs():
    return [
        {"title": "bank-statement-sep.csv", "text": "Analysed 128 transactions"},
        {"title": "invoice-1042.pdf", "text": "Stored for review"},
    ]


def build_demo_dashboard(state):
    if state["dashboard"]:
        return state["dashboard"]
    series = _series(START, DEMO_EVENTS)
    anchor = date.today()
    # A believable 30-day look-back so the Available cash view has something to show.
    hist = [START - 5200 + i * 175 + (-1) ** i * 600 for i in range(30)] + [START]
    cats = [{"name": "Suppliers & stock", "amount": 21400}, {"name": "Payroll", "amount": 19000},
            {"name": "Rent & utilities", "amount": 6800}, {"name": "Tax", "amount": 6500}]
    recent = [
        {"date": (anchor - timedelta(days=1)).isoformat(), "desc": "Customer payment - Lim Trading", "amount": 7400},
        {"date": (anchor - timedelta(days=3)).isoformat(), "desc": "Supplier invoice - Metro Foods", "amount": -3150},
        {"date": (anchor - timedelta(days=5)).isoformat(), "desc": "Cloud hosting subscription", "amount": -860},
        {"date": (anchor - timedelta(days=8)).isoformat(), "desc": "Customer payment - Aiman Cafe", "amount": 5200},
        {"date": (anchor - timedelta(days=10)).isoformat(), "desc": "Laptop purchase", "amount": -2400},
    ]
    return _dashboard(start=START, events=DEMO_EVENTS, series=series,
                      band=([v - 1500 - i * 120 for i, v in enumerate(series)],
                            [v + 1500 + i * 120 for i, v in enumerate(series)]),
                      tax_items=DEMO_TAX, docs=_default_docs(), buffer=DEMO_BUFFER, anchor=anchor,
                      method="Sample data", note="Upload a bank statement to replace this sample with your own forecast.",
                      avg_in=1050, avg_out=1750, categories=cats, recent=recent, history=hist,
                      tx_count=128, demo=True)


def build_tax_report(state):
    return {"items": state["tax"] or DEMO_TAX}


# ---------------------------------------------------------------- upload entry point
def _from_df(df, docs, tax):
    start, events, series, band, anchor, flows = _forecast(df)
    last30 = df[df["date"] > anchor - timedelta(days=30)]
    span = max((anchor - df["date"].min().normalize()).days + 1, 1)
    window = min(span, 30)
    avg_in = float(last30[last30["amount"] > 0]["amount"].sum()) / window
    avg_out = float(-last30[last30["amount"] < 0]["amount"].sum()) / window

    spend = last30[last30["amount"] < 0].copy()
    spend["cat"] = spend["desc"].map(_category)
    cats = (spend.groupby("cat")["amount"].sum().mul(-1).sort_values(ascending=False).head(5))
    categories = [{"name": k, "amount": _f(v, 0)} for k, v in cats.items()]

    recent = [{"date": r.date.date().isoformat(), "desc": (r.desc or "Transaction")[:48], "amount": _f(r.amount)}
              for r in df.tail(6).iloc[::-1].itertuples()]

    # Actual balance trail for the look-back chart (running balance if supplied, else rebuilt).
    if df["balance"].notna().any():
        trail = df.set_index(df["date"].dt.normalize())["balance"].dropna()
        trail = trail[~trail.index.duplicated(keep="last")]
    else:
        trail = df.groupby(df["date"].dt.normalize())["amount"].sum().cumsum()
    idx = pd.date_range(max(trail.index.min(), anchor - timedelta(days=29)), anchor, freq="D")
    history = trail.reindex(idx, method="ffill").bfill().tolist() or [start]

    buffer = max(500.0, math.ceil(avg_out * 14 / 500) * 500) if avg_out else DEMO_BUFFER
    return _dashboard(
        start=start, events=events, series=series, band=band, tax_items=tax, docs=docs, buffer=buffer,
        anchor=anchor, method="Estimated from your uploaded transactions",
        note=("Repeating payments are projected on their usual rhythm; everything else follows your "
              "typical movement for each day of the week. The shaded area shows likely range."),
        avg_in=avg_in, avg_out=avg_out, categories=categories, recent=recent, history=history,
        tx_count=len(df), flows=flows)


def analyse_upload(path: Path, filename: str, state):
    ext = Path(filename).suffix.lower()
    docs = state["docs"]

    if ext not in {".csv", ".xlsx", ".xls"}:
        docs.insert(0, {"title": filename, "text": "Stored. Text extraction is not enabled yet."})
        del docs[4:]
        base = state["dashboard"] or build_demo_dashboard(state)
        return {"ok": True, "message": "File stored. Only CSV and Excel files are analysed for now.",
                "dashboard": base | {"documents": list(docs)}}

    try:
        df = _read_table(path)
        tax = _tax_items(df)
        docs.insert(0, {"title": filename, "text": f"Analysed {len(df)} transactions"})
        del docs[4:]
        dash = _from_df(df, list(docs), tax)
    except Exception as exc:   # never let a bad file take the request down
        if docs and docs[0]["title"] == filename:
            docs.pop(0)
        return {"ok": False, "message": f"Could not analyse this file: {exc}",
                "dashboard": build_demo_dashboard(state)}

    state["tax"] = tax
    state["dashboard"] = dash
    return {"ok": True,
            "message": f"Analysed {len(df)} transactions. The forecast is an estimate from your history.",
            "dashboard": dash}
