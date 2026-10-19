import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

CLOUD_MODE = os.getenv("CLOUD_MODE", "local").strip().lower()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1").strip()
AWS_EC2_INSTANCE_ID = os.getenv("AWS_EC2_INSTANCE_ID", "").strip()
EC2_HOURLY_PRICE_USD = os.getenv("EC2_HOURLY_PRICE_USD", "").strip()
LOW_CPU_THRESHOLD = float(os.getenv("LOW_CPU_THRESHOLD", "10"))
LOW_CPU_WINDOW_POINTS = max(3, int(os.getenv("LOW_CPU_WINDOW_POINTS", "12")))
ALLOW_LAMBDA_REMEDIATION = env_bool("ALLOW_LAMBDA_REMEDIATION", False)
REMEDIATION_LAMBDA_NAME = os.getenv("REMEDIATION_LAMBDA_NAME", "").strip()
REMEDIATION_APPROVAL_TOKEN = os.getenv("REMEDIATION_APPROVAL_TOKEN", "").strip()
