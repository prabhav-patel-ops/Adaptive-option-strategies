"""Run a reproducible, monthly NSE option hedge experiment."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import pandas as pd

from backtest import POLICIES, simulate, summarize
from fetch_nse import DataError, atomic_write, configured_feed, iso_day, read_calendar
from prepare import choose_contract, local_contracts, match_contract, normalized

IST = timezone(timedelta(hours=5, minutes=30))
SETTINGS = {
    "symbol": "NIFTY",
    "kind": "CE",
    "rate": .06,
    "expiry_buffer_days": 7,
    "capital": 2_000_000,
    "option_lots": 10,
    "futures_cost_bps": 2,
    "option_cost_bps": 10,
    "band": .15,
    "shock": .01,
}


def evaluate(sessions, contracts, settings=SETTINGS):
    by_policy = {policy: [] for policy in POLICIES}
    months = 0
    for month, dates in groupby(sessions, key=lambda day: day.strftime("%Y-%m")):
        days = list(dates)
        if len(days) < 2:
            raise DataError(f"fewer than two sessions in {month}")
        try:
            records = normalized(contracts(day, settings["symbol"]) for day in days)
            strike, expiry = choose_contract(records, days, settings["kind"], settings["expiry_buffer_days"])
            panel = match_contract(records, days, strike, expiry, settings["kind"], settings["rate"])
        except DataError as exc:
            raise DataError(f"{month}: {exc}") from None
        for policy, blocks in by_policy.items():
            blocks.append(simulate(
                panel, policy=policy, band=settings["band"], shock=settings["shock"],
                cost_bps=settings["futures_cost_bps"], option_cost_bps=settings["option_cost_bps"],
                option_lot=panel.NewBrdLotQty_option.iloc[0], futures_lot=panel.NewBrdLotQty_future.iloc[0],
                option_lots=settings["option_lots"],
            ))
        months += 1
    if not months:
        raise DataError("no completed monthly cohorts")

    comparisons = {}
    for policy, blocks in by_policy.items():
        ledger = pd.concat(blocks, ignore_index=True)
        cumulative = ledger.pnl.cumsum()
        peak = cumulative.cummax().clip(lower=0)
        # Only derived series and aggregate metrics leave this function.
        comparisons[policy] = {
            "metrics": summarize(ledger, settings["capital"]),
            "series": {
                "pnl": cumulative.round(2).tolist(),
                "cost": ledger.cost.cumsum().round(2).tolist(),
                "drawdown": (cumulative - peak).round(2).tolist(),
            },
        }
    return {
        "from": sessions[0].isoformat(),
        "through": sessions[-1].isoformat(),
        "sessions": len(sessions),
        "months": months,
        "dates": [day.isoformat() for day in sessions],
        "settings": settings,
        "strategies": comparisons,
    }


def write_json(path, payload):
    atomic_write(path, (json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n").encode())


def _window(start, end, now):
    latest_complete = now.date().replace(day=1) - timedelta(days=1)
    if end is None:
        end = latest_complete
    if start.day != 1 or (end + timedelta(days=1)).day != 1 or start > end or end > latest_complete:
        raise DataError("use complete calendar months ending before the current month in India")
    return start, end


def _check_month_coverage(sessions, start, end):
    covered = {day.strftime("%Y-%m") for day in sessions}
    expected = {str(month) for month in pd.period_range(start, end, freq="M")}
    if covered != expected:
        raise DataError("session calendar omits an entire requested month")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=iso_day)
    parser.add_argument("--end", type=iso_day)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--ci-status", type=Path, help="write a public status manifest")
    parser.add_argument("--private-output", type=Path, default=Path("data/research.json"))
    args = parser.parse_args(argv)
    if bool(args.raw_dir) != bool(args.calendar) or (args.ci_status and args.raw_dir):
        parser.error("local input needs both --raw-dir and --calendar, without --ci-status")

    now = datetime.now(IST)
    status = {
        "schema": 1,
        "checked_at": now.isoformat(timespec="seconds"),
        "commit": os.getenv("GITHUB_SHA"),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "trigger": os.getenv("GITHUB_EVENT_NAME", "local"),
        "state": "awaiting-access",
    }
    code = 0
    try:
        authorized = os.getenv("NSE_ACCESS_AUTHORIZED") == "true"
        cloud = os.getenv("NSE_CLOUD_PROCESSING_AUTHORIZED") == "true"
        if args.ci_status and not (authorized and cloud):
            write_json(args.ci_status, status)
            return 0
        start = args.start or iso_day(os.getenv("NSE_HISTORY_START") or "2025-01-01")
        start, end = _window(start, args.end, now)
        if args.raw_dir:
            sessions = read_calendar(args.calendar.read_bytes(), start, end)
            _check_month_coverage(sessions, start, end)
            results = evaluate(sessions, lambda day, symbol: local_contracts(args.raw_dir, day, symbol))
        else:
            with configured_feed() as feed:
                sessions = feed.sessions(start, end)
                _check_month_coverage(sessions, start, end)
                results = evaluate(sessions, lambda day, symbol: feed.contracts(day, symbol, args.refresh_cache))
        if args.ci_status:
            if os.getenv("NSE_PUBLISH_DERIVED") == "true":
                status.update(state="published", research=results)
            else:
                status.update(state="private")
        else:
            write_json(args.private_output, results)
            print(f"Calculated three policies for {results['months']} cohorts. Results saved locally.")
    except Exception as exc:
        if not args.ci_status:
            if isinstance(exc, (DataError, OSError)):
                parser.exit(1, f"{exc}\n")
            raise
        # Public Actions logs and status must not contain source URLs, credentials or market inputs.
        print("Research refresh failed. Reproduce locally with the authorized feed for diagnostics.")
        status.update(state="failed")
        code = 1
    if args.ci_status:
        write_json(args.ci_status, status)
    return code


def run_saved_panel():
    """Preserve the original manual prepare.py and run_research.py entry points."""
    panel = pd.read_csv("data/panel.csv")
    ledgers = {}
    for policy in POLICIES:
        sizes = [panel[col] for col in ("NewBrdLotQty_option", "NewBrdLotQty_future")]
        if any(size.nunique() != 1 for size in sizes):
            raise DataError("lot size changes inside the holding window")
        out = simulate(panel, policy=policy, option_lot=sizes[0].iloc[0], futures_lot=sizes[1].iloc[0],
                       option_lots=SETTINGS["option_lots"], cost_bps=SETTINGS["futures_cost_bps"],
                       option_cost_bps=SETTINGS["option_cost_bps"])
        out.to_csv(f"data/{policy}.csv", index=False)
        ledgers[policy] = summarize(out, SETTINGS["capital"])
    write_json("data/comparison.json", ledgers)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1 and Path("data/panel.csv").is_file():
        run_saved_panel()
    else:
        sys.exit(main())
