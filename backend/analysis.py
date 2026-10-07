"""Finvia analysis: demo data, CSV/XLSX parsing, a simple 30-day forecast and tax signals.

This is a prototype. The forecast is an estimate from average cash movement,
and tax items are signals only, not confirmed eligibility.
"""
import re
from pathlib import Path

import pandas as pd

BUFFER = 15000
START = 48600.0

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

def new_state():
    """A fresh per-visitor workspace. Kept in memory by the API layer."""
    return {"dashboard": None, "tax": None, "docs": []}


def _rm(n):
    return f"RM {round(n):,}"


def _series(start, events):
    s = [float(start)]
    for day in range(1, 31):
        s.append(s[-1] + sum(e[1] for e in events if e[0] == day))
    return s


def _signals(series, tax_items):
    out = []
    low = min(series)
    if low < BUFFER:
        below = [i for i, v in enumerate(series) if v < BUFFER]
        out.append({
            "type": "warn",
            "title": "Balance drops below buffer",
            "text": f"Expected around day {below[0]}.",
            "amount": "",
        })
    for t in tax_items[:2]:
        out.append({"type": "tax", "title": t["title"], "text": t["text"], "amount": t["amount"]})
    return out


def _dashboard(start, events, series, tax_items, docs):
    return {
        "start": start,
        "forecast_method": "Estimated from uploaded transaction history",
        "forecast_note": "Historical net movement is smoothed between the largest estimated inflow/outflow events.",
        "balances": [round(v, 2) for v in series],
        "events": events,
        "signals": _signals(series, tax_items),
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
    return _dashboard(START, DEMO_EVENTS, series, DEMO_TAX, _default_docs())


def build_tax_report(state):
    return {"items": state["tax"] or DEMO_TAX}


# ---------- Parsing ----------
def _find(cols, names):
    for name in names:
        for c in cols:
            if name in c:
                return c
    return None


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    cols = list(df.columns)

    date_c = _find(cols, ["date"])
    desc_c = _find(cols, ["description", "details", "narration", "particulars", "memo", "reference"])
    amt_c = _find(cols, ["amount"])
    debit_c = _find(cols, ["debit", "withdrawal", "money out"])
    credit_c = _find(cols, ["credit", "deposit", "money in"])
    bal_c = _find(cols, ["balance"])

    if not date_c:
        raise ValueError("No date column found. Add a column called Date.")
    if amt_c:
        amount = pd.to_numeric(df[amt_c].astype(str).str.replace(",", ""), errors="coerce")
    elif debit_c or credit_c:
        d = pd.to_numeric(df[debit_c].astype(str).str.replace(",", ""), errors="coerce").fillna(0) if debit_c else 0
        c = pd.to_numeric(df[credit_c].astype(str).str.replace(",", ""), errors="coerce").fillna(0) if credit_c else 0
        amount = c - d
    else:
        raise ValueError("No amount column found. Add Amount, or Debit and Credit.")

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_c], errors="coerce", dayfirst=True),
        "desc": df[desc_c].astype(str) if desc_c else "",
        "amount": amount,
        "balance": pd.to_numeric(df[bal_c].astype(str).str.replace(",", ""), errors="coerce") if bal_c else None,
    }).dropna(subset=["date", "amount"]).sort_values("date")
    if out.empty:
        raise ValueError("No usable rows found in the file.")
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


def _forecast(df):
    """Build a transparent 30-day estimate from the uploaded transaction history.

    The latest available balance is the starting point when present. The largest
    historical inflows/outflows are surfaced as dated estimated events, while the
    remaining historical net movement is spread evenly across the forecast horizon.
    This keeps the chart tied to the user's uploaded data without pretending the
    prototype knows future invoices or customer payment dates.
    """
    span = max((df["date"].max() - df["date"].min()).days + 1, 1)
    if df["balance"].notna().any():
        start = float(df["balance"].dropna().iloc[-1])
    else:
        start = float(df["amount"].sum())

    inflow = df[df["amount"] > 0].copy()
    inflow["abs"] = inflow["amount"]
    outflow = df[df["amount"] < 0].copy()
    outflow["abs"] = -outflow["amount"]

    events = []
    inflow_days = [8, 18, 27]
    outflow_days = [5, 12, 19, 26]

    for day, (_, row) in zip(inflow_days, inflow.sort_values("abs", ascending=False).head(3).iterrows()):
        label = str(row["desc"]).strip()[:32].title() or "Expected customer payment"
        events.append([day, round(float(row["amount"]), 2), label, "in"])

    for day, (_, row) in zip(outflow_days, outflow.sort_values("abs", ascending=False).head(4).iterrows()):
        label = str(row["desc"]).strip()[:32].title() or "Expected payment"
        events.append([day, round(float(row["amount"]), 2), label, "out"])

    scheduled_total = sum(float(e[1]) for e in events)
    residual_daily = (float(df["amount"].sum()) - scheduled_total) / span

    series = [start]
    for d in range(1, 31):
        scheduled = sum(e[1] for e in events if e[0] == d)
        series.append(series[-1] + residual_daily + scheduled)

    events.sort(key=lambda e: e[0])
    return start, events, series


# ---------- Public: upload analysis ----------
def analyse_upload(path: Path, filename: str, state):
    ext = Path(filename).suffix.lower()
    docs = state["docs"]

    if ext not in {".csv", ".xlsx", ".xls"}:
        docs.insert(0, {"title": filename, "text": "Stored. Text extraction is not enabled yet."})
        del docs[4:]
        base = state["dashboard"] or build_demo_dashboard(state)
        return {
            "message": "File stored. Only CSV and XLSX files are analysed for now.",
            "dashboard": base | {"documents": list(docs)},
        }

    try:
        df = _read_table(path)
        start, events, series = _forecast(df)
        tax = _tax_items(df)
    except Exception as exc:
        return {
            "message": f"Could not analyse this file: {exc}",
            "dashboard": build_demo_dashboard(state),
        }

    docs.insert(0, {"title": filename, "text": f"Analysed {len(df)} transactions"})
    del docs[4:]
    state["tax"] = tax
    state["dashboard"] = _dashboard(start, events, series, tax, list(docs))
    return {
        "message": f"Analysed {len(df)} transactions. The forecast is an estimate from your average cash movement.",
        "dashboard": state["dashboard"],
    }
