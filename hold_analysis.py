#!/usr/bin/env python3
"""Holding-period analysis: forward returns of QUALITY_DIP and RECLAIM_200
at 5, 10, 21, 42, 63, 126, 189 and 252 sessions after the signal.
Uses ~3y of history per ticker."""
import sys
from collections import defaultdict

from check import SECTORS, fetch_daily
from backtest import rolling_sma, wilder_rsi, mean

HORIZONS = [5, 10, 21, 42, 63, 126, 189, 252]
HMAX = max(HORIZONS)

def main():
    stats = {s: defaultdict(list) for s in ["QUALITY_DIP", "RECLAIM_200"]}
    base = defaultdict(list)
    n_tick = 0

    for sector, tickers in SECTORS.items():
        for t in tickers:
            try:
                closes = fetch_daily(t, "3y")
            except Exception:
                continue
            if len(closes) < 550:
                continue
            n_tick += 1
            s50 = rolling_sma(closes, 50)
            s200 = rolling_sma(closes, 200)
            rsi = wilder_rsi(closes)
            last_cross = None
            for i in range(210, len(closes) - HMAX):
                c, p = closes[i], closes[i - 1]
                a50, a200, a200p, r = s50[i], s200[i], s200[i - 1], rsi[i]
                if p <= a200p and c > a200:
                    last_cross = i
                sigs = []
                if c > a200 and p > a200p and last_cross is not None and i - last_cross <= 5:
                    sigs.append("RECLAIM_200")
                dip = (a50 - c) / a50
                if 0.04 < dip < 0.12 and c > a200 and 35 < r < 55:
                    sigs.append("QUALITY_DIP")
                rets = {h: closes[i + h] / c - 1 for h in HORIZONS}
                for h in HORIZONS:
                    base[h].append(rets[h])
                    for s in sigs:
                        stats[s][h].append(rets[h])

    print(f"tickers: {n_tick}, baseline days: {len(base[21])}")
    print()
    hdr = f"{'horizon':>8s}"
    for s in ["QUALITY_DIP", "RECLAIM_200"]:
        hdr += f" | {s:>28s}"
    hdr += f" | {'random day':>20s}"
    print(hdr)
    print("-" * len(hdr))
    for h in HORIZONS:
        row = f"{h:>4d}d   "
        for s in ["QUALITY_DIP", "RECLAIM_200"]:
            xs = stats[s][h]
            w = sum(1 for x in xs if x > 0) / len(xs)
            row += f" | n={len(xs):<4d} {mean(xs)*100:+6.2f}% win {w:.0%}"
        w = sum(1 for x in base[h] if x > 0) / len(base[h])
        row += f" | {mean(base[h])*100:+6.2f}% win {w:.0%}"
        print(row)
    print()
    print("Entry at signal-day close, no costs. ~3y history per ticker.")

if __name__ == "__main__":
    main()
