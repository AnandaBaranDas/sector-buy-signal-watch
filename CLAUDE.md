# CLAUDE.md — sector-buy-signal-watch

> **Thesis in one line:** Buy orderly dips inside confirmed uptrends in
> large-cap stocks, hold 2–6 months, and never panic-sell 200-day breakdowns —
> because backtesting across 89 stocks showed dips beat random entry clearly
> (+12.9% vs +5.6% over 63 days, 67% win rate) while breakdowns *recovered*
> on average (+7.9% over 63 days).

This repo is a **daily technical buy-signal screener** plus a **position
tracker** for any universe of securities you define. Pure Python standard
library — zero dependencies. If you have Python 3, you can run it.

**Author:** the signal framework (confirmed 2-close 200-day reclaim rule,
quality-dip entry criteria, backtest methodology) was developed by
**Ananda Baran Das** (September 2026). Please credit if you use, fork, or
build on this: https://github.com/AnandaBaranDas/sector-buy-signal-watch

---

## 1. The strategy (what to implement / preserve)

### Signals — exact rules (`signals_for()` in `check.py`)

| Signal | Exact rule | Meaning |
|---|---|---|
| `QUALITY_DIP` | 4–12% below SMA-50 **and** above SMA-200 **and** RSI(14) 35–55 | **The buy setup.** Orderly dip inside an uptrend — scale-in zone |
| `RECLAIM_200` | **2 consecutive closes** above SMA-200, with the cross inside the last 5 sessions | Confirmed trend repair. The 2-close rule kills one-day fakeouts |
| `AT_200_SUPPORT` | Within 2% of SMA-200 **and** RSI < 40 | Decision zone — watch for hold-or-break, **not** a buy |
| `BREAKDOWN` | Fresh close below SMA-200 (was above yesterday) | Trend weakening — **watch for a reclaim, never auto-sell** |

Deliberately removed after backtesting:
- **Oversold bounce** (RSI < 32 above the 200-day) — no edge vs random entry.
- **"Avoid" framing on breakdowns** — softened to "watch" (see evidence below).

### Evidence (reference run: 3-year horizon, 89 stocks, entry at signal close, no costs)

| Signal | Signals | +21d | +63d (win) |
|---|---|---|---|
| **QUALITY_DIP** | 1,688 | +3.25% | **+12.92%** (67%) |
| RECLAIM_200 | 2,036 | +1.82% | +6.21% (66%) |
| AT_200_SUPPORT | 934 | +0.78% | +7.65% (70%) |
| BREAKDOWN | 738 | +2.34% | +7.87% (68%) |
| *random entry* | *42,508* | *+1.97%* | *+5.57%* |

Holding-period study: no edge under ~2 weeks; sweet spot **2–6 months**
(win rates 65–86% from 42 to 252 days).

> The 3-year window above is the reference run, **not** a fixed limit.
> The research horizon is a parameter — extend it to 5–10 years for tighter
> estimates and multiple market regimes (see §5).

**Position rules derived from this:**
- `REVIEW` alert after **63 trading sessions** (~3 months) with P&L %.
- `WATCH` warning (one-time, re-armed after a reclaim) when a holding slips
  below its 200-day — informational, **never a sell directive**.
- Caveats: the reference window favored mega-caps; the universe is today's
  winners (survivorship bias); real trading has costs/slippage. Treat win
  rates as the trustworthy part, not exact percentages.

---

## 2. Data — bring your own source

The framework is **data-source agnostic**. It needs exactly one thing per
security:

> **Daily adjusted closes as `(YYYY-MM-DD, price)` pairs, oldest → newest.**
> - Live screener: **210+ bars** (200 for the SMA + warmup).
> - Research runs: full horizon **plus 63 forward sessions** of margin
>   (the longest forward-measurement window).

The reference implementation ships with a fetch adapter for a free public
price provider (`fetch_bars()` / `fetch_daily()` in `check.py`). To use your
own source — a CSV dump, a database, a paid API, an internal warehouse —
**replace those two functions** and touch nothing else. The signal engine,
state diffing, backtester, and position tracker all consume the same
`(date, price)` contract.

```python
# the only seam you need to implement:
def fetch_bars(ticker, rng="2y"):
    """Return [(YYYY-MM-DD, adj_close)] oldest -> newest for ticker."""
    ...
```

Ticker symbols are passed through `yahoo_symbol()` (`.` → `-`) in the
reference adapter — adapt or drop that mapping for your own source.

---

## 3. Quick start

```bash
python3 check.py --baseline   # first run: writes state.json silently, no alerts
python3 check.py              # daily run: prints NEW signals as JSON
```

Run on **weekdays after market close** (signals are defined on closes):

```cron
21 17 * * 1-5 cd /path/to/sector-buy-signal-watch && python3 check.py
```

Alert only when `new_buy_signals` / `new_breakdowns` / `thesis_warnings` /
`position_reviews` is non-empty — **stay silent otherwise**.

### Position tracking

```bash
python3 check.py --bought TICKER PRICE [YYYY-MM-DD]  # record a fill (ask for the real fill price — never infer it)
python3 check.py --positions                        # list tracked lots
python3 check.py --sold TICKER [YYYY-MM-DD]          # close position(s)
```

Positions live in `positions.json` (git-ignored, never committed).

### Reproduce the research

```bash
python3 backtest.py       # every signal vs random entry (~2 min for 89 stocks at 3y)
python3 hold_analysis.py  # forward returns by holding period (5d … 252d)
```

---

## 4. How the pipeline works

```
daily price data → SMA-50 / SMA-200 / RSI-14 (Wilder)
  → signals_for() → active signal names per ticker
  → diff vs state.json → only FRESH transitions emitted as JSON
```

- **Stateful alerting:** `state.json` stores the previous run's active
  signals per ticker. A signal already active yesterday is *not* re-alerted.
- **Indicators:** SMA-50, SMA-200, and RSI-14 with standard Wilder smoothing.
- **Minimum history:** a ticker needs **210 daily bars** before it can emit
  signals. Short-history tickers are reported once in `notes` and join
  automatically once they qualify.
- **Fetch resilience (reference adapter):** 3 retries + fallback per ticker.

### Output JSON fields

| Field | Contents |
|---|---|
| `new_buy_signals` | Fresh `QUALITY_DIP` / `RECLAIM_200` / `AT_200_SUPPORT` (+ price, SMAs, RSI, % vs 200-day) |
| `new_breakdowns` | Fresh closes below the 200-day (framed "watch for a reclaim") |
| `thesis_warnings` | Open holdings that slipped below their 200-day (one-time each) |
| `position_reviews` | Holdings past 63 sessions — prompt to decide hold/exit, with P&L |
| `open_positions` | Count of open lots |
| `errors` / `notes` | Fetch failures / tickers newly joining the watch |
| `tickers_checked` | How many tickers had enough history |

---

## 5. Research at wider horizons

The reference evidence used 3 years. **Longer is better:** more signals,
tighter estimates, and coverage of multiple market regimes (the 3y window
was unusually kind to mega-caps).

To extend the horizon, in `backtest.py` and `hold_analysis.py`:

1. Change the history range in each `fetch_daily(t, "3y")` call —
   e.g. `"5y"`, `"10y"`, or `"max"` where your source supports it.
2. Raise the minimum-bars guard (`len(closes) < 550`) to roughly
   `years × 252 + 100` so thin histories are skipped instead of biasing results.
3. Optionally extend `HORIZONS` in `hold_analysis.py` (currently
   5…252 sessions) to study longer holds.

Notes:
- Every ticker needs the *full* horizon of history; tickers that listed
  recently are skipped automatically (they appear in the fail list).
- Longer horizons strengthen the survivorship-bias caveat: you are
  studying the stocks that survived the whole window.
- Re-run the backtest **after any rule change** — thresholds in
  `signals_for()` are hypotheses until the numbers confirm them.

---

## 6. Universes at scale — more sectors, more securities

The `SECTORS` dict at the top of `check.py` is just
`group name → ticker list`. Groups can be sectors, indices, factors,
market-cap tiers, or any custom basket. The group name flows through to
every alert, and the engine treats all groups identically.

```python
SECTORS = {
    "Financials": ["BRK.B", "JPM", ...],
    "Semiconductors": ["NVDA", "AVGO", ...],   # any grouping you want
    "My Watchlist": ["AAPL", "TSLA", ...],     # ...at any size
}
```

### Throughput

- The reference loop pauses **0.4 s between tickers** → ~90 tickers take
  ~2–3 min including fetch time. For hundreds or thousands of tickers this
  is the bottleneck.
- **Shard by group:** split the universe across N processes/machines, each
  writing its own `state.json`, then merge the JSON outputs. Shards are
  independent — no shared state except the final merge.
- **Cache bars:** the fetch adapter is the only network call. For backtests
  or repeated intraday runs, cache raw responses to disk keyed by
  ticker+date and skip re-fetching.
- **Backtest scale:** `backtest.py` replays the full horizon per ticker and
  parallelizes naturally by ticker. Results aggregate by signal name, so
  workers can each handle a group and you sum the counters.
- **Source etiquette:** keep request rates reasonable, keep retries bounded,
  and back off (don't retry harder) if your source returns rate-limit
  responses.

### Operating it as a service

- **Schedule:** weekdays only — the script has no weekend guard; the cron
  expression `1-5` provides it.
- **Idempotency:** re-running `check.py` twice in a day is safe — the second
  run diffs against the state the first run wrote and stays silent.
- **State hygiene:** `state.json` and `positions.json` are runtime state.
  Back them up; if `state.json` is deleted, the next run re-baselines and
  stays silent (no false alert storm).
- **Pre-close alternative:** running ~15 min before the close gives a
  trading window, but signals then rest on *intraday* prices, not the
  settled close the rules were validated on. Treat pre-close signals as
  provisional — a setup can appear or vanish in the final minutes.

### Interpreting alerts for others

- Frame everything as **setups/opportunities, never directives**.
  This is a screener, not financial advice.
- `QUALITY_DIP` is the highest-conviction signal in the backtest; the rest
  are roughly market-like or informational.
- A fresh `BREAKDOWN` is **not** a sell signal — the breakdown study
  (marginal −0.5%: +7.0%/63d; deep ≥2%: +11.6%/63d) is why exits rest on the
  63-session review, not on the breakdown itself.

---

## 7. Files

| File | Purpose |
|---|---|
| `check.py` | Daily checker + position tracker (the main script) |
| `backtest.py` | Signal backtest vs random entry (horizon = parameter) |
| `hold_analysis.py` | Forward returns by holding period |
| `state.json` | Runtime state — previous run's signals (git-ignored) |
| `positions.json` | Runtime state — tracked lots (git-ignored) |
| `CITATION.cff` | Author citation (GitHub "Cite this repository") |
| `LICENSE` | MIT — copyright Ananda Baran Das |

## Disclaimer

Educational project, **not financial advice**. Technical signals fail; the
backtest is no guarantee of future results. Size positions accordingly and
do your own diligence.
