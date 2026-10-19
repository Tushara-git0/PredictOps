# PredictOps — Predictive Cloud Operations & Intelligent Infrastructure Management

**Project workflow:** Predict → Detect → Diagnose → Optimize Cost → Human-approved Remediation  
**Designed for:** final-year project, 10-week plan, near-$0-first development.

This is an application prototype with a real FastAPI backend and a connected interactive dashboard, not just a static mockup. It contains:
- FastAPI backend and a dashboard served from the same origin.
- Local synthetic e-commerce service metrics and traffic generator.
- Forecasting interface with a transparent linear baseline; optional Prophet training script.
- Isolation Forest anomaly detector plus an optional supervised Random Forest incident classifier when scikit-learn is installed; deterministic threshold fallback.
- Transparent health-score formula, rule-based root-cause correlation, incident timeline and audit history.
- Cost analyzer that calculates waste only from supplied hourly price and measured utilization; it never invents a price.
- Human-approval workflow. Local mode records approval only; it never changes infrastructure.
- Optional AWS CloudWatch metric import and optional Lambda invocation behind an explicit environment flag.
- Interactive cloud digital-twin topology with an optional Three.js WebGL layer and fallback topology.
- Capacity what-if simulator for traffic multipliers, extra instances and optional user-supplied price assumptions.
- Explainable incident copilot grounded in current metrics and transparent diagnosis rules (no fabricated AI claims).
- SLO target checks and an explicitly labelled educational error-budget proxy.
- A/B remediation experiment comparing scale-out, cache and concurrency choices using a deterministic illustrative model.
- Recovery verification from operator-entered before/after metrics, plus a replay timeline for recorded incidents and operations.
- Unit tests, sample data, configuration examples, runbook and architecture docs.
- No Docker required.

## Safety and cost
Default mode is **LOCAL**. It creates no AWS resources, sends no AWS requests and uses labelled synthetic data.
Do not enable AWS integration until billing alerts, IAM least privilege and budget are set. AWS prices vary by region and instance type; enter your verified price in `.env` instead of relying on fabricated savings. Remediation is disabled unless explicitly configured, and the app's local approval endpoint never executes cloud actions.

## 1. Run on Windows 11 / VS Code
Use Python 3.12. Open this project folder in VS Code.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Open **http://127.0.0.1:8010**. Keep the terminal open. API docs: http://127.0.0.1:8010/docs

Use port 8010 so a stuck process on port 8000 does not block the project. If port 8010 is occupied, change it to 8011 in the command and open that port.

## 2. Verify
In a second terminal (same project, activated `.venv`):
```powershell
python -m pytest -q
```
Health:
```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/health
```
Reset to baseline:
```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/api/reset
```

## 3. Dashboard features
- Interactive infrastructure map (select nodes, drag to rotate, orbit toggle)
- Health score and current synthetic CPU/memory/latency/request/error-rate metrics
- Observed metrics and next-30-minute forecast chart
- Traffic spike, database saturation, latency injection and error-rate spike scenarios
- Anomaly signals, rule-based diagnosis, structured runbook recommendations
- Cost review from explicitly configured hourly price + utilization; unknown price is shown as unknown
- Human approval history; local approvals are audit-only
- Dataset download and CSV upload endpoints
- Model status and evaluation-report endpoint (`/api/model/evaluation`)
- New feature endpoints: `POST /api/what-if`, `POST /api/slo`, `GET /api/copilot`, `POST /api/experiment`, `POST /api/recovery/verify`, and `GET /api/replay`

## 4. Train / evaluate models
The app can run without optional ML packages. Local JSON state is shared across visitors in this single-demo prototype; do not use it for sensitive data or multi-tenant workloads. In production, administrative mutation endpoints require the deployment token. The free Render blueprint is a demonstration deployment, not a hardened production service. For optional models:
```powershell
pip install -r requirements-ml.txt
python scripts/generate_training_data.py
python scripts/train_models.py
```
Training writes local artifacts under `artifacts/`. Do not commit trained private/large data unless you intend to.

`requirements-ml.txt` includes scikit-learn and Prophet. If Prophet install fails on your system, use the baseline and report it honestly. Model evaluation outputs precision/recall/F1 for the Isolation Forest and MAE/RMSE for the linear baseline on a synthetic held-out split; these are demo-data results, not production accuracy claims. Open `/api/model/evaluation` to view the report after training.

## 5. Optional AWS CloudWatch
1. Set billing alerts and budget first. Start with the AWS console and no resources if possible.
2. Configure `.env` with `CLOUD_MODE=aws`, `AWS_REGION`, and an existing `AWS_EC2_INSTANCE_ID`.
3. Use AWS CLI/SSO or an instance role. Do not paste credentials into source code or commit `.env`.
4. Grant only the read actions needed for CloudWatch metrics. Review `docs/AWS_SETUP.md`.
5. The app reads metrics only. It does not create EC2 instances.
6. Real EC2 hourly cost is shown only if you enter a verified `EC2_HOURLY_PRICE_USD` for your exact region/type. Otherwise it reports "price not configured".

Optional Lambda action:
- `ALLOW_LAMBDA_REMEDIATION=false` by default.
- Do not enable until you have reviewed IAM, CloudTrail and Lambda code.
- The approval endpoint only invokes Lambda when AWS mode, the explicit flag, and a strong `REMEDIATION_APPROVAL_TOKEN` are configured. The request must supply that token. In local mode it records a simulated approval. Never expose a live-remediation deployment publicly without additional access controls.
- Use a Lambda designed to perform one narrowly scoped, reversible action; never grant broad administrator permissions.

## 6. Project architecture
See `docs/ARCHITECTURE.md`, `docs/AWS_SETUP.md`, and `docs/DEMO_SCRIPT.md`.

## Honest scope
- Root cause: transparent rules, not causal ML.
- Recommendations: structured runbook lookup, not generative AI.
- Synthetic metrics are not AWS telemetry.
- Forecast baseline is a transparent linear trend. Prophet is optional and must be evaluated.
- Cost savings are never asserted without configured price and measured utilization.

## 7. Quality gates and model evaluation

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs Python compilation, API/security tests, model training/evaluation, JavaScript syntax checks, and a Chromium browser smoke test that requires the real Three.js WebGL scene to initialize. The browser job is intentionally strict: the CSS fallback is useful for accessibility but does **not** count as proof of WebGL success.

Run the same core checks locally:

```powershell
python -m compileall -q app scripts tests
python -m pytest -q
pip install -r requirements-ml.txt
python scripts/generate_training_data.py
python scripts/train_models.py
```

The evaluation report includes a chronological held-out split, confusion matrices, precision, recall and F1 for Isolation Forest and a supervised Random Forest classifier, a transparent threshold-rule baseline, and MAE/RMSE for persistence and linear-trend forecasting. On the current synthetic dataset, the supervised classifier scores F1 0.9606, threshold rules 0.8591 and Isolation Forest 0.5816. Because the labels are generated from distinctive synthetic patterns, these are reproducibility metrics—not evidence of real-world accuracy. Validate on independently labelled telemetry before making operational claims.

## 8. Public demo safety

The Render blueprint sets `APP_ENV=production`, keeps `CLOUD_MODE=local`, and generates an `ADMIN_API_TOKEN`. This token protects reset, CSV import, cost configuration, AWS sync and approval/audit mutations. The dashboard asks for the token only when an administrator operation is attempted and keeps it in `sessionStorage` for that browser tab. Retrieve the generated value from the Render environment settings; never put it in source control or screenshots. Public synthetic scenarios and what-if experiments do not call AWS.

Before switching to `CLOUD_MODE=aws`, set a strong `ADMIN_API_TOKEN`, configure AWS credentials through an instance role or secure environment, use least-privilege IAM, and verify billing guardrails. Keep `ALLOW_LAMBDA_REMEDIATION=false` until a dedicated demo Lambda, its IAM policy, audit trail, rollback and approval flow have been reviewed. Do not expose live cloud-changing actions to an unrestricted public demo.

**Deployment caveat:** Render's free service filesystem may be ephemeral, and the local JSON state is a single-demo store, not a multi-tenant database. Use managed persistent storage and per-user authorization before real multi-user use. The included Render blueprint is a deployment starter, not proof that the app is deployed.
