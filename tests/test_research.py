import csv
import io
import json
from datetime import date
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from fetch_nse import DataError, Feed, configured_feed, read_archive, read_calendar
from prepare import choose_contract, match_contract, normalized
from pricing import price
from run_research import evaluate, main


SESSIONS = [date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6)]
EXPIRY = date(2025, 2, 27)


def archive(day, future=100, missing_option=False):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["TradDt", "TckrSymb", "FinInstrmTp", "XpryDt", "StrkPric", "OptnTp",
                     "OpnPric", "ClsPric", "NewBrdLotQty", "TtlTradgVol"])
    writer.writerow([day, "NIFTY", "IDF", EXPIRY, "", "", future - .5, future, 25, 1000])
    if not missing_option:
        for strike in [100, 105]:
            amount = price(future, strike, (EXPIRY - day).days / 365, .06, .23)
            writer.writerow([day, "NIFTY", "IDO", EXPIRY, strike, "CE", amount, amount, 50, 1000])
    target = io.BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as zipped:
        zipped.writestr("fixture.csv", buffer.getvalue())
    return target.getvalue()


def calendar(dates=SESSIONS):
    return json.dumps({"from": "2025-01-01", "through": "2025-01-31",
                       "sessions": [day.isoformat() for day in dates]}).encode()


def test_calendar_and_archive_reject_invalid_inputs():
    assert read_calendar(calendar(), date(2025, 1, 1), date(2025, 1, 31)) == SESSIONS
    with pytest.raises(DataError, match="unique ordered"):
        read_calendar(calendar(SESSIONS * 2), SESSIONS[0], SESSIONS[-1])
    with pytest.raises(DataError, match="cover"):
        read_calendar(calendar(), date(2024, 12, 31), SESSIONS[-1])
    with pytest.raises(DataError, match="trade date"):
        read_archive(archive(SESSIONS[0]), SESSIONS[1])
    with pytest.raises(DataError, match="invalid archive"):
        read_archive(b"not ZIP data", SESSIONS[0])


def test_cache_validates_before_write_and_repairs_corruption(tmp_path, monkeypatch):
    with Feed("https://licensed.example/calendar", "https://licensed.example/{date}.zip",
              cache_dir=tmp_path) as feed:
        calls = []
        payload = archive(SESSIONS[0])

        def request(url, limit):
            calls.append(url)
            return payload

        monkeypatch.setattr(feed, "_get", request)
        assert len(feed.contracts(SESSIONS[0], "NIFTY")) == 3
        assert len(feed.contracts(SESSIONS[0], "NIFTY")) == 3
        assert len(calls) == 1
        path = next(tmp_path.rglob("*.zip"))
        path.write_bytes(b"invalid")
        assert len(feed.contracts(SESSIONS[0], "NIFTY")) == 3
        assert len(calls) == 2
        assert path.read_bytes() == payload
        with pytest.raises(DataError, match="trade date"):
            feed.contracts(SESSIONS[1], "NIFTY")
        assert len(list(tmp_path.rglob("*.zip"))) == 1


def test_selection_is_based_only_on_entry_and_missing_quotes_fail():
    checked = normalized(read_archive(archive(day, 100 if not i else 106, i == 1), day)
                         for i, day in enumerate(SESSIONS))
    strike, expiry = choose_contract(checked, SESSIONS, "CE", 7)
    assert strike == 100
    with pytest.raises(DataError, match="missing scheduled"):
        match_contract(checked, SESSIONS, strike, expiry, "CE", .06)


def test_private_local_end_to_end_and_measurement_schema(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for i, day in enumerate(SESSIONS):
        (raw / f"{day:%Y%m%d}.zip").write_bytes(archive(day, 100 + 2 * i))
    manifest = tmp_path / "calendar.json"
    manifest.write_bytes(calendar())
    result = tmp_path / "result.json"
    assert main(["--start", "2025-01-01", "--end", "2025-01-31", "--raw-dir", str(raw),
                 "--calendar", str(manifest), "--private-output", str(result)]) == 0
    raw_json = result.read_text()
    data = json.loads(raw_json)
    assert data["sessions"] == 3 and data["months"] == 1
    assert set(data["strategies"]) == {"unhedged", "daily", "adaptive"}
    assert data["strategies"]["unhedged"]["metrics"]["hedge_cost"] == 0
    assert data["strategies"]["daily"]["metrics"]["hedge_cost"] > 0
    assert "future_close" not in raw_json and "option_close" not in raw_json


def test_cloud_permission_gate_and_publication_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("NSE_ACCESS_AUTHORIZED", raising=False)
    monkeypatch.delenv("NSE_PUBLISH_DERIVED", raising=False)
    with pytest.raises(DataError, match="not configured"):
        configured_feed()
    status = tmp_path / "research.json"
    args = ["--start", "2025-01-01", "--end", "2025-01-31", "--ci-status", str(status)]
    assert main(args) == 0
    assert json.loads(status.read_bytes())["state"] == "awaiting-access"

    class FixtureFeed:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def sessions(self, *_): return SESSIONS
        def contracts(self, day, *_): return read_archive(archive(day), day)

    monkeypatch.setattr("run_research.configured_feed", FixtureFeed)
    monkeypatch.setenv("NSE_ACCESS_AUTHORIZED", "true")
    monkeypatch.setenv("NSE_CLOUD_PROCESSING_AUTHORIZED", "true")
    assert main(args) == 0
    private = json.loads(status.read_bytes())
    assert private["state"] == "private" and "research" not in private
    monkeypatch.setenv("NSE_PUBLISH_DERIVED", "true")
    assert main(args) == 0
    published = json.loads(status.read_bytes())
    assert published["state"] == "published" and published["research"]["sessions"] == 3
    monkeypatch.setattr(FixtureFeed, "contracts", lambda *args: read_archive(b"bad", SESSIONS[0]))
    assert main(args) == 1
    failed = json.loads(status.read_bytes())
    assert failed["state"] == "failed" and "research" not in failed
