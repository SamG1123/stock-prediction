from __future__ import annotations

import json
from datetime import date, timedelta

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .features import build_dataset
from .paths import OUTPUTS, ensure_dirs

FEATURES = ["symbol", "ret_1d", "ret_5d", "vol_20d", "volume_z20", "news_count", "news_tone", "disclosure_count", "disclosure_tone"]

def train(cutoff: date, horizon_sessions: int = 126, success_threshold: float = 0.15) -> dict:
    ensure_dirs()
    complete_data = build_dataset(horizon_sessions, success_threshold)
    data = complete_data.dropna(subset=["target_success"])
    data["date"] = pd.to_datetime(data.date)
    # Embargo protects the split: training labels cannot include post-cutoff prices.
    train_data = data[data.date < pd.Timestamp(cutoff) - timedelta(days=horizon_sessions * 2)].copy()
    test_data = data[data.date >= pd.Timestamp(cutoff)].copy()
    if len(train_data) < 500 or len(test_data) < 50:
        raise ValueError("Need at least 500 pre-cutoff and 50 post-cutoff labelled observations")
    pre = ColumnTransformer([
        ("symbol", OneHotEncoder(handle_unknown="ignore"), ["symbol"]),
        ("numeric", SimpleImputer(strategy="median"), FEATURES[1:]),
    ])
    model = Pipeline([("pre", pre), ("model", HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=15, learning_rate=.05, l2_regularization=1.0, random_state=42))])
    model.fit(train_data[FEATURES], train_data.target_success.astype(int))
    probability = model.predict_proba(test_data[FEATURES])[:, 1]
    prediction = (probability >= .5).astype(int)
    metrics = {"cutoff": str(cutoff), "horizon_sessions": horizon_sessions, "success_threshold": success_threshold,
               "train_rows": len(train_data), "test_rows": len(test_data),
               "accuracy": accuracy_score(test_data.target_success, prediction),
               "balanced_accuracy": balanced_accuracy_score(test_data.target_success, prediction),
               "roc_auc": roc_auc_score(test_data.target_success, probability),
               "unconditional_success_baseline": float(test_data.target_success.mean())}
    (OUTPUTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    report = test_data[["date", "symbol", "close", "target_return", "news_count", "news_tone", "disclosure_count", "disclosure_tone"]].copy()
    report["probability_success"] = probability
    report.to_csv(OUTPUTS / "holdout_predictions.csv", index=False)
    # Score the latest row per symbol separately from the historical holdout.
    latest = complete_data.sort_values("date").groupby("symbol", as_index=False).tail(1).copy()
    latest["probability_success"] = model.predict_proba(latest[FEATURES])[:, 1]
    latest[["date", "symbol", "close", "probability_success"]].sort_values("probability_success", ascending=False).to_csv(OUTPUTS / "current_predictions.csv", index=False)
    joblib.dump(model, OUTPUTS / "model.joblib")
    return metrics
