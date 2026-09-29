# sector-buy-signal-watch

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

A daily technical buy-signal screener for **60 large-cap stocks** — the top 10
holdings across 6 sectors. It pulls daily bars from Yahoo Finance, computes
50-day / 200-day moving averages and 14-day RSI (Wilder), and reports only
**new** signal transitions versus the previous run.

Pure Python standard library. **Zero dependencies** — if you have Python 3,
you can run it.

## Authorship & credit

This signal framework — the confirmed 2-close 200-day reclaim rule, the
quality-dip entry criteria, and the 3-year backtest methodology — was
developed by **Ananda Baran Das** (September 2026).

If you use, fork, or build on this project, **please credit the author**:

> Signal framework by Ananda Baran Das —
> https://github.com/AnandaBaranDas/sector-buy-signal-watch

For academic or written references, use the citation file
[`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository" button).

## How it works

```
Yahoo Finance daily bars → SMA-50 / SMA-200 / RSI-14 → signal engine → JSON of NEW signals
```

- **Stateful:** results are diffed against the previous run (`state.json`), so
  you only ever see *fresh* transitions — no repeated alerts.
- **Data:** adjusted daily closes via the Yahoo Finance chart API
  (`query1.finance.yahoo.com`), with automatic retry + `curl` fallback.
- **Indicators:** SMA-50, SMA-200, and RSI-14 with standard Wilder smoothing.

### The signals

| Signal | Exact rule | What it means |
|---|---|---|
| `QUALITY_DIP` | 4–12% below SMA-50, above SMA-200, RSI 35–55 | Orderly dip inside an uptrend — the scale-in zone |
| `RECLAIM_200` | **2 consecutive closes** above SMA-200, cross within last 5 sessions | Confirmed trend repair (the 2-close rule filters one-day fakeouts) |
| `AT_200_SUPPORT` | Within 2% of SMA-200 and RSI < 40 | Decision zone — watch for a hold or a break, not a buy |
| `BREAKDOWN` | Closed below SMA-200 | Trend weakening — watch for a reclaim |

Two signals were **removed after backtesting**: an oversold-bounce signal
(RSI < 32 above the 200-day) showed no edge, and breakdowns were softened from
"avoid" to "watch" because they historically recovered.

### Watched universe

| Sector | Tickers |
|---|---|
| Financials | BRK.B, JPM, V, MA, BAC, HSBC, MS, GS, WFC, AXP |
| Technology | NVDA, AAPL, MSFT, TSM, AVGO, SKHY, MU, AMD, ASML, INTC |
| Healthcare | LLY, JNJ, ABBV, MRK, UNH, NVS, AZN, TMO, AMGN, ABT |
| Consumer Discretionary | AMZN, TSLA, HD, BABA, TM, MCD, TJX, BKNG, PDD, SBUX |
| Industrials | CAT, GE, RTX, GEV, DE, ETN, UNP, BA, UBER, PH |
| Utilities | NEE, SO, CEG, DUK, NGG, AEP, SRE, D, PEG, EXC |

## Does it work? (3-year backtest)

Every signal was replayed over ~3 years of history per stock (59 stocks;
entry at signal close, no costs). Baseline = buying on a random day.

| Signal | Signals | Avg +21d | Win | Avg +63d | Win |
|---|---|---|---|---|---|
| **QUALITY_DIP** | 1,208 | **+4.15%** | 58% | **+15.72%** | 68% |
| RECLAIM_200 | 1,438 | +2.34% | 58% | +7.25% | 67% |
| AT_200_SUPPORT | 605 | +0.97% | 53% | +9.18% | 75% |
| BREAKDOWN | 515 | +2.95% | 61% | +8.67% | 69% |
| *random day* | *28,138* | *+2.34%* | *—* | *+6.70%* | *—* |

**Takeaway:** `QUALITY_DIP` clearly beats random entry on both horizons.
`RECLAIM_200` is roughly market-like. Breakdowns went *up* on average —
hence "watch," not "avoid."

### How long to hold?

Forward returns by holding period (QUALITY_DIP vs random entry):

| Hold | QUALITY_DIP | Win | Random day |
|---|---|---|---|
| 5 days | +0.38% | 56% | +0.62% |
| 21 days | +3.43% | 58% | +2.41% |
| 42 days | +9.69% | 68% | +4.73% |
| 63 days | +12.74% | 71% | +6.82% |
| 126 days | +23.53% | 83% | +14.13% |
| 252 days | +44.01% | 87% | +36.60% |

**Takeaway:** no edge under ~2 weeks; the sweet spot is **2–6 months**;
win rates keep climbing with longer holds (80%+ at 6–12 months).

> Caveats: 2023–2026 was kind to mega-cap stocks, the universe is today's
> winners (survivorship bias), and real trading has costs/slippage. Treat win
> rates as the trustworthy part, not exact percentages.

## Quick start

```bash
# 1. Build the baseline state (silent first run — no alerts)
python3 check.py --baseline

# 2. Daily check, ideally after market close — prints NEW signals as JSON
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
      "price": 336.59,
      "sma50": 352.10,
      "sma200": 319.74,
      "rsi": 36.0,
      "vs_sma200_pct": 5.3
    }
  ],
  "new_breakdowns": [],
  "errors": [],
  "notes": []
}
```

### Reproduce the research

```bash
python3 backtest.py        # signal stats vs random entry (~3y history, ~2 min)
python3 hold_analysis.py    # forward returns by holding period (5d … 252d)
```

## Files

| File | Purpose |
|---|---|
| `check.py` | Daily signal checker — the main script |
| `backtest.py` | 3-year backtest of every signal vs random entry |
| `hold_analysis.py` | Forward returns per holding period |
| `CITATION.cff` | Author citation file (GitHub "Cite this repository") |
| `LICENSE` | MIT license — copyright Ananda Baran Das |
| `state.json` | Created on first run — previous day's signals (git-ignored) |

## Automation

Run after the closing bell on weekdays (cron example, US Eastern):

```cron
21 17 * * 1-5 cd /path/to/sector-buy-signal-watch && python3 check.py
```

Alert only when `new_buy_signals` or `new_breakdowns` is non-empty;
stay silent otherwise.

## Customization

- **Your own tickers:** edit the `SECTORS` dict at the top of `check.py`.
- **Your own thresholds:** signal rules live in `signals_for()`.
- **Confirmation strictness:** the reclaim rule (`_days_since_cross_up`)
  requires 2 closes above the 200-day with the cross inside 5 sessions —
  relax or tighten to taste, then re-run `backtest.py` to check.

## Disclaimer

Educational project, **not financial advice**. Technical signals fail —
the backtest above is no guarantee of future results. Size positions
accordingly and do your own diligence.

## License

MIT — see [LICENSE](LICENSE).
