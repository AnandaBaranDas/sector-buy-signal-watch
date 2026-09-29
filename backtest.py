#!/usr/bin/env python3
"""
Backtest the 60-stock watch signal rules on ~3y of history.

For each ticker: walk every trading day (from day 210 onward), evaluate the
same signal conditions as check.py (including the 2-close RECLAIM_200
confirmation rule), and measure forward returns 21 and 63 sessions out.
Entry is assumed at the signal day's close (no costs/slippage modeled).
"""
import sys
from collections import defaultdict

from check import SECTORS, fetch_daily

def rolling_sma(closes, n):
    out, s = [None] * len(closes), 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= n:
            s -= closes[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out

def wilder_rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    ag = sum(max(closes[i] - closes[i - 1], 0) for i in range(1, n + 1)) / n
    al = sum(max(closes[i - 1] - closes[i], 0) for i in range(1, n + 1)) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

def main():
    stats = defaultdict(lambda: {"n": 0, "r21": [], "r63": []})
    base21, base63 = [], []
    tickers_ok, tickers_fail = 0, []

    for sector, tickers in SECTORS.items():
        for t in tickers:
            try:
                closes = fetch_daily(t, "3y")
            except Exception as e:
                tickers_fail.append(t)
                continue
            if len(closes) < 550:
                tickers_fail.append(t + " (short)")
                continue
            tickers_ok += 1
            s50 = rolling_sma(closes, 50)
            s200 = rolling_sma(closes, 200)
            rsi = wilder_rsi(closes)
            last_cross_up = None
            # need 63 sessions of forward data; start once indicators exist
            for i in range(210, len(closes) - 63):
                c, p = closes[i], closes[i - 1]
                a50, a200, a200p, r = s50[i], s200[i], s200[i - 1], rsi[i]
                if p <= a200p and c > a200:
                    last_cross_up = i
                fwd21 = closes[i + 21] / c - 1
                fwd63 = closes[i + 63] / c - 1
                base21.append(fwd21)
                base63.append(fwd63)
                sigs = []
                if c > a200 and r < 32:
                    sigs.append("OVERSOLD_UPTREND")
                if (c > a200 and p > a200p and last_cross_up is not None
                        and i - last_cross_up <= 5):
                    sigs.append("RECLAIM_200")
                if p <= a200p and c > a200:
                    sigs.append("RECLAIM_1CLOSE_OLD")
                if abs(c - a200) / a200 < 0.02 and r < 40 and "RECLAIM_200" not in sigs:
                    sigs.append("AT_200_SUPPORT")
                dip = (a50 - c) / a50
                if 0.04 < dip < 0.12 and c > a200 and 35 < r < 55:
                    sigs.append("QUALITY_DIP")
                if p > a200p and c < a200:
                    sigs.append("BREAKDOWN")
                for s in sigs:
                    stats[s]["n"] += 1
                    stats[s]["r21"].append(fwd21)
                    stats[s]["r63"].append(fwd63)

    print(f"tickers with data: {tickers_ok}, failed/skipped: {tickers_fail}")
    print(f"baseline (any random day): n={len(base21)}, "
          f"avg +21d={mean(base21)*100:+.2f}%, avg +63d={mean(base63)*100:+.2f}%")
    print()
    print(f"{'signal':16s} {'n':>6s} {'avg+21d':>9s} {'win21':>7s} {'avg+63d':>9s} {'win63':>7s}")
    for s in ["OVERSOLD_UPTREND", "RECLAIM_200", "RECLAIM_1CLOSE_OLD",
              "AT_200_SUPPORT", "QUALITY_DIP", "BREAKDOWN"]:
        d = stats[s]
        w21 = sum(1 for x in d["r21"] if x > 0) / len(d["r21"]) if d["r21"] else 0
        w63 = sum(1 for x in d["r63"] if x > 0) / len(d["r63"]) if d["r63"] else 0
        print(f"{s:16s} {d['n']:6d} {mean(d['r21'])*100:+8.2f}% {w21:6.0%} "
              f"{mean(d['r63'])*100:+8.2f}% {w63:6.0%}")
    print()
    print("Assumptions: entry at signal-day close, no costs/slippage, overlapping")
    print("signals counted separately, ~3y history per ticker.")

if __name__ == "__main__":
    main()
