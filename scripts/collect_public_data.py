"""Rate-limited collector for public source files used by What Moves India.

This has no third-party Python dependencies. It never bypasses a paywall, login,
or access control: failed/blocked downloads are recorded for review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifests" / "public_collection.csv"
USER_AGENT = "what-moves-india-research/0.1 (public-data collector)"
UNIVERSE_URL = "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv"

def record(path: Path, source: str, url: str, status: str, detail: str = "") -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    header = ["retrieved_at_utc", "path", "sha256", "source", "url", "status", "detail"]
    new = not MANIFEST.exists()
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    with MANIFEST.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new: writer.writerow(header)
        writer.writerow([datetime.now(timezone.utc).isoformat(), str(path.relative_to(ROOT)), digest, source, url, status, detail])

def download(opener, url: str, path: Path, source: str, referer: str = "", retries: int = 0) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/csv,application/zip,application/json,*/*"}
    if referer: headers["Referer"] = referer
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=headers)
            with opener.open(request, timeout=45) as response:
                content = response.read()
            if len(content) < 40:
                raise ValueError("response is unexpectedly short")
            path.write_bytes(content)
            record(path, source, url, "downloaded")
            return True
        except HTTPError as error:
            if error.code == 429 and attempt < retries:
                time.sleep(min(60, 5 * (2 ** attempt)))
                continue
            record(path, source, url, "failed", str(error))
            return False
        except (URLError, TimeoutError, ValueError) as error:
            record(path, source, url, "failed", str(error))
            return False

def collect_universe(opener) -> Path:
    target = RAW / "universe" / f"nifty_smallcap_250_{date.today().isoformat()}.csv"
    download(opener, UNIVERSE_URL, target, "Nifty Indices current constituent file")
    return target

def business_days(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)

def collect_prices(opener, start: date, end: date, pause: float) -> None:
    """Try the public post-2025 PR archive naming convention once per weekday.

    NSE may change archive paths or deny automated access. Each non-download is
    recorded and should be filled from the official reports UI or licensed EOD
    delivery; no alternate data vendor is silently substituted.
    """
    for day in business_days(start, end):
        # NSE changed this filename convention in 2025. Try both documented
        # forms and retain the one actually supplied by the official archive.
        found = False
        for filename in (f"PR{day:%d%m%Y}.zip", f"PR{day:%d%m%y}.zip"):
            target = RAW / "nse_bhavcopy" / filename
            url = f"https://nsearchives.nseindia.com/content/cm/{filename}"
            if target.exists() or download(opener, url, target, "NSE Bhavcopy PR archive", "https://www.nseindia.com/all-reports"):
                found = True
                break
        if not found:
            # Failures are already recorded separately for both official URLs.
            pass
        time.sleep(pause)

def load_universe(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [(row["Symbol"].strip(), row["Company Name"].strip()) for row in rows if row.get("Symbol")]

def collect_news(opener, universe: Path, start: date, end: date, pause: float, max_symbols: int | None, offset: int) -> None:
    """Fetch GDELT per company/day, preserving the exact JSON response.

    This is deliberately granular to avoid the API's per-query record cap. It
    may take hours for a large date range; use consecutive date windows.
    """
    symbols = load_universe(universe)
    symbols = symbols[offset:]
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    for symbol, company in symbols:
        current = start
        while current <= end:
            next_day = current + timedelta(days=1)
            query = quote_plus(f'"{company}"')
            url = ("https://api.gdeltproject.org/api/v2/doc/doc?format=json&mode=artlist&maxrecords=250"
                   f"&query={query}&startdatetime={current:%Y%m%d}000000&enddatetime={next_day:%Y%m%d}000000")
            target = RAW / "news" / "gdelt" / symbol / f"{current.isoformat()}.json"
            if not target.exists():
                download(opener, url, target, "GDELT 2.1 DOC API", retries=4)
            time.sleep(pause)
            current = next_day

def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public NSE/Nifty/GDELT research inputs")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--prices", action="store_true", help="Try public NSE price archives")
    parser.add_argument("--news", action="store_true", help="Collect GDELT news (one request per symbol/day)")
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--max-symbols", type=int, help="Bound a news collection test; omit for all 250")
    parser.add_argument("--offset", type=int, default=0, help="Zero-based universe offset; use with --max-symbols for batches")
    args = parser.parse_args()
    if (args.prices or args.news) and (not args.start or not args.end):
        parser.error("--start and --end are required with --prices or --news")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    # Establish NSE cookies before archives; errors are non-fatal and logged by downloads.
    try: opener.open(Request("https://www.nseindia.com", headers={"User-Agent": USER_AGENT}), timeout=30).read(1024)
    except (HTTPError, URLError): pass
    universe = collect_universe(opener)
    if args.prices: collect_prices(opener, args.start, args.end, args.pause)
    if args.news: collect_news(opener, universe, args.start, args.end, args.pause, args.max_symbols, args.offset)

if __name__ == "__main__":
    main()
