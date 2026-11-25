# Research protocol

## Data access

Use an NSE or licensed provider feed whose agreement covers automated acquisition, local storage, and backtesting. Confirm separate permissions for processing on GitHub-hosted runners and public release of derived results if you need those modes. NSE's website terms prohibit automated collection and restrict simulation uses. The project has no website scraper or default archive URL. [NSE terms of use](https://www.nseindia.com/static/nse-terms-of-use) · [NSE data policy](https://www.nseindia.com/static/market-data/nse-data-policy) · [NSE historical subscriptions](https://www.nseindia.com/static/market-data/eod-historical-data-subscription) · [NSE research requests](https://www.nseindia.com/static/research/initiatives-data-for-research)

| GitHub settings | Value |
| --- | --- |
| Variable `NSE_ACCESS_AUTHORIZED` | `true` once the intended automated use and storage are authorized |
| Variable `NSE_CLOUD_PROCESSING_AUTHORIZED` | `true` once ephemeral processing on GitHub-hosted runners is authorized |
| Variable `NSE_PUBLISH_DERIVED` | `true` only if public release of the derived metrics and time series is authorized |
| Variable `NSE_HISTORY_START` | First complete calendar month to process, as `YYYY-MM-01`. Defaults to `2025-01-01`. |
| Secret `NSE_CALENDAR_URL` | Authorized HTTPS URL for the calendar JSON |
| Secret `NSE_ARCHIVE_URL_TEMPLATE` | Authorized HTTPS URL with exactly one `{date}` placeholder for `YYYYMMDD` |
| Secret `NSE_FEED_TOKEN` | Optional bearer token |

Use repository **Settings → Secrets and variables → Actions**. The calendar and archive URLs use the same HTTPS origin. Redirects and embedded credentials are rejected. The calendar must supply inclusive coverage as ISO strings in `from` and `through`, plus an ascending, unique `sessions` array of every actual F&O trading session in coverage, including special sessions. The pipeline treats a missing archive for a scheduled session as a failure. Sessions absent from the authoritative calendar are treated as closed.

Each date must provide one ZIP containing one NSE UDiFF F&O CSV. The reader checks ZIP bounds, the required columns and the reported session date. Preprocessing rejects duplicate keys, mismatched expiries, missing scheduled observations, invalid marks or IV, and in-window lot-size changes. The validated ZIP cache persists locally and is namespaced by source. Hosted runners use temporary storage for each run. They upload only the static site and its manifest. Public manifests contain status and, when authorized, derived strategy metrics, dates and series. Raw observations, credentials and private research files stay out of Git.

## Local execution

For a provisioned HTTPS feed, set the appropriate environment variables from the table and run:

```sh
python fetch_nse.py 2025-01-01 2025-01-31
python run_research.py --start 2025-01-01 --end 2025-01-31
```

For a locally licensed archive collection, name each ZIP `YYYYMMDD.zip` and provide the corresponding calendar:

```sh
python run_research.py --raw-dir data/import --calendar data/calendar.json --start 2025-01-01 --end 2025-01-31
```

The result defaults to the ignored `data/research.json`. Omit `--end` to process through the last complete calendar month in India. Use `--refresh-cache` to revalidate downloaded source revisions. For a manually specified contract, `python prepare.py --help` lists the original single-contract path and its calendar inputs. After creating a panel, running `python run_research.py` with no arguments writes individual local ledgers and a comparison.

## Experiment

- Each complete study month uses one cohort. At the first session close, select a traded NIFTY call paired with a same-expiry futures contract. Among eligible expiries at least seven calendar days beyond the final session, choose the earliest and then the closest strike to the futures close. Resolve strike ties by reported trading volume and then by lower strike. Missing quotes for the selected pair invalidate the window. Contract selection uses the entry signal session and never substitutes a more convenient contract after later observations arrive.
- Sell ten option lots at the next session's open. Daily and adaptive targets use the previous close's futures delta and execute at the next open in whole futures lots, sized using exchange lot sizes. Hold the option position and mark both legs to observed closes. Buy the option back and close any futures at the final scheduled session close. The unhedged policy trades only the same option. The signal session has zero P&L.
- Black-76 uses the same-expiry futures close as the forward proxy, ACT/365 and a flat 6% continuously compounded input. Vega is per unit of decimal volatility. The adaptive policy rebalances when absolute delta drift exceeds `b / (1 + |gamma × futures close × shock| / b)`, using `b = 0.15` and `shock = 1%`. If triggered it targets the nearest integer hedge.
- Cost assumptions are 2 basis points per futures trade on futures notional and 10 basis points per option trade on premium, each applied to every entry, rebalance or exit as applicable. These are scenario assumptions. The experiment does not model fills inside the bid/ask, queueing, actual taxes and broker fees, margin calls, financing, or market impact.
- Net P&L, transaction costs and drawdowns are in INR. Drawdown uses the running equity peak, beginning at ₹2,000,000. Sharpe uses daily net P&L on that fixed capital, a zero hurdle, sample standard deviation and 252 sessions per year. Daily 95% VaR is the smallest loss in the worst `ceil(n/20)` sessions, and expected shortfall is their average. Both use signed losses and can be negative when even the worst sessions are profitable. These are in-sample descriptive statistics, with limited tail resolution for short windows.

[Fischer Black, The pricing of commodity contracts](https://doi.org/10.1016/0304-405X(76)90024-6) · [NSE UDiFF specification notice](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/MSD59875.pdf)

## Scheduled operations

The Pages workflow runs on pushes to `main`, on demand and on day 3 of each month at 18:47 IST. Pull requests run test-only CI without feed credentials. The Pages workflow runs tests before checking the authorization flags and deploying. Use **Research and Pages → Run workflow** after changing variables or secrets. Scheduled runs process completed months, and GitHub may delay a scheduled start.

A failed refresh publishes its status without a research series and marks the run failed. If the workflow cannot deploy, the prior deployed status remains visible with its timestamp. The workflow checks the live dashboard and manifest against its own run ID and commit after deployment. [GitHub Pages publishing settings](https://github.com/prabhav-patel-ops/Adaptive-option-strategies/settings/pages)
