from __future__ import annotations

import argparse
from datetime import date

from .features import build_dataset
from .ingest import fetch_current_smallcap_universe, fetch_gdelt_news, ingest_collected_news, ingest_disclosures, ingest_prices
from .paths import ensure_dirs
from .train import train

def main() -> None:
    parser = argparse.ArgumentParser(description="Leakage-aware NSE stock movement research")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest-prices")
    commands.add_parser("fetch-smallcap-universe")
    news = commands.add_parser("fetch-news")
    news.add_argument("--start", type=date.fromisoformat, required=True)
    news.add_argument("--end", type=date.fromisoformat, required=True)
    commands.add_parser("ingest-disclosures")
    commands.add_parser("ingest-news")
    commands.add_parser("validate")
    fit = commands.add_parser("train")
    fit.add_argument("--cutoff", type=date.fromisoformat, required=True)
    fit.add_argument("--horizon-sessions", type=int, default=126)
    fit.add_argument("--success-threshold", type=float, default=.15)
    args = parser.parse_args()
    ensure_dirs()
    if args.command == "ingest-prices": print(f"Imported {len(ingest_prices()):,} price rows")
    elif args.command == "fetch-smallcap-universe": print(f"Fetched {len(fetch_current_smallcap_universe()):,} current Smallcap 250 constituents")
    elif args.command == "fetch-news": print(f"Fetched {len(fetch_gdelt_news(args.start, args.end)):,} news rows")
    elif args.command == "ingest-disclosures": print(f"Imported {len(ingest_disclosures()):,} disclosure rows")
    elif args.command == "ingest-news": print(f"Imported {len(ingest_collected_news()):,} news rows")
    elif args.command == "validate": print(f"Dataset rows: {len(build_dataset()):,}")
    else: print(train(args.cutoff, args.horizon_sessions, args.success_threshold))

if __name__ == "__main__": main()
