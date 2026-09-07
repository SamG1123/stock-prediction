"""Publish a transparent daily research status into the README marker block."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
UNIVERSE = ROOT / "data" / "raw" / "universe"
PREDICTIONS = ROOT / "data" / "outputs" / "current_predictions.csv"
START = "<!-- DAILY-INSIGHTS:START -->"
END = "<!-- DAILY-INSIGHTS:END -->"

def latest_universe() -> list[dict[str, str]]:
    files = sorted(UNIVERSE.glob("nifty_smallcap_250_*.csv"))
    if not files:
        return []
    with files[-1].open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def prediction_rows() -> list[dict[str, str]]:
    if not PREDICTIONS.exists():
        return []
    with PREDICTIONS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

def render() -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    universe = latest_universe()
    lines = [START, "## Daily Small-Cap Research Update", "", f"Last refreshed: **{generated}**.", ""]
    if universe:
        industries = Counter(row.get("Industry", "Unclassified") for row in universe)
        top_industries = ", ".join(f"{name} ({count})" for name, count in industries.most_common(6))
        lines += [f"- Current official NIFTY Smallcap 250 snapshot: **{len(universe)} stocks**.",
                  f"- Largest industry groups: {top_industries}.", ""]
    else:
        lines += ["- **Universe status:** waiting for the official NIFTY Smallcap 250 constituent file.", ""]
    predictions = prediction_rows()
    if predictions:
        def probability(row: dict[str, str]) -> float:
            try: return float(row.get("probability_success", ""))
            except ValueError: return -1.0
        rows = sorted(predictions, key=probability, reverse=True)[:10]
        lines += ["### Latest model research probabilities", "",
                  "Probability means the model's estimated chance of a **≥15% price return over 126 trading sessions**. It is not investment advice.", "",
                  "| Symbol | As-of date | Probability |", "| --- | --- | ---: |"]
        for row in rows:
            lines.append(f"| {row.get('symbol', '')} | {row.get('date', '')} | {probability(row):.1%} |")
    else:
        lines += ["### Prediction status", "",
                  "**No model probabilities are published yet.** The pipeline will only publish them after it has a trained model based on validated official NSE price history. This avoids presenting unverified or fabricated stock predictions."]
    lines += [END]
    return "\n".join(lines)

def main() -> None:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError("README daily-insights markers are missing")
    before, remainder = text.split(START, 1)
    _, after = remainder.split(END, 1)
    README.write_text(before + render() + after, encoding="utf-8")

if __name__ == "__main__":
    main()
