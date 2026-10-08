"""Market data engine for the dashboard (Yahoo Finance public chart API).

Provides:
  build_payload(extra, force)  -> ETF universe + metrics (RS, RRG, indicators, history)
  build_scanner(force)         -> stocks held by the strongest ETFs, with the same metrics
"""
import json
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd

BENCHMARK = "SPY"
CACHE_TTL = 300      # seconds a downloaded history is reused
HIST_DAYS = 252      # days of history sent to the browser for charts
HORIZONS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
RS_WEIGHTS = {"1m": 0.2, "3m": 0.4, "6m": 0.2, "12m": 0.2}

ETFS = [
    # Technology
    ("IGV", "Software / SaaS", "Technology"),
    ("SMH", "Semiconductors", "Technology"),
    ("CIBR", "Cybersecurity", "Technology"),
    ("SRVR", "Data Centers & Infrastructure", "Technology"),
    # Healthcare
    ("PPH", "Pharmaceuticals", "Healthcare"),
    ("XBI", "Biotech (Equal Weight)", "Healthcare"),
    ("IHI", "Medical Devices", "Healthcare"),
    # Financials
    ("KRE", "Regional Banking", "Financials"),
    ("IPAY", "Fintech & Digital Payments", "Financials"),
    # Industrials
    ("ITA", "Aerospace & Defense", "Industrials"),
    ("IYT", "Transportation", "Industrials"),
    ("PAVE", "Infrastructure Development", "Industrials"),
    # Commodities & Energy
    ("XOP", "Oil & Gas Exploration", "Commodities & Energy"),
    ("URA", "Uranium & Nuclear", "Commodities & Energy"),
    ("GDX", "Gold Miners", "Commodities & Energy"),
    ("XME", "Metals & Mining", "Commodities & Energy"),
    # Themes
    ("BOTZ", "AI & Robotics", "Themes"),
    ("ICLN", "Clean Energy", "Themes"),
    ("LIT", "Lithium & EV Batteries", "Themes"),
    # SPDR sectors
    ("XLK", "Technology Sector", "Sectors (SPDR)"),
    ("XLF", "Financials Sector", "Sectors (SPDR)"),
    ("XLE", "Energy Sector", "Sectors (SPDR)"),
    ("XLV", "Health Care Sector", "Sectors (SPDR)"),
    ("XLY", "Consumer Discretionary", "Sectors (SPDR)"),
    ("XLP", "Consumer Staples", "Sectors (SPDR)"),
    ("XLI", "Industrials Sector", "Sectors (SPDR)"),
    ("XLB", "Materials Sector", "Sectors (SPDR)"),
    ("XLU", "Utilities Sector", "Sectors (SPDR)"),
    ("XLRE", "Real Estate Sector", "Sectors (SPDR)"),
    ("XLC", "Communication Services", "Sectors (SPDR)"),
]
CATEGORIES = ["Technology", "Healthcare", "Financials", "Industrials",
              "Commodities & Energy", "Themes", "Sectors (SPDR)", "Watchlist"]

# Curated approximate top holdings (static list - review occasionally; holdings drift over time).
HOLDINGS = {
    "IGV": ["MSFT", "ORCL", "CRM", "PLTR", "NOW", "INTU", "ADBE", "PANW", "CRWD", "APP"],
    "SMH": ["NVDA", "TSM", "AVGO", "AMD", "ASML", "MU", "QCOM", "LRCX", "AMAT", "KLAC"],
    "CIBR": ["AVGO", "CRWD", "PANW", "CSCO", "FTNT", "ZS", "NET", "OKTA"],
    "SRVR": ["EQIX", "DLR", "AMT", "CCI", "SBAC", "IRM"],
    "PPH": ["LLY", "JNJ", "NVO", "ABBV", "MRK", "PFE", "AZN", "NVS"],
    "XBI": ["VRTX", "GILD", "AMGN", "REGN", "MRNA", "BIIB", "INCY", "EXEL", "NTRA", "ALNY"],
    "IHI": ["ISRG", "ABT", "BSX", "SYK", "MDT", "EW", "DXCM", "BDX"],
    "KRE": ["HBAN", "RF", "CFG", "KEY", "FHN", "WAL", "ZION", "CMA"],
    "IPAY": ["V", "MA", "PYPL", "AXP", "COF", "GPN", "TOST"],
    "ITA": ["GE", "RTX", "BA", "LMT", "NOC", "GD", "HWM", "TDG"],
    "IYT": ["UBER", "UNP", "UPS", "FDX", "CSX", "NSC", "DAL", "ODFL"],
    "PAVE": ["PWR", "EMR", "URI", "ETN", "DE", "NUE", "VMC", "MLM"],
    "XOP": ["OXY", "DVN", "FANG", "EOG", "COP", "APA", "EQT"],
    "URA": ["CCJ", "NXE", "UEC", "UUUU", "LEU", "DNN"],
    "GDX": ["NEM", "AEM", "GOLD", "WPM", "FNV", "KGC", "AU", "GFI"],
    "XME": ["FCX", "NUE", "STLD", "AA", "RS", "HL", "CMC", "MP"],
    "BOTZ": ["NVDA", "ISRG", "TER", "ROK", "PATH"],
    "ICLN": ["FSLR", "ENPH", "RUN", "PLUG", "ORA", "BEP"],
    "LIT": ["ALB", "TSLA", "SQM", "ENS", "PLL", "SGML"],
    "XLK": ["NVDA", "MSFT", "AAPL", "AVGO", "ORCL", "AMD"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC"],
    "XLE": ["XOM", "CVX", "COP", "EOG", "SLB", "WMB"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "BKNG", "LOW"],
    "XLP": ["WMT", "COST", "PG", "KO", "PEP", "PM"],
    "XLI": ["GE", "RTX", "CAT", "UNP", "HON", "DE"],
    "XLB": ["LIN", "SHW", "FCX", "ECL", "APD", "NEM"],
    "XLU": ["NEE", "SO", "DUK", "CEG", "AEP", "VST"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O"],
    "XLC": ["META", "GOOGL", "NFLX", "DIS", "T", "VZ", "TMUS"],
}

TICKER_RE = re.compile(r"^[A-Z0-9.\-^]{1,10}$")

# ---------------------------------------------------------------- downloading
_cache = {}
_cache_lock = threading.Lock()


def _download(ticker, retries=3):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1=0&period2={int(time.time()) + 86400}&interval=1d&events=history")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
            df = pd.DataFrame({"Close": q["close"], "High": q["high"], "Low": q["low"],
                               "Volume": q["volume"], "Adj": adj}, index=idx)
            df = df.dropna(subset=["Close", "High", "Low"])
            df["Volume"] = df["Volume"].fillna(0)
            df["Adj"] = df["Adj"].fillna(df["Close"])
            df = df[~df.index.duplicated(keep="last")]
            meta = res.get("meta", {})
            return df, (meta.get("longName") or meta.get("shortName") or ticker)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{ticker}: {last_err}")


def get_history(ticker, force=False):
    """Cached download. Falls back to stale data if Yahoo fails. Returns (df, name) or None."""
    with _cache_lock:
        hit = _cache.get(ticker)
    if hit and not force and time.time() - hit[0] < CACHE_TTL:
        return hit[1], hit[2]
    try:
        df, name = _download(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"download failed: {e}")
        return (hit[1], hit[2]) if hit else None
    with _cache_lock:
        _cache[ticker] = (time.time(), df, name)
    return df, name


def load_many(tickers, force=False, workers=8):
    tickers = list(dict.fromkeys(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(tickers, pool.map(lambda t: get_history(t, force), tickers)))


# ---------------------------------------------------------------- indicators
def _r2(v):
    return None if v is None or pd.isna(v) else round(float(v), 2)


def _ret(close, n):
    return float((close.iloc[-1] / close.iloc[-1 - n] - 1) * 100) if len(close) > n else None


def _rsi(close, n=14):
    d = close.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    v = 100 - 100 / (1 + ag / al.replace(0, np.nan))
    last = v.iloc[-1]
    return 100.0 if pd.isna(last) else float(last)


def _atr_pct(df, n=14):
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1] / df["Close"].iloc[-1] * 100)


def _series(s):
    return [None if pd.isna(v) else round(float(v), 2) for v in s]


def compute_row(ticker, name, category, df, spy_df, with_hist=True):
    close = df["Close"]
    n = len(close)
    if n < 60:
        return None
    price, prev = float(close.iloc[-1]), float(close.iloc[-2])
    high = df["High"]
    ath = float(high.max())
    ath_adj = float((df["High"] * df["Adj"] / df["Close"]).max())
    h52_series = high.tail(252)
    h52 = float(h52_series.max())
    h52_date = h52_series.idxmax().strftime("%Y-%m-%d")

    # Prior swing high: highest peak at least 15 days before the recent high or prior peak
    before_h52 = high.loc[:h52_series.idxmax()]
    if len(before_h52) > 25:
        cutoff = h52_series.idxmax() - pd.Timedelta(days=15)
        prior_slice = high.loc[cutoff - pd.Timedelta(days=252):cutoff]
        if len(prior_slice) > 0:
            prior_high = float(prior_slice.max())
            prior_date = prior_slice.idxmax().strftime("%Y-%m-%d")
        else:
            prior_high, prior_date = h52, h52_date
    else:
        prior_high, prior_date = h52, h52_date

    row = {
        "ticker": ticker, "name": name, "category": category,
        "price": _r2(price), "dayChg": _r2((price / prev - 1) * 100),
        "ath": _r2(ath), "athDate": high.idxmax().strftime("%Y-%m-%d"),
        "distAth": _r2((price / ath - 1) * 100),
        "distAthAdj": _r2((float(df["Adj"].iloc[-1]) / ath_adj - 1) * 100),
        "high52": _r2(h52), "high52Date": h52_date,
        "dist52": _r2((price / h52 - 1) * 100),
        "priorHigh": _r2(prior_high), "priorHighDate": prior_date,
        "distPriorHigh": _r2((price / prior_high - 1) * 100),
        "rsi": _r2(_rsi(close)), "atrPct": _r2(_atr_pct(df)),
    }
    vol_avg = df["Volume"].tail(51).iloc[:-1].mean()
    row["volRatio"] = _r2(df["Volume"].iloc[-1] / vol_avg) if vol_avg > 0 else None

    s20, s50, s200 = (close.rolling(k).mean() for k in (20, 50, 200))
    row["sma20"], row["sma50"], row["sma200"] = _r2(s20.iloc[-1]), _r2(s50.iloc[-1]), _r2(s200.iloc[-1])

    # Golden / death cross within the last 30 sessions
    diff = (s50 - s200).dropna()
    row["cross"], row["trend5075"] = None, None
    if len(diff) >= 31:
        rec = diff.tail(30)
        row["trend5075"] = bool(rec.iloc[-1] > 0)
        if rec.iloc[-1] > 0 and (rec <= 0).any():
            row["cross"] = "golden"
        elif rec.iloc[-1] < 0 and (rec >= 0).any():
            row["cross"] = "death"

    # Returns + relative strength vs benchmark on several horizons
    spy_close = spy_df["Close"]
    score_num = score_den = 0.0
    for k, days in HORIZONS.items():
        r, rs = _ret(close, days), _ret(spy_close, days)
        row[f"r{k}"] = _r2(r)
        rel = r - rs if r is not None and rs is not None else None
        row[f"rel{k}"] = _r2(rel)
        if rel is not None:
            score_num += RS_WEIGHTS[k] * rel
            score_den += RS_WEIGHTS[k]
    row["_score"] = score_num / score_den if score_den else None

    # RRG: RS-Ratio (RS line vs its 63d average) and RS-Momentum (10-day change of RS-Ratio)
    row["rsRatio"] = row["rsMom"] = row["quadrant"] = None
    al = pd.concat([close, spy_close], axis=1, join="inner").dropna()
    if len(al) >= 80:
        ratio = al.iloc[:, 0] / al.iloc[:, 1]
        rsr = (100 * ratio / ratio.rolling(63).mean()).dropna()
        if len(rsr) >= 11:
            a, m = float(rsr.iloc[-1]), 100 + float(rsr.iloc[-1] - rsr.iloc[-11])
            row["rsRatio"], row["rsMom"] = _r2(a), _r2(m)
            row["quadrant"] = ("Leading" if m >= 100 else "Weakening") if a >= 100 \
                else ("Improving" if m >= 100 else "Lagging")

    if with_hist:
        tail = close.tail(HIST_DAYS)
        row["hist"] = {"d": [d.strftime("%Y-%m-%d") for d in tail.index], "c": _series(tail),
                       "s50": _series(s50.tail(HIST_DAYS)), "s200": _series(s200.tail(HIST_DAYS))}
    else:
        row["spark"] = _series(close.tail(60))
    return row


def assign_rank(rows):
    """RS Rank 1-99: percentile of the composite relative-strength score within `rows`."""
    scored = sorted((r for r in rows if r["_score"] is not None), key=lambda r: r["_score"])
    for i, r in enumerate(scored):
        r["rsRank"] = int(round(1 + 98 * i / (len(scored) - 1))) if len(scored) > 1 else 50
    for r in rows:
        r.setdefault("rsRank", None)
        r.pop("_score", None)


# ---------------------------------------------------------------- payloads
def build_payload(extra=None, force=False):
    base = {t for t, _, _ in ETFS}
    extra = [e for e in dict.fromkeys(extra or []) if TICKER_RE.match(e) and e not in base and e != BENCHMARK]
    entries = list(ETFS) + [(e, None, "Watchlist") for e in extra]
    data = load_many([t for t, _, _ in entries] + [BENCHMARK], force)
    if not data.get(BENCHMARK):
        raise RuntimeError("Could not download benchmark data (SPY)")
    spy_df = data[BENCHMARK][0]

    rows, errors = [], []
    for ticker, name, category in entries:
        got = data.get(ticker)
        row = compute_row(ticker, name or (got[1] if got else ticker), category, got[0], spy_df) if got else None
        if row:
            rows.append(row)
        else:
            errors.append(ticker)
    assign_rank(rows)

    sc = spy_df["Close"]
    return {
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lastTradingDay": sc.index[-1].strftime("%Y-%m-%d"),
        "benchmark": BENCHMARK,
        "benchmarkRet": {k: _r2(_ret(sc, d)) for k, d in HORIZONS.items()},
        "categories": [c for c in CATEGORIES if any(r["category"] == c for r in rows)],
        "etfs": rows,
        "errors": errors,
    }


def build_scanner(force=False):
    """Stocks held by the strongest ETFs (Leading quadrant or RS rank >= 70)."""
    base = build_payload(force=force)
    strong = [r["ticker"] for r in base["etfs"]
              if r["category"] != "Watchlist" and (r["quadrant"] == "Leading" or (r["rsRank"] or 0) >= 70)]
    sources = {}
    for etf in strong:
        for stock in HOLDINGS.get(etf, []):
            sources.setdefault(stock, []).append(etf)

    spy_df = get_history(BENCHMARK)[0]
    data = load_many(list(sources), force)
    rows = []
    for stock, srcs in sources.items():
        got = data.get(stock)
        row = compute_row(stock, got[1] if got else stock, "Stock", got[0], spy_df, with_hist=False) if got else None
        if row:
            row["sources"] = srcs
            rows.append(row)
    assign_rank(rows)
    return {"updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sourceEtfs": strong, "stocks": rows}


if __name__ == "__main__":
    from pathlib import Path
    out_dir = Path(__file__).parent
    print("Fetching ETF data...")
    p = build_payload(force=True)
    (out_dir / "data.json").write_text(json.dumps(p, indent=2))
    print(f"Wrote {len(p['etfs'])} ETFs to data.json")

    print("Fetching scanner stocks...")
    s = build_scanner(force=True)
    (out_dir / "scanner.json").write_text(json.dumps(s, indent=2))
    print(f"Wrote {len(s['stocks'])} stocks to scanner.json")
