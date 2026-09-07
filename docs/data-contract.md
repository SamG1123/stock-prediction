# Small-cap data contract

The current `NIFTY Smallcap 250` file downloaded to `data/raw/universe/` is a point-in-time universe snapshot. A research run needs the following time-stamped datasets before it can be described as complete.

| Dataset | Minimum fields | Primary source | Status |
|---|---|---|---|
| Universe membership | symbol, ISIN, effective_from, effective_to | Nifty Indices constituent files and reconstitution notices | current snapshot downloaded; historical snapshots required |
| Daily market data | OHLC, volume, delivery quantity, trade date | NSE Common Bhavcopy / UDiFF | importer ready |
| Corporate events | announcement timestamp, event type, source URL, text | NSE/BSE issuer disclosures | importer ready |
| Financial statements | statement period end, filing timestamp, revenue, EBITDA, EPS, debt, cash flow | issuer results / annual reports | required before a business-quality model |
| Ownership and governance | filing timestamp, promoter holding/pledge, insider trades, auditor/resignation flags | NSE/BSE filings and SEBI disclosures | required before a business-quality model |
| News | first-seen timestamp, publisher, title, URL, language | GDELT plus a licensed India-focused archive if coverage is material | collector ready for GDELT |
| Macro / sector | observation date, release timestamp, value, revision timestamp | RBI and official ministry releases | add only when its release time is known |

## What the current label means

The model's default label is `target_return >= 15%` over 126 trading sessions. It measures a price outcome, not whether a company will literally succeed or fail. For a stronger label, supply NIFTY Smallcap 250 Total Return index history and calculate excess return after transaction costs, then combine it with a separately documented financial-distress label.

## Non-negotiable checks

1. Every raw file has its original filename, retrieval time, source URL and SHA-256 in the manifest.
2. Every event and financial input has an **availability timestamp**, not merely a reporting period/date.
3. Historical constituent membership is joined before feature construction; delisted/suspended stocks remain in the historical sample.
4. Do not use revised macro values or adjusted data that was unavailable at the historical prediction time.
5. Split training, validation and final test chronologically, with a label-horizon embargo between partitions.
