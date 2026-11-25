"""Retrieve NSE F&O UDiFF archives through a configured, authorized HTTPS feed."""

import argparse
import hashlib
import io
import json
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


UDIFF_COLUMNS = {
    "TradDt", "TckrSymb", "FinInstrmTp", "XpryDt", "StrkPric", "OptnTp",
    "OpnPric", "ClsPric", "NewBrdLotQty", "TtlTradgVol",
}
MAX_ZIP_BYTES = 32 * 1024 * 1024
MAX_CSV_BYTES = 192 * 1024 * 1024


class DataError(ValueError):
    """A market-data input failed an ingestion or validation check."""


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(content)
            temp.close()
            temporary.replace(path)
        finally:
            temp.close()
            temporary.unlink(missing_ok=True)


def iso_day(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise DataError("calendar dates must use YYYY-MM-DD") from None
    if parsed.isoformat() != value:
        raise DataError("calendar dates must use YYYY-MM-DD")
    return parsed


def read_calendar(content, start, end):
    if start > end:
        raise DataError("calendar start date must precede end date")
    try:
        raw = json.loads(content)
        first, last = iso_day(raw["from"]), iso_day(raw["through"])
        if not isinstance(raw["sessions"], list):
            raise DataError("calendar sessions must be an array")
        sessions = [iso_day(value) for value in raw["sessions"]]
    except (TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        raise DataError("invalid session calendar") from None
    if first > start or last < end or first > last:
        raise DataError("session calendar does not cover the requested window")
    if not sessions or sessions != sorted(set(sessions)) or sessions[0] < first or sessions[-1] > last:
        raise DataError("session calendar must contain unique ordered in-range dates")
    selected = [day for day in sessions if start <= day <= end]
    if not selected:
        raise DataError("no scheduled sessions in requested window")
    return selected


def read_archive(content, day, symbol="NIFTY"):
    if len(content) > MAX_ZIP_BYTES:
        raise DataError("archive exceeds compressed size limit")
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if (len(entries) != 1 or not entries[0].filename.lower().endswith(".csv")
                    or entries[0].file_size > MAX_CSV_BYTES):
                raise DataError("expected one UDiFF CSV in each archive")
            with archive.open(entries[0]) as csv:
                frame = pd.read_csv(csv, usecols=lambda name: name in UDIFF_COLUMNS, low_memory=False)
    except (BadZipFile, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError,
            RuntimeError, NotImplementedError, OSError, EOFError):
        raise DataError("invalid archive or CSV") from None
    if not UDIFF_COLUMNS <= set(frame) or frame.empty:
        raise DataError("missing UDiFF columns or records")
    if not frame.TradDt.eq(day.isoformat()).all():
        raise DataError("UDiFF trade date differs from requested session")
    contracts = frame.loc[frame.TckrSymb.eq(symbol) & frame.FinInstrmTp.isin(["IDO", "IDF"])].copy()
    if contracts.empty:
        raise DataError("symbol has no index derivatives in this archive")
    return contracts


def _origin(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise DataError("the feed requires HTTPS URLs without embedded credentials or fragments")
    return parts.hostname, parts.port or 443


class Feed:
    def __init__(self, calendar_url, archive_url, token=None, cache_dir=Path("data/raw")):
        if archive_url.count("{date}") != 1:
            raise DataError("archive URL must contain one {date} placeholder for YYYYMMDD")
        if _origin(calendar_url) != _origin(archive_url.replace("{date}", "20000101")):
            raise DataError("calendar and archive URLs must use the same origin")
        self.calendar_url = calendar_url
        self.archive_url = archive_url
        namespace = hashlib.sha256((calendar_url + "\n" + archive_url).encode()).hexdigest()[:20]
        self.cache = Path(cache_dir) / namespace
        self.http = requests.Session()
        self.http.trust_env = False
        if token:
            self.http.headers["Authorization"] = f"Bearer {token}"
        retry = Retry(total=3, backoff_factor=1, allowed_methods={"GET"},
                      status_forcelist=[429, 500, 502, 503, 504])
        self.http.mount("https://", HTTPAdapter(max_retries=retry))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def _get(self, url, limit):
        try:
            with self.http.get(url, stream=True, timeout=(10, 45), allow_redirects=False) as response:
                if response.status_code == 404:
                    raise DataError("feed file missing for a scheduled date or calendar")
                if response.status_code != 200:
                    raise DataError(f"feed returned HTTP {response.status_code}")
                body = bytearray()
                for chunk in response.iter_content(64 * 1024):
                    body.extend(chunk)
                    if len(body) > limit:
                        raise DataError("feed response exceeds size limit")
                return bytes(body)
        except requests.RequestException:
            raise DataError("feed request failed after retries") from None

    def sessions(self, start, end):
        return read_calendar(self._get(self.calendar_url, 1024 * 1024), start, end)

    def contracts(self, day, symbol, refresh=False):
        path = self.cache / f"{day:%Y%m%d}.zip"
        if not refresh and path.is_file() and path.stat().st_size <= MAX_ZIP_BYTES:
            try:
                return read_archive(path.read_bytes(), day, symbol)
            except DataError:
                pass
        payload = self._get(self.archive_url.replace("{date}", day.strftime("%Y%m%d")), MAX_ZIP_BYTES)
        records = read_archive(payload, day, symbol)
        atomic_write(path, payload)
        return records


def configured_feed():
    if os.getenv("NSE_ACCESS_AUTHORIZED") != "true":
        raise DataError("authorized market-data access is not configured")
    calendar = os.getenv("NSE_CALENDAR_URL")
    template = os.getenv("NSE_ARCHIVE_URL_TEMPLATE")
    if not calendar or not template:
        raise DataError("authorized feed requires both calendar and archive URLs")
    return Feed(calendar, template, os.getenv("NSE_FEED_TOKEN"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", type=iso_day)
    parser.add_argument("end", type=iso_day)
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        with configured_feed() as feed:
            sessions = feed.sessions(args.start, args.end)
            for day in sessions:
                feed.contracts(day, args.symbol, args.refresh)
        print(f"Validated {len(sessions)} scheduled archives.")
    except DataError as exc:
        parser.exit(1, f"{exc}\n")
