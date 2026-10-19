# Architecture and design decisions

## Data path
Synthetic generator / optional CSV import / optional CloudWatch read-only sync
→ metric state store (`data/state.json`)
→ forecast engine + anomaly rules / optional Isolation Forest
→ transparent root-cause correlation
→ runbook recommendations + cost review
→ human approval + audit history.

## Components
- FastAPI: API and same-origin dashboard server.
- `engine.py`: health-score formula, linear forecast, diagnosis and cost calculation.
- `storage.py`: local JSON state and CSV export. State is a simple single-process prototype store, not a production database; public deployments share this state and may lose it on restart/redeploy depending on the host filesystem.
- `aws.py`: optional read-only CloudWatch CPU and gated Lambda invoke.
- `scripts/`: synthetic training data and model evaluation.
- `dashboard.html`: responsive frontend with interactive 3D-style topology, charts, scenario controls and audit history.

## Safety boundaries
Default `CLOUD_MODE=local`. No AWS SDK is required. No cloud resource creation. AWS integration only reads existing EC2 CPU metrics; memory requires CloudWatch Agent configuration and is not faked as live. Lambda execution requires both AWS mode and explicit opt-in, and should be configured to one narrowly scoped function.
