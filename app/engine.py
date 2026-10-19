from __future__ import annotations
from datetime import datetime, timezone
from statistics import mean
from typing import Any
import math

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def health_score(m: dict[str, Any]) -> dict[str, Any]:
    # Transparent, explainable weighted score. Each penalty is capped.
    penalties = {
        "cpu": max(0.0, float(m.get("cpu", 0)) - 60) * 0.45,
        "memory": max(0.0, float(m.get("memory", 0)) - 75) * 0.35,
        "latency": max(0.0, float(m.get("latency_ms", 0)) - 180) * 0.08,
        "error_rate": max(0.0, float(m.get("error_rate", 0)) - 1) * 3.0,
    }
    capped = {k: min(v, 35.0) for k, v in penalties.items()}
    score = max(0, min(100, round(100 - sum(capped.values()))))
    return {"score": score, "formula": "100 - capped penalties: CPU >60% (0.45/point), memory >75% (0.35/point), latency >180ms (0.08/ms), error rate >1% (3/percentage point)", "penalties": {k: round(v, 2) for k,v in capped.items()}}

def linear_forecast(values: list[float], horizon: int = 6) -> dict[str, Any]:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        vals = (vals * 2)[:2] if vals else [0.0, 0.0]
    n = len(vals)
    xs = list(range(n))
    xm, ym = mean(xs), mean(vals)
    den = sum((x-xm)**2 for x in xs)
    slope = sum((x-xm)*(y-ym) for x,y in zip(xs,vals))/den if den else 0
    intercept = ym - slope*xm
    preds = [round(max(0,min(100,intercept+slope*(n+i))),2) for i in range(horizon)]
    return {"method":"Linear trend baseline", "trend":"rising" if slope > 0.8 else "falling" if slope < -0.8 else "stable", "slope_per_5m":round(slope,3), "points":[{"step":f"+{(i+1)*5}m","cpu":p} for i,p in enumerate(preds)], "warning":"Baseline only; use held-out MAE/RMSE before making performance claims."}

def diagnose(m: dict[str, Any]) -> list[dict[str, str]]:
    cpu=float(m.get("cpu",0)); mem=float(m.get("memory",0)); lat=float(m.get("latency_ms",0))
    err=float(m.get("error_rate",0)); db=float(m.get("db_connections",0)); req=float(m.get("requests_per_min",0))
    found=[]
    if db >= 80 and lat >= 220 and err >= 2:
        found.append({"code":"DB_SATURATION","severity":"critical","title":"Likely database saturation","evidence":f"DB connections {db:.0f}%, latency {lat:.0f} ms, errors {err:.1f}%","explanation":"Rule-based correlation: high database connection pressure coincides with elevated latency and errors.","runbook":"Inspect connection pool, slow queries, lock waits and recent schema/deployment changes."})
    if cpu >= 80 and req >= 400:
        found.append({"code":"CAPACITY_PRESSURE","severity":"critical" if cpu>=90 else "high","title":"Capacity pressure during demand increase","evidence":f"CPU {cpu:.0f}%, requests/min {req:.0f}","explanation":"High CPU and request volume are occurring together; verify scaling limits and downstream saturation.","runbook":"Check request rate, autoscaling events, replica count and error budget before scaling out."})
    if lat >= 250 and db < 80:
        found.append({"code":"LATENCY_REGRESSION","severity":"high","title":"Elevated service latency","evidence":f"Latency {lat:.0f} ms; DB connections {db:.0f}%","explanation":"Latency exceeds the configured demo threshold without the DB-saturation rule being satisfied.","runbook":"Compare service spans, upstream timing, connection pool waits and recent deployments."})
    if mem >= 85:
        found.append({"code":"MEMORY_PRESSURE","severity":"high","title":"Memory pressure detected","evidence":f"Memory {mem:.0f}%","explanation":"Memory utilization is above 85%; this can precede garbage collection pressure or OOM events.","runbook":"Inspect process memory trend, worker concurrency, cache size and container/host OOM logs."})
    if err >= 3:
        found.append({"code":"ERROR_SPIKE","severity":"high","title":"Elevated error rate","evidence":f"Error rate {err:.1f}%","explanation":"Error rate exceeds 3%; correlate by endpoint and dependency before choosing a remediation.","runbook":"Inspect 4xx/5xx split, recent releases, dependency health and sampled request logs."})
    if not found:
        found.append({"code":"HEALTHY","severity":"info","title":"No threshold breach detected","evidence":"Current sample is below configured rule thresholds","explanation":"No diagnosis rule fired for this sample; this is not proof that the system is healthy.","runbook":"Continue monitoring and compare against SLOs and baseline behavior."})
    return found

def anomaly_thresholds(m: dict[str, Any]) -> list[str]:
    out=[]
    if float(m.get("cpu",0)) >= 80: out.append("CPU >= 80%")
    if float(m.get("memory",0)) >= 85: out.append("Memory >= 85%")
    if float(m.get("latency_ms",0)) >= 250: out.append("Latency >= 250ms")
    if float(m.get("error_rate",0)) >= 3: out.append("Error rate >= 3%")
    return out

def calculate_cost_review(cpu_values: list[float], hourly_price_usd: str, threshold: float = 10) -> dict[str, Any]:
    # No price is invented. An illustrative "idle-hours" opportunity is calculated only with configured price.
    if not hourly_price_usd:
        return {"price_configured":False,"hourly_price_usd":None,"estimated_monthly_cost_usd":None,"estimated_low_utilization_cost_usd":None,"recommendation":"Enter a verified hourly price for your exact instance type and region in .env; no savings estimate is shown without it.","low_cpu_threshold_percent":threshold}
    try: price=float(hourly_price_usd)
    except ValueError: price=-1
    if not math.isfinite(price) or price < 0:
        return {"price_configured":False,"hourly_price_usd":None,"estimated_monthly_cost_usd":None,"estimated_low_utilization_cost_usd":None,"recommendation":"Configured price is invalid; enter a non-negative verified hourly price.","low_cpu_threshold_percent":threshold}
    vals=[float(v) for v in cpu_values]
    low=sum(1 for v in vals if v < threshold)
    fraction=low/len(vals) if vals else 0
    monthly=price*24*30
    return {"price_configured":True,"hourly_price_usd":price,"estimated_monthly_cost_usd":round(monthly,2),"estimated_low_utilization_cost_usd":round(monthly*fraction,2),"low_cpu_samples":low,"total_samples":len(vals),"low_cpu_fraction":round(fraction,3),"recommendation":"Review stop/schedule/downsize options only after checking workload, availability, backups and ownership." if fraction >= .75 else "Insufficient sustained low-CPU evidence for an idle-resource recommendation.","low_cpu_threshold_percent":threshold}
