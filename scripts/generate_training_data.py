"""Generate a deterministic, explicitly synthetic metric dataset for reproducible model demos."""
from pathlib import Path
import csv, random
from datetime import datetime, timedelta, timezone

SEED = 7
ROWS = 3000
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "training_metrics.csv"
random.seed(SEED)
OUT.parent.mkdir(exist_ok=True)
fields = ["timestamp", "cpu", "memory", "latency_ms", "error_rate", "requests_per_min", "db_connections", "label"]
start = datetime(2026, 1, 1, tzinfo=timezone.utc)
with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for i in range(ROWS):
        # A slow load trend + periodic demand variation makes the baseline less trivial.
        phase = (i % 288) / 288
        demand = 1 + 0.22 * __import__("math").sin(phase * 2 * __import__("math").pi)
        req = max(30, random.gauss(250 * demand, 55))
        cpu = max(5, min(98, req / 5 + random.gauss(0, 7)))
        mem = max(25, min(95, 43 + cpu * .27 + random.gauss(0, 5)))
        latency = max(35, 75 + cpu * 1.15 + random.gauss(0, 18))
        error = max(0, random.gauss(.35, .22))
        db = max(8, min(100, req / 8 + random.gauss(0, 8)))
        label = 0
        if random.random() < .08:
            label = 1
            kind = random.choice(["cpu", "db", "latency", "errors"])
            if kind == "cpu":
                cpu, req = random.uniform(82, 99), random.uniform(450, 900)
            elif kind == "db":
                db, latency, error = random.uniform(85, 100), random.uniform(250, 700), random.uniform(3, 15)
            elif kind == "latency":
                latency = random.uniform(280, 800)
            else:
                error = random.uniform(4, 20)
        writer.writerow({
            "timestamp": (start + timedelta(minutes=5*i)).isoformat().replace("+00:00", "Z"),
            "cpu": round(cpu, 2), "memory": round(mem, 2), "latency_ms": round(latency, 2),
            "error_rate": round(error, 3), "requests_per_min": round(req, 2),
            "db_connections": round(db, 2), "label": label,
        })
print(f"Wrote {ROWS} SYNTHETIC rows to {OUT} (seed={SEED}). Do not report as production telemetry.")
