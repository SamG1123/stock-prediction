# What Moves India

A reproducible, **research-only** pipeline for estimating whether NSE small-cap stocks meet a stated future-return outcome and for auditing what dated information was available before a prediction. It is intentionally conservative: it does not claim that a news item *caused* a return, and it does not produce trading instructions.

## Data policy

| Data | Training use | Authority / provenance |
| --- | --- | --- |
| Daily OHLCV and delivery | labels, technical features | NSE Common Bhavcopy / UDiFF raw download |
| Corporate announcements, results, actions | issuer event features | NSE/BSE disclosure export; Regulation 30 disclosures |
| News headlines | dated media features | GDELT 2.1 DOC API response, including URL/domain/first-seen time |
| Rates, FX, inflation and liquidity | macro features | RBI DBIE/downloads |

The repository refuses to train from rows with unknown sources, duplicate raw-file hashes, invalid OHLC values, or timestamps later than the prediction cut-off. Keep every download in `data/raw/` and do not replace it: reruns are traceable through `data/manifests/raw_files.csv`.

NSE's public reports page lists Common Bhavcopy / UDiFF reports. For a larger historical or intraday study, license NSE EOD/historical data rather than scraping a website. GDELT is broad media coverage, not an authoritative account of corporate facts; corporate disclosures remain the primary event record.

## Quick start

```powershell
# Use Python 3.11–3.13 (the local Python 3.14 build may not yet have binary
# wheels for the numerical stack).
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

# Download and retain today's official Smallcap 250 constituent snapshot.
what-moves-india fetch-smallcap-universe

# Put officially downloaded NSE daily files in data/raw/nse_bhavcopy/
# (CSV or ZIP; preserve the original filename.)
what-moves-india ingest-prices

# Collect a reproducible GDELT headline snapshot for the configured symbols.
what-moves-india fetch-news --start 2024-01-01 --end 2024-01-31

# Optionally add issuer disclosures exported from NSE/BSE, with the prescribed columns.
what-moves-india validate
what-moves-india train --cutoff 2025-01-01 --horizon-sessions 126 --success-threshold 0.15
```

`train` defaults to a six-month (126-session) label: **success** means a raw price return of at least 15%; otherwise it is **not successful under this definition**. This is a market-outcome label, never a claim that the business will succeed or fail. It uses a chronological pre-/post-cutoff holdout and an embargo before the cutoff. It writes metrics and per-stock/day predictions to `data/outputs/`. A result is only a backtest estimate and must not be used as investment advice.

## Public-data automation

The dependency-free collector downloads the official current universe, can try the public NSE daily archive, and can retrieve a rate-limited GDELT snapshot. It records every result (including failures) in `data/manifests/public_collection.csv`; it never works around access restrictions.

```powershell
# First prove source access over a short window.
python scripts/collect_public_data.py --start 2026-08-03 --end 2026-08-07 --prices

# News is 250 requests per day; collect it in small date windows.
python scripts/collect_public_data.py --start 2026-08-03 --end 2026-08-03 --news --pause 1.25

# A quick, bounded news-source check before a full 250-stock run.
python scripts/collect_public_data.py --start 2026-08-03 --end 2026-08-03 --news --max-symbols 5
```

NSE's public archive path and report formats can change. When a file is blocked or absent, the manifest flags it; use the official reports UI or an NSE historical-data licence to fill it rather than substituting an unverified feed.
GDELT may return HTTP 429 during a large shared-IP run; the collector backs off and retries, and preserves a failed manifest row if the service remains rate-limited.

<!-- DAILY-INSIGHTS:START -->
## Daily Small-Cap Research Update

Last refreshed: **2026-09-08 17:42 UTC**.

- Current official NIFTY Smallcap 250 snapshot: **251 stocks**.
- Largest industry groups: Financial Services (42), Capital Goods (35), Healthcare (26), Automobile and Auto Components (19), Chemicals (18), Consumer Services (17).

### Prediction status

**No model probabilities are published yet.** The pipeline will only publish them after it has a trained model based on validated official NSE price history. This avoids presenting unverified or fabricated stock predictions.
<!-- DAILY-INSIGHTS:END -->

## GitHub Actions deployment

Four workflows are ready under `.github/workflows/`: daily official-input collection, batched weekday GDELT collection, model training, and daily README publication. The README update includes a transparent current-universe summary and only publishes model probabilities after validated official price inputs have produced a trained model. In **Settings → Actions → General**, set **Workflow permissions** to **Read and write permissions** so the collectors and publisher can commit outputs. Scheduled workflows run in UTC from the default branch. Use the Actions tab to run a historical backfill in small windows. If the repository is public, create any commit or manually re-enable schedules at least once every 60 days.

## Required raw-file schemas

### NSE price files

One official CSV/ZIP per day, containing recognizable aliases for: `SYMBOL`, `TIMESTAMP`/`DATE1`, `OPEN`, `HIGH`, `LOW`, `CLOSE`, `TOTTRDQTY`/`VOLUME`. Unknown columns are retained in the raw copy. The importer normalizes aliases and validates each row.

### Disclosures (optional, `data/raw/disclosures/*.csv`)

`symbol,announced_at_ist,event_type,headline,source_url,source_name`

`announced_at_ist` must be timezone-aware or be an ISO date/time interpreted as Asia/Kolkata. A record only affects the next eligible prediction after its announcement time.

## Important research safeguards

- The default universe is the current NIFTY Smallcap 250 constituent file. A current constituent list is for current screening only: backtests require historical membership snapshots, ticker/ISIN mappings, delistings and corporate actions to avoid survivorship bias.
- Do **not** use today’s adjusted close or a later-restated fundamental value to predict an earlier date.
- Tune only on validation periods; leave the final time block untouched until selection is complete.
- Compare against an unconditional-up baseline and report accuracy, balanced accuracy, AUC, precision, recall, turnover and transaction-cost sensitivity before treating a signal as interesting.

## Sources

- [NSE all reports](https://www.nseindia.com/all-reports) (daily report availability)
- [NSE EOD / historical data](https://www.nseindia.com/static/market-data/eod-historical-data-subscription) (licensed, richer history)
- [SEBI corporate-filings directory](https://www.sebi.gov.in/curation/corporate_filings.html)
- [RBI data releases](https://statistics.rbi.org.in/)
- [GDELT 2.1 DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
