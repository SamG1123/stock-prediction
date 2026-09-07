from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import PROCESSED

POSITIVE = {"beats", "profit", "approval", "wins", "growth", "upgrade", "record", "dividend"}
NEGATIVE = {"misses", "loss", "probe", "downgrade", "fraud", "penalty", "resigns", "default"}

def _headline_score(headline: str) -> int:
    words = set(re.findall(r"[a-z]+", str(headline).lower()))
    return len(words & POSITIVE) - len(words & NEGATIVE)

def _available_session_date(timestamp: pd.Series, timezone: str) -> pd.Series:
    """Map an item after NSE close to the next calendar date.

    The later price-table join naturally discards non-trading dates; a production
    calendar can replace this mapping if weekend/holiday events are material.
    """
    local = timestamp.dt.tz_convert(timezone)
    after_close = local.dt.time > pd.Timestamp("15:30").time()
    return (local.dt.tz_localize(None).dt.normalize() + pd.to_timedelta(after_close.astype(int), unit="D"))

def build_dataset(horizon_sessions: int = 126, success_threshold: float = 0.15) -> pd.DataFrame:
    path = PROCESSED / "prices.csv"
    if not path.exists():
        raise FileNotFoundError("Run ingest-prices first")
    data = pd.read_csv(path, parse_dates=["date"]).sort_values(["symbol", "date"])
    group = data.groupby("symbol", group_keys=False)
    data["ret_1d"] = group.close.pct_change()
    data["ret_5d"] = group.close.pct_change(5)
    data["vol_20d"] = group.ret_1d.transform(lambda x: x.rolling(20, min_periods=15).std())
    data["volume_z20"] = group.volume.transform(lambda x: (x - x.rolling(20, min_periods=15).mean()) / x.rolling(20, min_periods=15).std())
    data["target_return"] = group.close.shift(-horizon_sessions) / data.close - 1
    data["target_success"] = (data.target_return >= success_threshold).astype("Int64")
    data.loc[data.target_return.isna(), "target_success"] = pd.NA
    data["target_horizon_sessions"] = horizon_sessions
    data["success_threshold"] = success_threshold
    data[["news_count", "news_tone", "disclosure_count", "disclosure_tone"]] = 0.0
    news_path = PROCESSED / "news.csv"
    if news_path.exists():
        news = pd.read_csv(news_path)
        news["seen_at_utc"] = pd.to_datetime(news.seen_at_utc, utc=True, errors="coerce")
        news["feature_date"] = _available_session_date(news.seen_at_utc, "Asia/Kolkata")
        news["tone"] = news.headline.map(_headline_score)
        summary = news.groupby(["symbol", "feature_date"]).agg(news_count=("headline", "size"), news_tone=("tone", "mean")).reset_index().rename(columns={"feature_date": "date"})
        data = data.drop(columns=["news_count", "news_tone"]).merge(summary, on=["symbol", "date"], how="left")
    disclosure_path = PROCESSED / "disclosures.csv"
    if disclosure_path.exists():
        disclosures = pd.read_csv(disclosure_path)
        announced = pd.to_datetime(disclosures.announced_at_ist, errors="coerce")
        if announced.dt.tz is None:
            announced = announced.dt.tz_localize("Asia/Kolkata")
        disclosures["feature_date"] = _available_session_date(announced.dt.tz_convert("UTC"), "Asia/Kolkata")
        disclosures["tone"] = disclosures.headline.map(_headline_score)
        summary = disclosures.groupby(["symbol", "feature_date"]).agg(disclosure_count=("headline", "size"), disclosure_tone=("tone", "mean")).reset_index().rename(columns={"feature_date": "date"})
        data = data.drop(columns=["disclosure_count", "disclosure_tone"]).merge(summary, on=["symbol", "date"], how="left")
    data[["news_count", "news_tone", "disclosure_count", "disclosure_tone"]] = data[["news_count", "news_tone", "disclosure_count", "disclosure_tone"]].fillna(0)
    data.to_csv(PROCESSED / "model_dataset.csv", index=False)
    return data
