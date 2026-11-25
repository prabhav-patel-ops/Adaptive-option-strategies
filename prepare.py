"""Select and validate same-expiry option/futures panels from UDiFF sessions."""

import argparse
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from fetch_nse import DataError, MAX_ZIP_BYTES, iso_day, read_archive, read_calendar
from pricing import greeks, iv


def normalized(records):
    frame = pd.concat(records, ignore_index=True)
    frame["date"] = pd.to_datetime(frame.TradDt, format="%Y-%m-%d", errors="coerce")
    frame["expiry"] = pd.to_datetime(frame.XpryDt, format="%Y-%m-%d", errors="coerce")
    numeric = ["StrkPric", "ClsPric", "OpnPric", "NewBrdLotQty", "TtlTradgVol"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame.loc[frame.FinInstrmTp.eq("IDF"), ["StrkPric", "OptnTp"]] = [0, ""]
    if (frame[["date", "expiry"]].isna().any().any()
            or (frame.expiry < frame.date).any()
            or frame.duplicated(["date", "expiry", "FinInstrmTp", "StrkPric", "OptnTp"]).any()):
        raise DataError("invalid contract dates or duplicate contract keys")
    return frame


def _tradable(frame, fields):
    return (np.isfinite(frame[fields]).all(axis=1) & frame[fields].gt(0).all(axis=1)
            & frame.NewBrdLotQty.mod(1).eq(0))


def choose_contract(frame, sessions, kind, buffer_days):
    """Pick the closest-to-money traded strike on the first session only."""
    first = frame.loc[frame.date.eq(pd.Timestamp(sessions[0]))]
    cutoff = pd.Timestamp(sessions[-1] + timedelta(days=buffer_days))
    futures = first.loc[first.FinInstrmTp.eq("IDF") & first.expiry.ge(cutoff)].copy()
    futures = futures.loc[_tradable(futures, ["OpnPric", "ClsPric", "TtlTradgVol", "NewBrdLotQty"])]
    options = first.loc[first.FinInstrmTp.eq("IDO") & first.OptnTp.eq(kind)].copy()
    options = options.loc[_tradable(options, ["StrkPric", "OpnPric", "ClsPric", "TtlTradgVol", "NewBrdLotQty"])]
    pairs = options.merge(futures[["expiry", "ClsPric"]], on="expiry", validate="many_to_one",
                          suffixes=("_option", "_future"))
    if pairs.empty:
        raise DataError("no eligible option/future pair on the cohort entry date")
    pairs["distance"] = (pairs.StrkPric - pairs.ClsPric_future).abs()
    best = pairs.sort_values(["expiry", "distance", "TtlTradgVol", "StrkPric"],
                             ascending=[True, True, False, True]).iloc[0]
    return float(best.StrkPric), best.expiry


def match_contract(frame, sessions, strike, expiry, kind, rate):
    expiry = pd.Timestamp(expiry)
    if kind not in ("CE", "PE") or not np.isfinite(strike) or strike <= 0:
        raise DataError("invalid strike or option type")
    dated = frame.loc[frame.expiry.eq(expiry)]
    option = dated.loc[dated.FinInstrmTp.eq("IDO") & dated.StrkPric.eq(strike) & dated.OptnTp.eq(kind)]
    future = dated.loc[dated.FinInstrmTp.eq("IDF")]
    if (not _tradable(option, ["OpnPric", "ClsPric", "NewBrdLotQty", "TtlTradgVol"]).all()
            or not _tradable(future, ["OpnPric", "ClsPric", "NewBrdLotQty", "TtlTradgVol"]).all()):
        raise DataError("non-traded or invalid option or futures quote")
    panel = option[["date", "OpnPric", "ClsPric", "NewBrdLotQty"]].merge(
        future[["date", "OpnPric", "ClsPric", "NewBrdLotQty"]], on="date",
        validate="one_to_one", suffixes=("_option", "_future"),
    ).rename(columns={"ClsPric_option": "option_close", "ClsPric_future": "future_close",
                      "OpnPric_option": "option_open", "OpnPric_future": "future_open"}
             ).sort_values("date").reset_index(drop=True)
    if list(panel.date) != list(pd.to_datetime(sessions)):
        raise DataError("selected contract pair is missing scheduled quotes")
    for col in ("NewBrdLotQty_option", "NewBrdLotQty_future"):
        if panel[col].nunique() != 1:
            raise DataError("lot size changes inside the holding window")
    measures = []
    for row in panel.itertuples(index=False):
        years = (expiry - row.date).days / 365
        try:
            volatility = iv(row.option_close, row.future_close, strike, years, rate, kind)
            sensitivities = greeks(row.future_close, strike, years, rate, volatility, kind)
        except (ValueError, OverflowError):
            raise DataError("quote has no valid positive Black-76 IV and Greeks") from None
        measures.append((volatility, *sensitivities))
    panel[["iv", "delta", "gamma", "vega"]] = measures
    return panel


def local_contracts(root, day, symbol):
    path = Path(root) / f"{day:%Y%m%d}.zip"
    if not path.is_file() or path.stat().st_size > MAX_ZIP_BYTES:
        raise DataError("missing or oversized local archive for a scheduled session")
    return read_archive(path.read_bytes(), day, symbol)


def prepare(strike, expiry, kind, future_expiry, rate, *, sessions, raw_dir, symbol="NIFTY"):
    if iso_day(expiry) != iso_day(future_expiry):
        raise DataError("option and futures expiries must match")
    normalized_records = normalized(local_contracts(raw_dir, day, symbol) for day in sessions)
    return match_contract(normalized_records, sessions, strike, expiry, kind, rate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strike", type=float, required=True)
    parser.add_argument("--expiry", required=True)
    parser.add_argument("--future-expiry", required=True)
    parser.add_argument("--kind", choices=["CE", "PE"], default="CE")
    parser.add_argument("--rate", type=float, default=.06)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--start", type=iso_day, required=True)
    parser.add_argument("--end", type=iso_day, required=True)
    args = parser.parse_args()
    try:
        sessions = read_calendar(args.calendar.read_bytes(), args.start, args.end)
        panel = prepare(args.strike, args.expiry, args.kind, args.future_expiry, args.rate,
                        sessions=sessions, raw_dir=args.raw_dir, symbol=args.symbol)
        Path("data").mkdir(exist_ok=True)
        panel.to_csv("data/panel.csv", index=False)
    except (DataError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
