# PredictOps Feature Upgrade

This upgrade adds six research/demo workflows to the existing FastAPI app and dashboard.

## Added workflows

1. **Capacity what-if simulator** (`POST /api/what-if`): estimates the effect of traffic multipliers and additional instances. Any cost uses only an hourly price supplied by the user. It is a simplified model, not a benchmark or a live scaling action.
2. **SLO tracker** (`POST /api/slo`): compares the latest latency and error-rate sample against user-entered targets. Its error-budget value is an educational proxy; true availability SLOs require request counts and a measurement window.
3. **Explainable incident copilot** (`GET /api/copilot`): returns current metric evidence, rule-based hypotheses and suggested next steps. It does not use a generative model and explicitly labels its confidence as uncalibrated.
4. **A/B remediation experiment** (`POST /api/experiment`): compares deterministic illustrative models for scale-out, caching and reduced concurrency. Validate with repeatable load tests before making engineering decisions.
5. **Recovery verification** (`POST /api/recovery/verify`): compares operator-supplied before/after CPU, latency and error-rate values; stores the verification in local history.
6. **Incident replay** (`GET /api/replay`): combines the recorded demo incident and operation history into a timeline. It is not distributed tracing.

## Verification performed for this upgrade

- `python -m pytest -q`: 19 tests passed.
- `python -m py_compile app/*.py scripts/*.py`: passed.
- Dashboard inline JavaScript syntax check with Node.js: passed for both scripts.
- FastAPI TestClient smoke checks for dashboard and all six new endpoints: HTTP 200.
- ZIP integrity check: run when packaging.

## Limitations and responsible claims

The new simulation outputs are not live AWS measurements and do not prove production behavior. The SLO tracker is not a true availability calculation. Root-cause hypotheses are rule-based. A/B candidates use simplified assumptions. Recovery checks rely on values supplied by the operator. Live AWS integration and real browser WebGL rendering must be tested separately before claiming they are verified.

For a final-year submission, document these assumptions and evaluate the system on repeatable synthetic workloads plus any real metrics you can safely collect.
