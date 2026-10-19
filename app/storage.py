from __future__ import annotations
import csv, io, json, threading
from pathlib import Path
from typing import Any
from .engine import utc_now

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_PATH = DATA_DIR / "state.json"
LOCK = threading.Lock()

def initial_metrics():
    cpu=[32,35,38,36,42,45,43,49,52,55,58,57]
    mem=[48,49,51,50,53,55,54,58,60,62,64,63]
    lat=[118,122,129,124,142,151,147,166,179,188,205,198]
    req=[220,240,260,252,290,315,306,348,372,398,425,416]
    return [{"timestamp":f"2026-10-18T09:{i*5:02d}:00Z","cpu":cpu[i],"memory":mem[i],"latency_ms":lat[i],"requests_per_min":req[i],"error_rate":0.3+(i%4)*0.1,"db_connections":35+i*2,"source":"synthetic"} for i in range(12)]

def fresh_state():
    return {"metrics":initial_metrics(),"incidents":[],"history":[],"approvals":[],"scenario":"baseline","created_at":utc_now()}

def load_state():
    with LOCK:
        if not STATE_PATH.exists(): return fresh_state()
        try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (ValueError,OSError): return fresh_state()

def save_state(state):
    with LOCK:
        STATE_PATH.write_text(json.dumps(state,indent=2),encoding="utf-8")

def csv_bytes(metrics):
    buf=io.StringIO()
    fields=["timestamp","cpu","memory","latency_ms","requests_per_min","error_rate","db_connections","source"]
    w=csv.DictWriter(buf,fieldnames=fields);w.writeheader();w.writerows(metrics)
    return buf.getvalue().encode("utf-8")
