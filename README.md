# sector-buy-signal-watch

A daily technical buy-signal screener covering **60 large-cap stocks** — the top 10
holdings across 6 sectors (Financials, Technology, Healthcare, Consumer
Discretionary, Industrials, Utilities).

It pulls daily bars from Yahoo Finance, computes 50-day / 200-day moving
averages and 14-day RSI (Wilder), and reports only **new** signal transitions
versus the previous run. No dependencies — pure Python standard library.

## Signals

| Signal | Meaning |
|---|---|
| `QUALITY_DIP` | 4–12% below the 50-day SMA, still above the 200-day, RSI 35–55 — orderly dip inside an uptrend |
| `RECLAIM_200` | **Confirmed** reclaim: 2 consecutive closes above the 200-day, cross within the last 5 sessions |
| `AT_200_SUPPORT` | Within 2% of the 200-day with weak momentum (RSI < 40) — decision zone, not a buy |
| `BREAKDOWN` | Closed below the 200-day — watch for a reclaim rather than assuming the worst |

## Quick start

```bash
# 1. Build the baseline state (no alerts on first run)
python3 check.py --baseline

# 2. Run the daily check (after market close); prints new signals as JSON
python3 check.py
```

Example output:

```json
{
  "new_buy_signals": [
    {
      "ticker": "JPM",
      "sector": "Financials",
      "signal": "QUALITY_DIP",
      "detail": "orderly 4-12% dip below 50-day inside an uptrend — scale-in zone",
      "price": 336.59, "sma50": 352.1, "sma200": 319.74,
      "rsi": 36.0, "vs_sma200_pct": 5.3
    }
  ],
  "new_breakdowns": [],
  "errors": [],
  "notes": []
}
```

## Backtest it yourself

```bash
python3 backtest.py        # signal stats vs random entry, ~3y history
python3 hold_analysis.py   # forward returns by holding period (5d … 252d)
```

Reference results (59 stocks, ~3 years, entry at signal close, no costs):

| Signal | n | avg +21d | win | avg +63d | win |
|---|---|---|---|---|---|
| QUALITY_DIP | 1208 | +4.15% | 58% | +15.72% | 68% |
| RECLAIM_200 | 1438 | +2.34% | 58% | +7.25% | 67% |
| random day | 28138 | +2.34% | — | +6.70% | — |

Holding-period sweet spot is **2–6 months**; win rates rise to 80%+ at 6–12
months. Holds under ~2 weeks show no edge. Past performance does not predict
future results — this window was kind to mega-cap stocks.

## Automate it

Run after the closing bell on weekdays (cron example, ET):

```cron
21 17 * * 1-5 cd /path/to/sector-buy-signal-watch && python3 check.py
```

Only alert when `new_buy_signals` or `new_breakdowns` is non-empty.

## Customizing

Edit the `SECTORS` dict at the top of `check.py` to watch your own tickers.
Signal thresholds live in `signals_for()`.

## Disclaimer

Educational project, not financial advice. Technical signals fail — size
positions accordingly and do your own diligence.
