from __future__ import annotations
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal
import math, secrets
from . import config, storage
from .engine import utc_now, health_score, linear_forecast, diagnose, anomaly_thresholds, calculate_cost_review
from .aws import cloudwatch_cpu, invoke_approved_lambda

app=FastAPI(title="PredictOps CloudOps",version="1.1.0",description="Predictive operations research prototype: forecast, detect, diagnose, cost review and approval.")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["GET","POST"],allow_headers=["Content-Type","Authorization"])

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Baseline browser security headers; same-origin app does not need permissive CORS."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    return response

def require_admin(request: Request, *, cloud_action: bool = False) -> None:
    """Protect administrative and cloud-changing endpoints in production/AWS mode.

    Configure ADMIN_API_TOKEN in the deployment secret store. A missing token fails
    closed for production or cloud actions rather than silently allowing mutation.
    """
    protected = config.APP_ENV == "production" or config.CLOUD_MODE == "aws" or cloud_action
    if not protected:
        return
    if not config.ADMIN_API_TOKEN:
        raise HTTPException(status_code=503, detail="Administrative operation locked: configure ADMIN_API_TOKEN in the deployment environment.")
    supplied = request.headers.get("authorization", "")
    expected = "Bearer " + config.ADMIN_API_TOKEN
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Valid administrator bearer token required.")

class ScenarioRequest(BaseModel):
    scenario: Literal["traffic_spike","db_saturation","latency_spike","error_spike"]
class ApproveRequest(BaseModel):
    recommendation_id: str = Field(min_length=1,max_length=80)
    execute_lambda: bool = False
    approval_token: str | None = Field(default=None, max_length=256)
class CostConfig(BaseModel):
    hourly_price_usd: float = Field(ge=0)
    low_cpu_threshold_percent: float = Field(default=10,ge=0,le=100)
class WhatIfRequest(BaseModel):
    traffic_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)
    additional_instances: int = Field(default=1, ge=0, le=20)
    hourly_price_usd: float | None = Field(default=None, ge=0, le=1000)
class SLOConfig(BaseModel):
    latency_target_ms: float = Field(default=200, gt=0, le=60000)
    error_target_percent: float = Field(default=1.0, ge=0, le=100)
    monthly_minutes: int = Field(default=43200, ge=1, le=44640)
class ExperimentRequest(BaseModel):
    action_a: Literal["scale_out", "cache", "reduce_concurrency"] = "scale_out"
    action_b: Literal["scale_out", "cache", "reduce_concurrency"] = "cache"
    traffic_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)
class RecoveryRequest(BaseModel):
    before_cpu: float = Field(ge=0, le=100)
    after_cpu: float = Field(ge=0, le=100)
    before_latency_ms: float = Field(ge=0)
    after_latency_ms: float = Field(ge=0)
    before_error_rate: float = Field(ge=0, le=100)
    after_error_rate: float = Field(ge=0, le=100)

def get_state(): return storage.load_state()
def latest_metrics(state): return state["metrics"][-1] if state.get("metrics") else {}
def build_overview(state):
    m=latest_metrics(state); score=health_score(m)
    return {"health_score":score["score"],"health_formula":score["formula"],"health_penalties":score["penalties"],"cpu":m.get("cpu",0),"memory":m.get("memory",0),"latency_ms":m.get("latency_ms",0),"requests_per_min":m.get("requests_per_min",0),"error_rate":m.get("error_rate",0),"db_connections":m.get("db_connections",0),"active_incidents":len([i for i in state["incidents"] if i.get("status") not in ("Resolved","Closed")]),"source":m.get("source","synthetic"),"updated_at":utc_now(),"mode":config.CLOUD_MODE}
def build_recommendations(state):
    m=latest_metrics(state); recs=[]
    if float(m.get("cpu",0))>=70 or float(m.get("requests_per_min",0))>=450:
        recs.append({"id":"SCALE-REVIEW","title":"Review horizontal scale-out","category":"Reliability","priority":"High","reason":"CPU or request volume is near the configured demo capacity threshold.","action":"Check forecast, autoscaling limits and downstream health before adding capacity.","requires_approval":True})
    else:
        recs.append({"id":"CAPACITY-WATCH","title":"Continue capacity watch","category":"Reliability","priority":"Normal","reason":"Current sample is below the demo scale-out threshold.","action":"Reassess if CPU remains elevated for multiple windows.","requires_approval":True})
    recs.append({"id":"COST-REVIEW","title":"Review sustained low-utilization compute","category":"Cost","priority":"Review","reason":"Use measured CPU samples and a verified region/instance hourly price; no price is assumed.","action":"Validate owner, schedule, availability and backups before stop/downsize/schedule changes.","requires_approval":True})
    return recs

@app.get("/",response_class=HTMLResponse)
def dashboard():
    path=Path(__file__).with_name("dashboard.html")
    if not path.exists(): raise HTTPException(status_code=500,detail="Dashboard file missing: app/dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))

@app.get("/api/health")
def health():
    state_path = storage.STATE_PATH
    writable = state_path.parent.exists() and __import__("os").access(state_path.parent, __import__("os").W_OK)
    return {"status":"healthy" if writable else "degraded", "service":"PredictOps CloudOps", "version":"1.1.0", "time":utc_now(), "checks":{"state_directory_writable":writable,"cloud_mode":config.CLOUD_MODE,"environment":config.APP_ENV}, "note":"Health is an application-process check, not proof of AWS or external dependency health."}
@app.get("/api/overview")
def overview(): return build_overview(get_state())
@app.get("/api/metrics")
def metrics(limit:int=Query(default=120,ge=1,le=2000)):
    state=get_state(); return {"items":state["metrics"][-limit:],"count":len(state["metrics"]),"source":"mixed" if any(m.get("source")=="aws-cloudwatch" for m in state["metrics"]) else "synthetic"}
@app.get("/api/forecast")
def forecast():
    state=get_state(); values=[float(m.get("cpu",0)) for m in state["metrics"]]
    base=linear_forecast(values,6)
    # If a trained Prophet artifact exists and optional package is installed, use it; fallback is explicit.
    model_path=Path(__file__).resolve().parent.parent/"artifacts"/"prophet_cpu.joblib"
    if model_path.exists():
        try:
            import joblib, pandas as pd
            model=joblib.load(model_path); future=model.make_future_dataframe(periods=6,freq="5min")
            pred=model.predict(future).tail(6)
            base["method"]="Prophet (trained artifact)"
            base["points"]=[{"step":f"+{(i+1)*5}m","cpu":round(max(0,min(100,float(v))),2)} for i,v in enumerate(pred["yhat"].tolist())]
        except Exception as e: base["artifact_warning"]=f"Prophet artifact could not be loaded; baseline used ({type(e).__name__})."
    return base
@app.get("/api/model/status")
def model_status():
    root=Path(__file__).resolve().parent.parent/"artifacts"
    try:
        import joblib, sklearn
        sklearn_ready=True
    except ImportError:
        sklearn_ready=False
    try:
        import prophet
        prophet_ready=True
    except ImportError:
        prophet_ready=False
    return {"prophet_trained":(root/"prophet_cpu.joblib").exists() and prophet_ready,"isolation_forest_trained":(root/"isolation_forest.joblib").exists() and sklearn_ready,"incident_classifier_trained":(root/"incident_classifier.joblib").exists() and sklearn_ready,"ml_dependencies_available":sklearn_ready,"prophet_dependency_available":prophet_ready,"artifact_presence":{"prophet":(root/"prophet_cpu.joblib").exists(),"isolation_forest":(root/"isolation_forest.joblib").exists(),"incident_classifier":(root/"incident_classifier.joblib").exists()},"optional_ml":"Install requirements-ml.txt to load/train optional models","baseline_available":True}
@app.get("/api/model/evaluation")
def model_evaluation():
    report=Path(__file__).resolve().parent.parent/"artifacts"/"evaluation.json"
    if not report.exists(): return {"available":False,"message":"No evaluation report yet. Generate synthetic training data and run scripts/train_models.py."}
    import json
    try: return {"available":True,"report":json.loads(report.read_text(encoding="utf-8"))}
    except (ValueError,OSError): raise HTTPException(500,"Evaluation report exists but could not be read.")
@app.get("/api/anomalies")
def anomalies():
    state=get_state(); m=latest_metrics(state); flags=anomaly_thresholds(m); ml_flag=None
    model_path=Path(__file__).resolve().parent.parent/"artifacts"/"isolation_forest.joblib"
    if model_path.exists():
        try:
            import joblib, pandas as pd
            features=("cpu","memory","latency_ms","error_rate")
            row=pd.DataFrame([{k:float(m.get(k,0)) for k in features}],columns=list(features))
            model=joblib.load(model_path)
            ml_flag=bool(model.predict(row)[0]==-1)
        except Exception: ml_flag=None
    classifier_result=None
    classifier_path=Path(__file__).resolve().parent.parent/"artifacts"/"incident_classifier.joblib"
    if classifier_path.exists():
        try:
            import joblib, pandas as pd
            features=("cpu","memory","latency_ms","error_rate")
            row=pd.DataFrame([{k:float(m.get(k,0)) for k in features}],columns=list(features))
            classifier=joblib.load(classifier_path)
            predicted=int(classifier.predict(row)[0])
            probabilities=classifier.predict_proba(row)[0].tolist()
            classifier_result={"predicted_label":"anomaly" if predicted==1 else "normal","anomaly_probability":round(float(probabilities[list(classifier.classes_).index(1)]),4),"model":"Random Forest supervised classifier","provenance":"trained on synthetic labelled examples; not production-calibrated"}
        except Exception: classifier_result=None
    return {"threshold_flags":flags,"isolation_forest_anomaly":ml_flag,"supervised_classifier":classifier_result,"method":"Isolation Forest + supervised classifier + transparent thresholds" if classifier_result is not None else "Isolation Forest + transparent thresholds" if ml_flag is not None else "Transparent threshold fallback","threshold_breaches":len(flags)}
@app.get("/api/incidents")
def incidents():
    state=get_state(); m=latest_metrics(state)
    current=[]
    for d in diagnose(m):
        if d["code"]!="HEALTHY" or not state["incidents"]:
            current.append({"id":"RULE-"+d["code"],**d,"service":"ecommerce-api","status":"Monitoring","created_at":utc_now(),"source":"rule-correlation"})
    ids={i["id"] for i in current}
    current.extend(i for i in state["incidents"] if i["id"] not in ids)
    return {"items":current[:30]}
@app.get("/api/recommendations")
def recommendations(): return {"items":build_recommendations(get_state())}
@app.get("/api/history")
def history():
    s=get_state(); return {"items":s["history"][-50:][::-1],"approvals":s["approvals"][-50:][::-1]}
@app.get("/api/cost")
def cost():
    s=get_state()
    return calculate_cost_review([float(m.get("cpu",0)) for m in s["metrics"]],config.EC2_HOURLY_PRICE_USD,config.LOW_CPU_THRESHOLD)
@app.post("/api/what-if")
def what_if(req: WhatIfRequest):
    """Deterministic capacity scenario; outputs are modeled estimates, not live AWS measurements."""
    m=latest_metrics(get_state()); cpu=float(m.get("cpu",0)); latency=float(m.get("latency_ms",0)); error=float(m.get("error_rate",0)); reqpm=float(m.get("requests_per_min",0))
    raw_cpu=min(100,cpu*req.traffic_multiplier)
    # Explicitly illustrative response model: scale-out distributes load; cache helps latency only.
    scale_factor=1+0.65*req.additional_instances
    scaled_cpu=min(100,raw_cpu/scale_factor)
    scaled_latency=max(1,latency*req.traffic_multiplier/(1+0.25*req.additional_instances))
    scaled_error=min(100,error*max(1,req.traffic_multiplier*0.8))
    monthly_cost=round(req.hourly_price_usd*req.additional_instances*24*30,2) if req.hourly_price_usd is not None else None
    return {"source":"illustrative-model","assumptions":["CPU scales linearly with traffic before capacity adjustments","each additional instance reduces modeled CPU by a factor of 1 + 0.65 per instance","latency uses a simplified load multiplier","not a performance guarantee; validate with load tests"],"baseline":{"cpu":round(cpu,2),"latency_ms":round(latency,2),"error_rate":round(error,2),"requests_per_min":round(reqpm,2)},"scenario":{"traffic_multiplier":req.traffic_multiplier,"additional_instances":req.additional_instances,"modeled_cpu":round(scaled_cpu,2),"modeled_latency_ms":round(scaled_latency,2),"modeled_error_rate":round(scaled_error,2),"monthly_incremental_cost_usd":monthly_cost},"capacity_risk":"high" if scaled_cpu>=80 or scaled_latency>=250 or scaled_error>=3 else "moderate" if scaled_cpu>=65 or scaled_latency>=200 else "lower","warning":"Simulation only. No infrastructure was changed and costs are shown only when you provide a verified hourly rate."}

@app.post("/api/slo")
def slo(req: SLOConfig):
    m=latest_metrics(get_state()); latency=float(m.get("latency_ms",0)); error=float(m.get("error_rate",0))
    # Error rate is used only as an approximate error-budget proxy; actual availability requires request counts.
    budget_fraction=max(0,min(1,(req.error_target_percent-error)/req.error_target_percent)) if req.error_target_percent>0 else (1.0 if error==0 else 0.0)
    return {"source":"latest metric sample","targets":{"latency_ms":req.latency_target_ms,"error_rate_percent":req.error_target_percent},"observed":{"latency_ms":latency,"error_rate_percent":error},"latency_slo":"breached" if latency>req.latency_target_ms else "within-target","error_rate_slo":"breached" if error>req.error_target_percent else "within-target","error_budget_remaining_proxy_percent":round(budget_fraction*100,2),"estimated_budget_minutes_remaining":round(req.monthly_minutes*budget_fraction,1),"caveat":"This is a point-in-time educational proxy, not a true availability SLI. Use request counts and a defined measurement window for production SLOs."}

@app.get("/api/copilot")
def copilot():
    s=get_state(); m=latest_metrics(s); diagnoses=[d for d in diagnose(m) if d["code"]!="HEALTHY"]
    flags=anomaly_thresholds(m); score=health_score(m)["score"]
    if diagnoses:
        lead=diagnoses[0]
        summary=f"{lead['title']} is the leading rule-based hypothesis. Evidence: {lead['evidence']}."
        next_steps=[lead["runbook"],"Compare the last known-good deployment and dependency metrics.","Capture a before-state snapshot before attempting remediation."]
    else:
        summary="No configured diagnosis rule fired for the latest sample. This does not prove that the service is healthy."
        next_steps=["Compare current metrics with the service baseline.","Review forecast and SLO indicators for emerging risk.","Keep changes reversible and preserve the current state."]
    return {"type":"evidence-grounded-rule-copilot","summary":summary,"health_score":score,"evidence":{"cpu":m.get("cpu"),"memory":m.get("memory"),"latency_ms":m.get("latency_ms"),"error_rate":m.get("error_rate"),"db_connections":m.get("db_connections"),"threshold_breaches":flags},"hypotheses":diagnoses,"recommended_next_steps":next_steps,"confidence":"rule-match only; not a calibrated probability","guardrail":"No generative model was used; all statements are grounded in current metrics and configured rules."}

@app.post("/api/experiment")
def experiment(req: ExperimentRequest):
    m=latest_metrics(get_state()); base_cpu=min(100,float(m.get("cpu",0))*req.traffic_multiplier); base_lat=float(m.get("latency_ms",0))*req.traffic_multiplier; base_err=min(100,float(m.get("error_rate",0))*max(1,req.traffic_multiplier*.8))
    def apply(action):
        cpu,lat,err=base_cpu,base_lat,base_err
        if action=="scale_out": cpu/=1.65;lat/=1.25;err=max(0,err*.9)
        elif action=="cache": lat*=.72;cpu*=.88;err=max(0,err*.95)
        elif action=="reduce_concurrency": cpu*=.78;lat*=1.2;err=min(100,err*1.15)
        risk=(max(0,cpu-70)*.8+max(0,lat-200)*.08+max(0,err-1)*4)
        return {"action":action,"modeled_cpu":round(min(100,cpu),2),"modeled_latency_ms":round(lat,2),"modeled_error_rate":round(err,2),"risk_index":round(risk,2)}
    a,b=apply(req.action_a),apply(req.action_b)
    winner=min([a,b],key=lambda x:x["risk_index"])
    return {"source":"deterministic A/B simulation","traffic_multiplier":req.traffic_multiplier,"baseline":{"cpu":round(base_cpu,2),"latency_ms":round(base_lat,2),"error_rate":round(base_err,2)},"candidate_a":a,"candidate_b":b,"preferred_candidate":winner["action"],"reason":"Lower modeled risk index across CPU, latency and error rate. This is a simulation, not a real-world experiment.","warning":"Use repeatable load tests before making a production decision."}

@app.get("/api/replay")
def replay():
    s=get_state(); events=[]
    for i in s.get("incidents",[])[:20]: events.append({"time":i.get("created_at"),"kind":"incident","title":i.get("title","Incident"),"detail":i.get("explanation",""),"status":i.get("status","Unknown")})
    for h in s.get("history",[])[:30]: events.append({"time":h.get("time"),"kind":"operation","title":h.get("event","Operation"),"detail":h.get("detail",""),"status":h.get("status","Recorded")})
    events.sort(key=lambda x:x.get("time") or "",reverse=True)
    return {"items":events[:30],"count":len(events),"note":"Replay reconstructs recorded demo events; it is not a complete distributed trace."}

@app.post("/api/recovery/verify")
def recovery_verify(req: RecoveryRequest):
    cpu_delta=round(req.before_cpu-req.after_cpu,2);lat_delta=round(req.before_latency_ms-req.after_latency_ms,2);err_delta=round(req.before_error_rate-req.after_error_rate,2)
    improved=sum(d>0 for d in (cpu_delta,lat_delta,err_delta)); regressed=sum(d<0 for d in (cpu_delta,lat_delta,err_delta))
    status="recovered" if improved>=2 and regressed==0 else "partially-recovered" if improved>regressed else "not-verified"
    result={"status":status,"changes":{"cpu_reduction_points":cpu_delta,"latency_reduction_ms":lat_delta,"error_rate_reduction_points":err_delta},"checks":{"cpu_below_80":req.after_cpu<80,"latency_below_250ms":req.after_latency_ms<250,"error_rate_below_3_percent":req.after_error_rate<3},"message":"Recovery is verified only when at least two metrics improve and none regress; otherwise treat the result as partial or unverified.","source":"operator-supplied before/after measurements"}
    s=get_state();entry={"time":utc_now(),"event":"Recovery verification","detail":f"Status: {status}; CPU {cpu_delta:+.1f} pts, latency {lat_delta:+.1f} ms, error rate {err_delta:+.2f} pts","status":status};s["history"].append(entry);storage.save_state(s);return result

@app.get("/api/dataset.csv")
def dataset():
    s=get_state(); return Response(storage.csv_bytes(s["metrics"]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=predictops_metrics.csv"})
@app.post("/api/simulate")
def simulate(req:ScenarioRequest):
    s=get_state(); m=dict(latest_metrics(s))
    multipliers={"traffic_spike":(34,12,100,280,0.8,8),"db_saturation":(12,5,170,20,2.7,48),"latency_spike":(4,2,190,5,0.5,5),"error_spike":(10,4,75,35,5.2,10)}
    dc,dm,dl,dr,de,ddb=multipliers[req.scenario]
    m.update({"timestamp":utc_now(),"cpu":min(99,round(float(m.get("cpu",0))+dc,2)),"memory":min(99,round(float(m.get("memory",0))+dm,2)),"latency_ms":round(float(m.get("latency_ms",0))+dl,2),"requests_per_min":round(float(m.get("requests_per_min",0))+dr,2),"error_rate":round(float(m.get("error_rate",0))+de,2),"db_connections":min(100,round(float(m.get("db_connections",0))+ddb,2)),"source":"synthetic-scenario"})
    s["metrics"].append(m); s["metrics"]=s["metrics"][-500:]
    ds=diagnose(m); s["scenario"]=req.scenario
    incident={"id":f"INC-{len(s['incidents'])+1:04d}","title":req.scenario.replace("_"," ").title(),"severity":"critical" if any(d["severity"]=="critical" for d in ds) else "high","service":"ecommerce-api","status":"Investigating","explanation":"Synthetic scenario applied; diagnoses are based on transparent rules.","metric":req.scenario,"created_at":utc_now(),"diagnoses":ds,"source":"synthetic"}
    s["incidents"].insert(0,incident); s["incidents"]=s["incidents"][:100]
    s["history"].append({"time":utc_now(),"event":"Scenario simulated","detail":req.scenario.replace("_"," ").title(),"status":"Demo only"})
    storage.save_state(s)
    return {"ok":True,"incident":incident,"overview":build_overview(s),"diagnoses":ds}
@app.post("/api/reset")
def reset(request: Request):
    require_admin(request)
    s=storage.fresh_state(); storage.save_state(s); return {"ok":True,"message":"Demo reset to baseline synthetic data"}
@app.post("/api/cost/configure")
def configure_cost(req:CostConfig, request: Request):
    require_admin(request)
    # Session-independent config isn't silently written to .env. Return calculated analysis for the supplied value.
    s=get_state()
    return calculate_cost_review([float(m.get("cpu",0)) for m in s["metrics"]],str(req.hourly_price_usd),req.low_cpu_threshold_percent)
@app.post("/api/metrics/import")
async def import_metrics(request: Request, file:UploadFile=File(...)):
    require_admin(request)
    if not file.filename.lower().endswith(".csv"): raise HTTPException(400,"Upload a CSV file.")
    import csv,io
    raw_bytes=await file.read(5*1024*1024+1)
    if len(raw_bytes)>5*1024*1024: raise HTTPException(413,"CSV file exceeds the 5 MB limit.")
    try: raw=raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError: raise HTTPException(400,"CSV must be UTF-8 encoded.")
    reader=csv.DictReader(io.StringIO(raw)); required={"cpu","memory","latency_ms","requests_per_min","error_rate","db_connections"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise HTTPException(400,f"CSV must include columns: {', '.join(sorted(required))}")
    rows=[]
    try:
        for row_number,row in enumerate(reader,start=2):
            if len(rows)>=5000: raise HTTPException(400,"CSV may contain at most 5,000 data rows.")
            item={k:float(row[k]) for k in required}
            if not all(math.isfinite(v) for v in item.values()): raise HTTPException(400,f"Row {row_number} contains a non-finite number.")
            for key in ("cpu","memory","error_rate","db_connections"):
                if not 0 <= item[key] <= 100: raise HTTPException(400,f"Row {row_number}: {key} must be between 0 and 100.")
            for key in ("latency_ms","requests_per_min"):
                if item[key] < 0: raise HTTPException(400,f"Row {row_number}: {key} cannot be negative.")
            item["timestamp"]=row.get("timestamp") or utc_now();item["source"]="csv-import";rows.append(item)
    except HTTPException: raise
    except (ValueError,TypeError,KeyError) as e: raise HTTPException(400,f"Invalid numeric CSV value: {e}")
    if not rows: raise HTTPException(400,"CSV contained no rows.")
    s=get_state();s["metrics"]=(s["metrics"]+rows)[-500:];s["history"].append({"time":utc_now(),"event":"CSV imported","detail":f"{len(rows)} metric rows","status":"Imported"});storage.save_state(s)
    return {"ok":True,"imported":len(rows),"total":len(s["metrics"])}
@app.post("/api/aws/sync")
def aws_sync(request: Request):
    require_admin(request, cloud_action=True)
    if config.CLOUD_MODE!="aws": raise HTTPException(400,"AWS sync is disabled. Set CLOUD_MODE=aws in .env and configure an existing instance.")
    try: rows=cloudwatch_cpu(config.AWS_EC2_INSTANCE_ID,config.AWS_REGION)
    except Exception as e: raise HTTPException(400,str(e))
    if not rows: raise HTTPException(404,"CloudWatch returned no CPU samples for this instance/time window.")
    s=get_state();s["metrics"]=(s["metrics"]+rows)[-500:];s["history"].append({"time":utc_now(),"event":"CloudWatch sync","detail":f"Imported {len(rows)} CPU samples from {config.AWS_EC2_INSTANCE_ID}","status":"Read-only"});storage.save_state(s)
    return {"ok":True,"imported":len(rows),"source":"AWS CloudWatch"}
@app.post("/api/remediation/approve")
def approve(req:ApproveRequest, request: Request):
    require_admin(request, cloud_action=req.execute_lambda)
    s=get_state(); recs=build_recommendations(s)
    rec=next((r for r in recs if r["id"]==req.recommendation_id),None)
    if not rec: raise HTTPException(404,"Recommendation not found.")
    result={"mode":"local-simulation","message":"Approval recorded only. No cloud resource was changed."}
    if req.execute_lambda:
        if config.CLOUD_MODE!="aws": raise HTTPException(400,"Lambda execution requires CLOUD_MODE=aws.")
        if not config.REMEDIATION_APPROVAL_TOKEN:
            raise HTTPException(503,"Live Lambda execution is locked: configure a strong REMEDIATION_APPROVAL_TOKEN first.")
        if not req.approval_token or not secrets.compare_digest(req.approval_token, config.REMEDIATION_APPROVAL_TOKEN):
            raise HTTPException(403,"Live Lambda execution requires a valid approval token.")
        try: result={"mode":"aws-lambda","result":invoke_approved_lambda({"recommendation_id":rec["id"],"title":rec["title"],"approved_at":utc_now(),"operator_approved":True})}
        except Exception as e: raise HTTPException(400,str(e))
    entry={"time":utc_now(),"event":"Human approval recorded","detail":rec["title"],"status":"Simulated approval" if not req.execute_lambda else "Lambda invoked","recommendation_id":rec["id"],"result":result}
    s["approvals"].append(entry);s["history"].append(entry);storage.save_state(s)
    return {"ok":True,**result,"history":entry}
