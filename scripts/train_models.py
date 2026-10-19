"""Train/evaluate optional models with reproducible held-out tests and explicit synthetic-data provenance."""
from pathlib import Path
import hashlib, json, math, sys

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)
DATA = ROOT / "data" / "training_metrics.csv"
if not DATA.exists():
    print("Training data missing. Run: python scripts/generate_training_data.py")
    sys.exit(2)
try:
    import joblib
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
        mean_absolute_error, mean_squared_error, precision_score, recall_score)
except ImportError:
    print("Optional ML dependencies missing. Run: pip install -r requirements-ml.txt")
    sys.exit(2)

raw = DATA.read_bytes()
df = pd.read_csv(DATA)
features = ["cpu", "memory", "latency_ms", "error_rate"]
required = set(features + ["label", "timestamp"])
if not required.issubset(df.columns) or len(df) < 100:
    raise SystemExit(f"Training data must contain {sorted(required)} and at least 100 rows")
if df[features + ["label"]].isna().any().any():
    raise SystemExit("Training data contains missing model values")
if not set(df["label"].unique()).issubset({0, 1}) or df["label"].nunique() < 2:
    raise SystemExit("Label must contain both 0 (normal) and 1 (anomaly)")

# Chronological split avoids training on future rows for the anomaly benchmark.
cut = int(len(df) * .75)
train, test = df.iloc[:cut].copy(), df.iloc[cut:].copy()
# Fit unsupervised model on only rows labelled normal in the training period.
normal_train = train.loc[train.label == 0, features]
if len(normal_train) < 50:
    raise SystemExit("Not enough normal training examples")
model = IsolationForest(contamination=0.06, random_state=42, n_estimators=300)
model.fit(normal_train)
pred = (model.predict(test[features]) == -1).astype(int)
y = test.label.astype(int).to_numpy()
tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
ml_metrics = {
    "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
    "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
    "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
    "accuracy": round(float(accuracy_score(y, pred)), 4),
    "specificity": round(float(tn / (tn + fp)) if tn + fp else 0.0, 4),
    "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)},
    "train_rows": int(len(train)), "normal_train_rows": int(len(normal_train)), "test_rows": int(len(test)),
    "split": "chronological 75/25; Isolation Forest fit only on normal training rows",
}
joblib.dump(model, ART / "isolation_forest.joblib")

# Supervised classifier uses synthetic incident labels; this is a separate model and must not be described as unsupervised anomaly detection.
classifier = RandomForestClassifier(n_estimators=300, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1)
classifier.fit(train[features], train.label.astype(int))
clf_pred = classifier.predict(test[features])
ctn, cfp, cfn, ctp = confusion_matrix(y, clf_pred, labels=[0, 1]).ravel()
classifier_metrics = {
    "precision": round(float(precision_score(y, clf_pred, zero_division=0)), 4),
    "recall": round(float(recall_score(y, clf_pred, zero_division=0)), 4),
    "f1": round(float(f1_score(y, clf_pred, zero_division=0)), 4),
    "accuracy": round(float(accuracy_score(y, clf_pred)), 4),
    "confusion_matrix": {"true_negative": int(ctn), "false_positive": int(cfp), "false_negative": int(cfn), "true_positive": int(ctp)},
    "train_rows": int(len(train)), "test_rows": int(len(test)),
    "split": "chronological 75/25; supervised labels come from synthetic scenario generation",
}
joblib.dump(classifier, ART / "incident_classifier.joblib")

series = df.cpu.astype(float).to_numpy()
train_series, test_series = series[:cut], series[cut:]
last_value_pred = np.repeat(train_series[-1], len(test_series))
slope = (train_series[-1] - train_series[0]) / max(1, len(train_series) - 1)
trend_pred = np.clip([train_series[-1] + slope * (i + 1) for i in range(len(test_series))], 0, 100)
def regression_metrics(actual, forecast):
    return {"mae": round(float(mean_absolute_error(actual, forecast)), 4), "rmse": round(float(math.sqrt(mean_squared_error(actual, forecast))), 4)}
# Transparent rule baseline uses the same held-out period; compare it rather than hiding a weaker ML result.
rule_pred = ((test.cpu > 80) | (test.latency_ms > 250) | (test.error_rate > 3)).astype(int).to_numpy()
rtn, rfp, rfn, rtp = confusion_matrix(y, rule_pred, labels=[0, 1]).ravel()
rule_metrics = {
    "precision": round(float(precision_score(y, rule_pred, zero_division=0)), 4),
    "recall": round(float(recall_score(y, rule_pred, zero_division=0)), 4),
    "f1": round(float(f1_score(y, rule_pred, zero_division=0)), 4),
    "accuracy": round(float(accuracy_score(y, rule_pred)), 4),
    "confusion_matrix": {"true_negative": int(rtn), "false_positive": int(rfp), "false_negative": int(rfn), "true_positive": int(rtp)},
    "rule": "CPU > 80% OR latency > 250 ms OR error rate > 3%; thresholds fixed before holdout evaluation",
}
forecast_metrics = {
    "persistence_baseline": regression_metrics(test_series, last_value_pred),
    "linear_trend_baseline": regression_metrics(test_series, trend_pred),
    "test_rows": int(len(test_series)),
    "split": "chronological 75/25",
}
report = {
    "provenance": "SYNTHETIC generated metrics; results are not production accuracy claims",
    "dataset": {"rows": int(len(df)), "sha256": hashlib.sha256(raw).hexdigest(), "seed": 7},
    "isolation_forest": ml_metrics,
    "supervised_incident_classifier": classifier_metrics,
    "threshold_rule_baseline": rule_metrics,
    "forecast_benchmarks": forecast_metrics,
    "created_utc": pd.Timestamp.now(tz="UTC").isoformat(),
}
(ART / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

# Prophet is an optional comparison model. Use the actual timestamps; never fabricate a date range.
try:
    from prophet import Prophet
    dates = pd.to_datetime(df.timestamp, utc=True).dt.tz_localize(None)
    p_train = pd.DataFrame({"ds": dates.iloc[:cut], "y": df.cpu.iloc[:cut].astype(float)})
    prophet_model = Prophet(daily_seasonality=True, weekly_seasonality=False, yearly_seasonality=False)
    prophet_model.fit(p_train)
    future = prophet_model.make_future_dataframe(periods=len(test_series), freq="5min", include_history=False)
    forecast = prophet_model.predict(future).yhat.to_numpy()
    prophet_eval = regression_metrics(test_series, np.clip(forecast, 0, 100))
    report["forecast_benchmarks"]["prophet"] = prophet_eval
    report["forecast_benchmarks"]["prophet_test_rows"] = int(len(test_series))
    joblib.dump(prophet_model, ART / "prophet_cpu.joblib")
    (ART / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Prophet model saved and evaluated on the chronological holdout:", prophet_eval)
except ImportError:
    print("Prophet not installed; baseline benchmarks remain available.")
except Exception as exc:
    print(f"Prophet training skipped safely: {type(exc).__name__}: {str(exc)[:160]}")
