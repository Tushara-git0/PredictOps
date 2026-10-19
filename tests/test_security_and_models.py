from fastapi.testclient import TestClient
from app.main import app
from app import config, storage

client = TestClient(app)

def setup_function():
    storage.save_state(storage.fresh_state())
    config.APP_ENV = "development"
    config.ADMIN_API_TOKEN = ""
    config.CLOUD_MODE = "local"

def test_security_headers_are_present():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]

def test_production_admin_operations_fail_closed_without_token():
    config.APP_ENV = "production"
    r = client.post("/api/reset")
    assert r.status_code == 503
    assert "ADMIN_API_TOKEN" in r.text

def test_production_admin_operations_reject_missing_or_wrong_token():
    config.APP_ENV = "production"
    config.ADMIN_API_TOKEN = "a-long-random-test-token"
    assert client.post("/api/reset").status_code == 403
    assert client.post("/api/reset", headers={"Authorization": "Bearer wrong"}).status_code == 403

def test_production_admin_operation_accepts_correct_token():
    config.APP_ENV = "production"
    config.ADMIN_API_TOKEN = "a-long-random-test-token"
    r = client.post("/api/reset", headers={"Authorization": "Bearer a-long-random-test-token"})
    assert r.status_code == 200

def test_cloudwatch_sync_requires_admin_token_in_aws_mode():
    config.CLOUD_MODE = "aws"
    config.ADMIN_API_TOKEN = "cloud-test-token"
    assert client.post("/api/aws/sync").status_code == 403
    # This validates authorization only; no AWS API is called.
    assert client.post("/api/aws/sync", headers={"Authorization": "Bearer cloud-test-token"}).status_code in (400, 404)

def test_model_evaluation_endpoint_is_json_and_truthful():
    r = client.get("/api/model/evaluation")
    assert r.status_code == 200
    data = r.json()
    assert "available" in data
    if data["available"] and "threshold_rule_baseline" in data["report"]:
        assert "SYNTHETIC" in data["report"]["provenance"]
        assert data["report"]["threshold_rule_baseline"]["f1"] >= 0
        assert "supervised_incident_classifier" in data["report"]
