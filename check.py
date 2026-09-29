#!/usr/bin/env python3
"""
Daily sector watch: top-10 stocks x 6 sectors.
Pulls daily bars from Yahoo Finance, computes SMA50 / SMA200 / RSI14 (Wilder),
and emits BUY-signal / breakdown transitions vs yesterday's state.

Usage:
  python3 check.py            # run daily check, print new signals (JSON)
  python3 check.py --baseline # (re)write state file without alerting
State: ~/workspace/stock-watch/state.json
"""
import json, os, subprocess, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state.json")

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

def fetch_daily(ticker, rng="2y"):
    """Adjusted daily closes, oldest -> newest, via Yahoo Finance chart API."""
    sym = yahoo_symbol(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
    last_err = None
    for attempt in range(3):
        # urllib attempt
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
            closes = _parse_chart(d)
            if len(closes) >= 30:
                return closes
            last_err = ValueError(f"only {len(closes)} bars")
        except Exception as e:
            last_err = e
        # curl fallback (handles Yahoo's flaky throttling of urllib)
        try:
            p = subprocess.run(
                ["curl", "-s", "-m", "30", "-A", UA["User-Agent"], url],
                capture_output=True, text=True, timeout=45)
            closes = _parse_chart(json.loads(p.stdout))
            if len(closes) >= 30:
                return closes
            last_err = ValueError(f"only {len(closes)} bars")
        except Exception as e:
            last_err = e
        time.sleep(2)
    raise RuntimeError(f"yahoo fetch failed for {ticker}: {last_err}")

def _parse_chart(d):
    res = d["chart"]["result"][0]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    return [float(x) for x in adj if x is not None]

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
    # OVERSOLD_UPTREND removed 2026-09-29: 2y backtest showed no edge
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

def main():
    baseline = "--baseline" in sys.argv
    state = {}
    if os.path.exists(STATE_PATH):
        state = json.load(open(STATE_PATH))
    new_state, events = {}, []
    short = set(state.pop("_short_history", []))
    new_short = set()
    for sector, tickers in SECTORS.items():
        for t in tickers:
            try:
                closes = fetch_daily(t)
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
        print(json.dumps({"new_buy_signals": buys, "new_breakdowns": warns,
                          "errors": errs, "notes": notes,
                          "tickers_checked": len(new_state) - 1}, indent=1))

if __name__ == "__main__":
    main()
