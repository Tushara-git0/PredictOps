from __future__ import annotations
from typing import Any
from . import config

def cloudwatch_cpu(instance_id: str, region: str) -> list[dict[str, Any]]:
    """Read CPU from CloudWatch only. Requires boto3 and AWS credentials via standard AWS chain."""
    try:
        import boto3
        from datetime import datetime, timedelta, timezone
    except ImportError as e:
        raise RuntimeError("AWS mode requires optional dependency boto3. Install requirements-aws.txt.") from e
    if not instance_id:
        raise ValueError("Set AWS_EC2_INSTANCE_ID in .env before selecting AWS mode.")
    client=boto3.client("cloudwatch",region_name=region)
    end=datetime.now(timezone.utc); start=end-timedelta(hours=2)
    response=client.get_metric_statistics(Namespace="AWS/EC2",MetricName="CPUUtilization",Dimensions=[{"Name":"InstanceId","Value":instance_id}],StartTime=start,EndTime=end,Period=300,Statistics=["Average"])
    points=sorted(response.get("Datapoints",[]),key=lambda p:p["Timestamp"])
    return [{"timestamp":p["Timestamp"].isoformat(),"cpu":round(float(p["Average"]),2),"memory":0,"latency_ms":0,"requests_per_min":0,"error_rate":0,"db_connections":0,"source":"aws-cloudwatch"} for p in points]

def invoke_approved_lambda(payload: dict[str, Any]) -> dict[str, Any]:
    if not config.ALLOW_LAMBDA_REMEDIATION:
        raise PermissionError("Lambda remediation is disabled. Set ALLOW_LAMBDA_REMEDIATION=true only after reviewing IAM and runbook.")
    if not config.REMEDIATION_LAMBDA_NAME:
        raise ValueError("Set REMEDIATION_LAMBDA_NAME before enabling Lambda remediation.")
    try:
        import boto3
    except ImportError as e:
        raise RuntimeError("AWS remediation requires boto3. Install requirements-aws.txt.") from e
    client=boto3.client("lambda",region_name=config.AWS_REGION)
    response=client.invoke(FunctionName=config.REMEDIATION_LAMBDA_NAME,InvocationType="RequestResponse",Payload=__import__("json").dumps(payload).encode())
    body=response["Payload"].read().decode("utf-8","replace")
    return {"status_code":response.get("StatusCode"),"function_error":response.get("FunctionError"),"payload":body}
