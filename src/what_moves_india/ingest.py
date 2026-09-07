"""Raw data importers. They preserve source files and emit normalized research tables."""
from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from .paths import PROCESSED, RAW, ROOT, ensure_dirs
from .provenance import register

PRICE_ALIASES = {
    "symbol": ("SYMBOL", "TckrSymb", "SYMBOL_NAME"),
    "date": ("TIMESTAMP", "DATE1", "TradDt", "DATE"),
    "open": ("OPEN", "OpnPric"), "high": ("HIGH", "HghPric"),
    "low": ("LOW", "LwPric"), "close": ("CLOSE", "ClsPric"),
    "volume": ("TOTTRDQTY", "VOLUME", "TtlTradgVol"),
}

def _read_any_csv(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [x for x in archive.namelist() if x.lower().endswith(".csv")]
            if not names:
                raise ValueError(f"{path} has no CSV member")
            return pd.read_csv(archive.open(names[0]), low_memory=False)
    return pd.read_csv(path, low_memory=False)

def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str:
    found = next((col for col in aliases if col in frame.columns), None)
    if not found:
        raise ValueError(f"Missing one of {aliases}; got {list(frame.columns)}")
    return found

def ingest_prices() -> pd.DataFrame:
    """Normalize official user-downloaded NSE daily price files; no exchange scraping."""
    ensure_dirs()
    files = sorted((RAW / "nse_bhavcopy").glob("*"))
    files = [p for p in files if p.suffix.lower() in {".csv", ".zip"}]
    if not files:
        raise FileNotFoundError("Place official NSE Common Bhavcopy/UDiFF CSV or ZIP files in data/raw/nse_bhavcopy/")
    rows = []
    for path in files:
        frame = _read_any_csv(path)
        cols = {key: _column(frame, aliases) for key, aliases in PRICE_ALIASES.items()}
        clean = pd.DataFrame({key: frame[value] for key, value in cols.items()})
        clean["source_file"] = path.name
        register(path, "NSE Common Bhavcopy / UDiFF", "https://www.nseindia.com/all-reports")
        rows.append(clean)
    prices = pd.concat(rows, ignore_index=True)
    prices["symbol"] = prices.symbol.astype(str).str.strip().str.upper()
    prices["date"] = pd.to_datetime(prices.date, dayfirst=True, errors="coerce").dt.normalize()
    for col in ("open", "high", "low", "close", "volume"):
        prices[col] = pd.to_numeric(prices[col], errors="coerce")
    prices = prices.dropna(subset=["symbol", "date", "open", "high", "low", "close"])
    invalid = (prices[["open", "high", "low", "close"]] <= 0).any(axis=1) | (prices.high < prices.low)
    if invalid.any():
        raise ValueError(f"{invalid.sum()} invalid OHLC rows; raw inputs were not changed")
    prices = prices.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"])
    prices.to_csv(PROCESSED / "prices.csv", index=False)
    return prices

def fetch_gdelt_news(start: date, end: date, pause_seconds: float = 1.0) -> pd.DataFrame:
    """Fetch headline snapshots; GDELT's first-seen time becomes the availability time."""
    ensure_dirs()
    universe_path = PROCESSED / "universe_current.csv"
    universe = pd.read_csv(universe_path) if universe_path.exists() else pd.read_csv(ROOT / "configs" / "universe.csv")
    all_rows: list[dict] = []
    import requests
    session = requests.Session()
    session.headers["User-Agent"] = "what-moves-india-research/0.1 (contact: local-user)"
    for _, company in universe.iterrows():
        day = start
        while day <= end:
            next_day = day + timedelta(days=1)
            query = quote_plus(str(company["query"]))
            url = ("https://api.gdeltproject.org/api/v2/doc/doc?format=json&mode=artlist"
                   f"&maxrecords=250&query={query}&startdatetime={day:%Y%m%d}000000"
                   f"&enddatetime={next_day:%Y%m%d}000000")
            response = session.get(url, timeout=30)
            response.raise_for_status()
            payload = response.json()
            retrieved = datetime.now(timezone.utc).isoformat()
            for article in payload.get("articles", []):
                all_rows.append({
                    "symbol": company["symbol"], "company": company["company"], "headline": article.get("title", ""),
                    "url": article.get("url", ""), "domain": article.get("domain", ""),
                    "language": article.get("language", ""), "seen_at_utc": article.get("seendate", ""),
                    "retrieved_at_utc": retrieved, "source_name": "GDELT 2.1 DOC API", "query_url": url,
                })
            time.sleep(pause_seconds)
            day = next_day
    output = RAW / "news" / f"gdelt_{start.isoformat()}_{end.isoformat()}.json"
    output.write_text(json.dumps(all_rows, ensure_ascii=False), encoding="utf-8")
    register(output, "GDELT 2.1 DOC API", "https://api.gdeltproject.org/api/v2/doc/doc")
    news = pd.DataFrame(all_rows)
    if not news.empty:
        news.to_csv(PROCESSED / "news.csv", index=False)
    return news

def fetch_current_smallcap_universe() -> pd.DataFrame:
    """Download the official *current* NIFTY Smallcap 250 constituent file.

    This snapshot is appropriate for current screening, not for historical
    backtests. Historical membership intervals must be supplied separately.
    """
    from urllib.request import Request, urlopen
    ensure_dirs()
    url = "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv"
    target = RAW / "universe" / f"nifty_smallcap_250_{date.today().isoformat()}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "what-moves-india-research/0.1"})
    with urlopen(request, timeout=45) as response:
        target.write_bytes(response.read())
    register(target, "Nifty Indices current constituent file", url)
    source = pd.read_csv(target)
    symbol_col = _column(source, ("Symbol", "SYMBOL"))
    company_col = _column(source, ("Company Name", "Company"))
    universe = pd.DataFrame({"symbol": source[symbol_col].astype(str).str.strip().str.upper(),
                             "company": source[company_col].astype(str).str.strip()})
    # The company phrase is intentionally simple; analysts may add aliases in
    # configs/news_aliases.csv for brands, subsidiaries and common abbreviations.
    universe["query"] = universe.company
    universe.to_csv(PROCESSED / "universe_current.csv", index=False)
    return universe

def ingest_disclosures() -> pd.DataFrame:
    ensure_dirs()
    files = list((RAW / "disclosures").glob("*.csv"))
    columns = ["symbol", "announced_at_ist", "event_type", "headline", "source_url", "source_name"]
    if not files:
        return pd.DataFrame(columns=columns)
    frame = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Disclosure files lack required columns: {sorted(missing)}")
    for path in files:
        register(path, "NSE/BSE issuer disclosure export")
    announced = pd.to_datetime(frame["announced_at_ist"], errors="raise")
    # A naive export timestamp is defined by the input contract to be IST.
    if announced.dt.tz is None:
        announced = announced.dt.tz_localize("Asia/Kolkata")
    frame["announced_at_ist"] = announced
    frame["symbol"] = frame.symbol.str.upper().str.strip()
    frame.to_csv(PROCESSED / "disclosures.csv", index=False)
    return frame

def ingest_collected_news() -> pd.DataFrame:
    """Normalize JSON files written by the scheduled public-data collector."""
    ensure_dirs()
    records: list[dict] = []
    for path in (RAW / "news" / "gdelt").glob("*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for article in payload.get("articles", []):
            records.append({
                "symbol": path.parent.name, "company": "", "headline": article.get("title", ""),
                "url": article.get("url", ""), "domain": article.get("domain", ""),
                "language": article.get("language", ""), "seen_at_utc": article.get("seendate", ""),
                "retrieved_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "source_name": "GDELT 2.1 DOC API", "query_url": "",
            })
    frame = pd.DataFrame(records, columns=["symbol", "company", "headline", "url", "domain", "language", "seen_at_utc", "retrieved_at_utc", "source_name", "query_url"])
    frame.to_csv(PROCESSED / "news.csv", index=False)
    return frame
