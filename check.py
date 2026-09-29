#!/usr/bin/env python3
"""
Daily sector watch: top-15 stocks x 6 sectors (90 tickers).
Pulls daily bars from Yahoo Finance, computes SMA50 / SMA200 / RSI14 (Wilder),
and emits BUY-signal / breakdown transitions vs yesterday's state.
Also tracks your open positions and fires exit alerts:
  - SELL when a holding freshly breaks below its 200-day (trend thesis broken)
  - REVIEW after 63 trading sessions (~3 months, the backtest sweet spot)

Usage:
  python3 check.py                       # run daily check, print new signals (JSON)
  python3 check.py --baseline            # (re)write state file without alerting
  python3 check.py --bought TICKER PRICE [YYYY-MM-DD]
                                         # record a buy (date defaults to today)
  python3 check.py --sold TICKER [YYYY-MM-DD]
                                         # close open position(s) in a ticker
  python3 check.py --positions            # list tracked positions
State: state.json and positions.json live beside this script.
"""
import json, os, subprocess, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state.json")
POSITIONS_PATH = os.path.join(BASE, "positions.json")
REVIEW_AFTER_SESSIONS = 63  # ~3 months of trading; backtest sweet spot is 2-6 months

SECTORS = {
    "Financials": ["BRK.B", "JPM", "V", "MA", "BAC", "HSBC", "MS", "GS", "WFC", "AXP",
                   "BLK", "SCHW", "C", "SPGI", "PGR"],
    "Technology": ["NVDA", "AAPL", "MSFT", "TSM", "AVGO", "SKHY", "MU", "AMD", "ASML", "INTC",
                   "ORCL", "CRM", "PLTR", "IBM", "ACN"],
    "Healthcare": ["LLY", "JNJ", "ABBV", "MRK", "UNH", "NVS", "AZN", "TMO", "AMGN", "ABT",
                   "ISRG", "PFE", "DHR", "GILD", "BMY"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "BABA", "TM", "MCD", "TJX", "BKNG", "PDD", "SBUX",
                               "NKE", "LOW", "GM", "MAR", "RCL"],
    "Industrials": ["CAT", "GE", "RTX", "GEV", "DE", "ETN", "UNP", "BA", "UBER", "PH",
                    "HON", "LMT", "UPS", "NOC", "WM"],
    "Utilities": ["NEE", "SO", "CEG", "DUK", "NGG", "AEP", "SRE", "D", "PEG", "EXC",
                  "ED", "XEL", "ETR", "WEC", "ES"],
}

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

def yahoo_symbol(t):
    return t.replace(".", "-")

def _get_chart(ticker, rng="2y"):
    """Raw Yahoo chart result dict, with urllib + curl fallback and retries."""
    sym = yahoo_symbol(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
    last_err = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())["chart"]["result"][0]
        except Exception as e:
            last_err = e
        try:
            p = subprocess.run(
                ["curl", "-s", "-m", "30", "-A", UA["User-Agent"], url],
                capture_output=True, text=True, timeout=45)
            return json.loads(p.stdout)["chart"]["result"][0]
        except Exception as e:
            last_err = e
        time.sleep(2)
    raise RuntimeError(f"yahoo fetch failed for {ticker}: {last_err}")

def _closes_from(res):
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    return [float(x) for x in adj if x is not None]

def fetch_daily(ticker, rng="2y"):
    """Adjusted daily closes, oldest -> newest, via Yahoo Finance chart API."""
    closes = _closes_from(_get_chart(ticker, rng))
    if len(closes) < 30:
        raise RuntimeError(f"yahoo fetch failed for {ticker}: only {len(closes)} bars")
    return closes

def fetch_bars(ticker, rng="2y"):
    """[(YYYY-MM-DD, adj_close)] oldest -> newest, via Yahoo Finance chart API."""
    res = _get_chart(ticker, rng)
    ts = res.get("timestamp") or []
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    bars = [(time.strftime("%Y-%m-%d", time.gmtime(t)), float(x))
            for t, x in zip(ts, adj) if x is not None]
    if len(bars) < 30:
        raise RuntimeError(f"yahoo fetch failed for {ticker}: only {len(bars)} bars")
    return bars

def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None

def rsi(closes, n=14):
    """Standard Wilder RSI over the full series."""
    if len(closes) < n + 1:
        return None
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    ag = sum(max(d, 0) for d in diffs[:n]) / n
    al = sum(max(-d, 0) for d in diffs[:n]) / n
    for d in diffs[n:]:
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def _days_since_cross_up(closes):
    """Sessions since the most recent close crossing from below to above the
    200-day SMA. None if no such cross in the available history."""
    for i in range(len(closes) - 1, 200, -1):
        if closes[i - 1] <= sma(closes[:i], 200) and closes[i] > sma(closes[:i + 1], 200):
            return len(closes) - 1 - i
    return None

def signals_for(ticker, closes):
    """Return (indicator snapshot, active signal names)."""
    if len(closes) < 210:
        return None, []
    c, p = closes[-1], closes[-2]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    s200_prev = sma(closes[:-1], 200)
    r = rsi(closes)
    snap = {"price": round(c, 2), "sma50": round(s50, 2), "sma200": round(s200, 2),
            "rsi": round(r, 1), "vs_sma200_pct": round(100 * (c - s200) / s200, 1)}
    sig = []
    # OVERSOLD_UPTREND removed 2026-09-29: 3y backtest showed no edge
    # (underperformed random entry on both 21d and 63d horizons).
    if p < s200_prev and c > s200:
        # First cross above: no signal yet — needs confirmation (see below).
        pass
    cross_ago = _days_since_cross_up(closes)
    if p > s200_prev and c > s200 and cross_ago is not None and cross_ago <= 5:
        # Confirmed reclaim: two consecutive closes above the 200-day, with the
        # cross inside the last 5 sessions. Kills one-day marginal fakeouts.
        sig.append("RECLAIM_200")
    if abs(c - s200) / s200 < 0.02 and r < 40 and "RECLAIM_200" not in sig:
        sig.append("AT_200_SUPPORT")
    dip = (s50 - c) / s50
    if 0.04 < dip < 0.12 and c > s200 and 35 < r < 55:
        sig.append("QUALITY_DIP")
    if p > s200_prev and c < s200:
        sig.append("BREAKDOWN")
    return snap, sig

SIGNAL_TEXT = {
    "RECLAIM_200": "reclaimed its 200-day with 2-close confirmation — downtrend may be repairing",
    "AT_200_SUPPORT": "sitting on its 200-day with weak momentum — decision zone, watch for hold or break",
    "QUALITY_DIP": "orderly 4-12% dip below 50-day inside an uptrend — scale-in zone",
    "BREAKDOWN": "slipped below its 200-day — backtest shows these often recover, so watch for a reclaim rather than avoid",
}

def load_positions():
    if os.path.exists(POSITIONS_PATH):
        try:
            return json.load(open(POSITIONS_PATH))
        except Exception:
            return []
    return []

def save_positions(lots):
    json.dump(lots, open(POSITIONS_PATH, "w"), indent=1)

def cmd_bought(args):
    """--bought TICKER PRICE [YYYY-MM-DD]: record a buy."""
    if len(args) < 2:
        print(json.dumps({"error": "usage: check.py --bought TICKER PRICE [YYYY-MM-DD]"}))
        return
    ticker = args[0].upper()
    price = float(args[1])
    date = args[2] if len(args) > 2 else time.strftime("%Y-%m-%d")
    entry_signal = None
    if os.path.exists(STATE_PATH):
        try:
            sigs = json.load(open(STATE_PATH)).get(ticker) or []
            entry_signal = sigs[0] if sigs else None
        except Exception:
            pass
    lots = load_positions()
    lots.append({"ticker": ticker, "entry_date": date, "entry_price": price,
                 "entry_signal": entry_signal, "status": "open",
                 "breakdown_alerted": False, "review_alerted": False})
    save_positions(lots)
    print(json.dumps({"recorded": lots[-1],
                      "open_positions": sum(1 for l in lots if l["status"] == "open")}))

def cmd_sold(args):
    """--sold TICKER [YYYY-MM-DD]: close open position(s) in a ticker."""
    if not args:
        print(json.dumps({"error": "usage: check.py --sold TICKER [YYYY-MM-DD]"}))
        return
    ticker = args[0].upper()
    date = args[1] if len(args) > 1 else time.strftime("%Y-%m-%d")
    lots = load_positions()
    n = 0
    for lot in lots:
        if lot["ticker"] == ticker and lot["status"] == "open":
            lot["status"] = "closed"
            lot["exit_date"] = date
            lot["exit_note"] = "manual"
            n += 1
    save_positions(lots)
    print(json.dumps({"ticker": ticker, "closed": n,
                      "open_positions": sum(1 for l in lots if l["status"] == "open")}))

def cmd_positions():
    print(json.dumps(load_positions(), indent=1))

def evaluate_positions(bars_cache):
    """SELL on fresh 200-day breakdown; REVIEW after 63 trading sessions."""
    sell_alerts, reviews = [], []
    lots = load_positions()
    if not lots:
        return sell_alerts, reviews
    for lot in lots:
        if lot.get("status") != "open":
            continue
        t = lot["ticker"]
        bars = bars_cache.get(t)
        if bars is None:
            try:
                bars = fetch_bars(t)
                bars_cache[t] = bars
            except Exception:
                continue
        if len(bars) < 210:
            continue  # not enough history to judge the 200-day trend
        dates = [d for d, _ in bars]
        closes = [c for _, c in bars]
        price = closes[-1]
        pnl = 100 * (price - lot["entry_price"]) / lot["entry_price"]
        base = {"ticker": t, "entry_date": lot["entry_date"],
                "entry_price": lot["entry_price"],
                "entry_signal": lot.get("entry_signal"),
                "price": round(price, 2), "pnl_pct": round(pnl, 1)}
        # 1) Trend-break exit: freshly closed below the 200-day
        _, sig = signals_for(t, closes)
        if ("BREAKDOWN" in sig and dates[-1] > lot["entry_date"]
                and not lot.get("breakdown_alerted")):
            sell_alerts.append({**base, "action": "SELL",
                "reason": "closed below its 200-day — the uptrend thesis is broken"})
            lot["breakdown_alerted"] = True
        # 2) Time review: 63 trading sessions after entry (~3 months)
        if not lot.get("review_alerted"):
            sessions = sum(1 for d in dates if d >= lot["entry_date"])
            if sessions >= REVIEW_AFTER_SESSIONS:
                reviews.append({**base, "action": "REVIEW",
                    "reason": (f"{sessions} trading sessions since entry — "
                               "backtest sweet spot is 2-6 months; decide hold or exit"),
                    "sessions_held": sessions})
                lot["review_alerted"] = True
    save_positions(lots)
    return sell_alerts, reviews

def main():
    if "--bought" in sys.argv:
        cmd_bought(sys.argv[sys.argv.index("--bought") + 1:])
        return
    if "--sold" in sys.argv:
        cmd_sold(sys.argv[sys.argv.index("--sold") + 1:])
        return
    if "--positions" in sys.argv:
        cmd_positions()
        return
    baseline = "--baseline" in sys.argv
    state = {}
    if os.path.exists(STATE_PATH):
        state = json.load(open(STATE_PATH))
    new_state, events = {}, []
    bars_cache = {}
    short = set(state.pop("_short_history", []))
    new_short = set()
    for sector, tickers in SECTORS.items():
        for t in tickers:
            try:
                bars = fetch_bars(t)
                bars_cache[t] = bars
                closes = [c for _, c in bars]
            except Exception as e:
                events.append({"ticker": t, "sector": sector, "error": f"data fetch failed: {e}"})
                continue
            snap, sig = signals_for(t, closes)
            if snap is None:
                new_short.add(t)
                if t not in short:
                    events.append({"ticker": t, "sector": sector,
                                   "note": f"only {len(closes)} daily bars — joins the watch once 210+ days of history exist"})
                continue
            prev = state.get(t, [])
            fresh = [s for s in sig if s not in prev]
            new_state[t] = sig
            for s in fresh:
                events.append({"ticker": t, "sector": sector, "signal": s,
                               "detail": SIGNAL_TEXT.get(s, s), **snap})
            time.sleep(0.4)
    new_state["_short_history"] = sorted(new_short)
    json.dump(new_state, open(STATE_PATH, "w"), indent=1)
    if baseline:
        print(json.dumps({"baseline_written": True,
                          "tickers": len(new_state) - 1,
                          "short_history": new_state.get("_short_history", [])}))
    else:
        buys = [e for e in events if "signal" in e and e["signal"] != "BREAKDOWN"]
        warns = [e for e in events if e.get("signal") == "BREAKDOWN"]
        errs = [e for e in events if "error" in e]
        notes = [e for e in events if "note" in e]
        sell_alerts, reviews = evaluate_positions(bars_cache)
        print(json.dumps({"new_buy_signals": buys, "new_breakdowns": warns,
                          "sell_alerts": sell_alerts, "position_reviews": reviews,
                          "open_positions": sum(1 for l in load_positions()
                                                if l.get("status") == "open"),
                          "errors": errs, "notes": notes,
                          "tickers_checked": len(new_state) - 1}, indent=1))

if __name__ == "__main__":
    main()
