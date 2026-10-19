from fastapi.testclient import TestClient
from app.main import app
from app import storage
client=TestClient(app)

def setup_function():
    storage.save_state(storage.fresh_state())

def test_dashboard_served():
    r=client.get("/")
    assert r.status_code==200
    assert "PredictOps" in r.text and "Interactive service topology" in r.text

def test_health_and_overview():
    assert client.get("/api/health").json()["status"]=="healthy"
    data=client.get("/api/overview").json()
    assert 0<=data["health_score"]<=100
    assert data["source"]=="synthetic"

def test_forecast_has_six_points():
    r=client.get("/api/forecast")
    assert r.status_code==200 and len(r.json()["points"])==6

def test_scenario_updates_metrics_and_incidents():
    before=client.get("/api/metrics").json()["count"]
    r=client.post("/api/simulate",json={"scenario":"traffic_spike"})
    assert r.status_code==200 and r.json()["incident"]["source"]=="synthetic"
    assert client.get("/api/metrics").json()["count"]==before+1
    assert len(client.get("/api/incidents").json()["items"])>=1

def test_reset():
    client.post("/api/simulate",json={"scenario":"error_spike"})
    assert client.post("/api/reset").status_code==200
    assert client.get("/api/metrics").json()["count"]==12

def test_approval_is_local_only():
    r=client.post("/api/remediation/approve",json={"recommendation_id":"COST-REVIEW","execute_lambda":False})
    assert r.status_code==200 and "No cloud resource was changed" in r.json()["message"]
    assert len(client.get("/api/history").json()["approvals"])==1

def test_cost_does_not_invent_price():
    r=client.get("/api/cost").json()
    assert r["price_configured"] is False
    assert r["estimated_monthly_cost_usd"] is None

def test_dataset_download():
    r=client.get("/api/dataset.csv")
    assert r.status_code==200 and "latency_ms" in r.text

def test_model_evaluation_endpoint_is_explicit_when_untrained():
    r=client.get('/api/model/evaluation')
    assert r.status_code==200
    assert 'available' in r.json()

def test_csv_rejects_out_of_range_metrics():
    csv=b'cpu,memory,latency_ms,requests_per_min,error_rate,db_connections\n200,20,10,10,0,10\n'
    r=client.post('/api/metrics/import',files={'file':('bad.csv',csv,'text/csv')})
    assert r.status_code==400
    assert 'cpu must be between 0 and 100' in r.text

def test_csv_rejects_non_finite_metrics():
    csv=b'cpu,memory,latency_ms,requests_per_min,error_rate,db_connections\nNaN,20,10,10,0,10\n'
    r=client.post('/api/metrics/import',files={'file':('bad.csv',csv,'text/csv')})
    assert r.status_code==400
    assert 'non-finite' in r.text

def test_csv_rejects_negative_latency():
    csv=b'cpu,memory,latency_ms,requests_per_min,error_rate,db_connections\n20,20,-1,10,0,10\n'
    r=client.post('/api/metrics/import',files={'file':('bad.csv',csv,'text/csv')})
    assert r.status_code==400
    assert 'latency_ms cannot be negative' in r.text

def test_what_if_capacity_simulation_is_explicitly_modeled():
    r=client.post('/api/what-if',json={'traffic_multiplier':3,'additional_instances':2,'hourly_price_usd':0.05})
    assert r.status_code==200
    d=r.json()
    assert d['source']=='illustrative-model'
    assert d['scenario']['monthly_incremental_cost_usd']==72.0
    assert 'No infrastructure was changed' in d['warning']

def test_what_if_rejects_out_of_range_inputs():
    assert client.post('/api/what-if',json={'traffic_multiplier':99,'additional_instances':1}).status_code==422

def test_slo_evaluation_discloses_proxy_limitations():
    r=client.post('/api/slo',json={'latency_target_ms':100,'error_target_percent':0.5})
    assert r.status_code==200
    assert 'not a true availability SLI' in r.json()['caveat']

def test_copilot_uses_evidence_and_rules():
    d=client.get('/api/copilot').json()
    assert d['type']=='evidence-grounded-rule-copilot'
    assert 'No generative model was used' in d['guardrail']

def test_experiment_compares_two_candidates():
    r=client.post('/api/experiment',json={'action_a':'scale_out','action_b':'cache','traffic_multiplier':2})
    assert r.status_code==200
    assert r.json()['candidate_a']['action']=='scale_out'
    assert r.json()['preferred_candidate'] in ('scale_out','cache')

def test_recovery_verification_records_event():
    r=client.post('/api/recovery/verify',json={'before_cpu':90,'after_cpu':50,'before_latency_ms':300,'after_latency_ms':120,'before_error_rate':4,'after_error_rate':0.5})
    assert r.status_code==200 and r.json()['status']=='recovered'
    assert any(x['event']=='Recovery verification' for x in client.get('/api/history').json()['items'])

def test_replay_returns_recorded_events():
    client.post('/api/simulate',json={'scenario':'error_spike'})
    d=client.get('/api/replay').json()
    assert d['count']>=1 and d['items'][0]['kind'] in ('incident','operation')

def test_live_lambda_locked_without_server_token(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'CLOUD_MODE', 'aws')
    monkeypatch.setattr(config, 'ALLOW_LAMBDA_REMEDIATION', True)
    monkeypatch.setattr(config, 'REMEDIATION_LAMBDA_NAME', 'predictops-demo')
    monkeypatch.setattr(config, 'REMEDIATION_APPROVAL_TOKEN', '')
    monkeypatch.setattr(config, 'ADMIN_API_TOKEN', 'admin-test-token')
    r=client.post('/api/remediation/approve',json={'recommendation_id':'COST-REVIEW','execute_lambda':True},headers={'Authorization':'Bearer admin-test-token'})
    assert r.status_code==503
    assert 'locked' in r.text.lower()

def test_live_lambda_rejects_wrong_approval_token(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'CLOUD_MODE', 'aws')
    monkeypatch.setattr(config, 'ALLOW_LAMBDA_REMEDIATION', True)
    monkeypatch.setattr(config, 'REMEDIATION_LAMBDA_NAME', 'predictops-demo')
    monkeypatch.setattr(config, 'REMEDIATION_APPROVAL_TOKEN', 'correct-long-test-token')
    monkeypatch.setattr(config, 'ADMIN_API_TOKEN', 'admin-test-token')
    r=client.post('/api/remediation/approve',json={'recommendation_id':'COST-REVIEW','execute_lambda':True,'approval_token':'wrong-token'},headers={'Authorization':'Bearer admin-test-token'})
    assert r.status_code==403

def test_live_lambda_still_disabled_by_default_flag(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'CLOUD_MODE', 'aws')
    monkeypatch.setattr(config, 'ALLOW_LAMBDA_REMEDIATION', False)
    monkeypatch.setattr(config, 'REMEDIATION_LAMBDA_NAME', 'predictops-demo')
    monkeypatch.setattr(config, 'REMEDIATION_APPROVAL_TOKEN', 'correct-long-test-token')
    monkeypatch.setattr(config, 'ADMIN_API_TOKEN', 'admin-test-token')
    r=client.post('/api/remediation/approve',json={'recommendation_id':'COST-REVIEW','execute_lambda':True,'approval_token':'correct-long-test-token'},headers={'Authorization':'Bearer admin-test-token'})
    assert r.status_code==400
    assert 'disabled' in r.text.lower()


def test_anomalies_response_has_classifier_field():
    r=client.get('/api/anomalies')
    assert r.status_code==200
    assert 'supervised_classifier' in r.json()
