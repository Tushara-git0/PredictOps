"""Real Chromium end-to-end smoke test. Requires `pip install playwright` and `playwright install chromium`."""
from __future__ import annotations
import os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PREDICTOPS_TEST_PORT", "18765"))
BASE = f"http://127.0.0.1:{PORT}"
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/api/health", timeout=1)
            break
        except Exception:
            if server.poll() is not None:
                raise RuntimeError("Uvicorn exited before health endpoint became ready")
            time.sleep(.2)
    else:
        raise RuntimeError("Timed out waiting for PredictOps API")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-webgl", "--ignore-gpu-blocklist", "--use-gl=angle", "--use-angle=swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors, failed_requests = [], []
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed_requests.append({"url": req.url, "error": req.failure}))
        response = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
        assert response and response.status == 200, "Dashboard did not return HTTP 200"
        page.wait_for_function("document.querySelector('#connection')?.textContent.includes('connected')", timeout=30000)
        # Actual WebGL is a release criterion; fallback topology alone is not sufficient.
        page.wait_for_function("document.querySelector('#topology')?.classList.contains('webgl-ready')", timeout=30000)
        assert page.locator("#threeCanvas").count() == 1
        assert page.evaluate("(() => { const c=document.querySelector('#threeCanvas'); const gl=c && (c.getContext('webgl2') || c.getContext('webgl')); return !!gl; })()"), "WebGL context unavailable"
        # Verify key workflows against the live API, not mocked browser data.
        page.locator('[data-scenario="db_saturation"]').click()
        page.locator("#simulate").click()
        page.wait_for_function("document.querySelector('#notice')?.textContent.includes('Scenario applied')", timeout=10000)
        page.locator("#runWhatIf").click()
        page.wait_for_function("document.querySelector('#whatResult')?.textContent.includes('Capacity risk')", timeout=10000)
        page.locator("#runSlo").click()
        page.wait_for_function("document.querySelector('#sloResult')?.textContent.includes('Latency:')", timeout=10000)
        page.locator("#runCopilot").click()
        page.wait_for_function("document.querySelector('#copilotResult')?.textContent.includes('Health score')", timeout=10000)
        page.locator("#runExperiment").click()
        page.wait_for_function("document.querySelector('#experimentResult')?.textContent.includes('Preferred simulated candidate')", timeout=10000)
        page.locator("#verifyRecovery").click()
        page.wait_for_function("document.querySelector('#recoveryResult')?.textContent.includes('Recovery status')", timeout=10000)
        page.locator("#loadReplay").click()
        page.wait_for_function("document.querySelector('#replayResult')?.textContent.length > 20", timeout=10000)
        assert not page_errors, f"Browser JavaScript errors: {page_errors}"
        print("PASS: live Chromium UI, real WebGL renderer, scenario simulation, capacity planning, SLO, copilot, A/B experiment, recovery verification and replay")
        print(f"Non-fatal failed requests: {failed_requests[:5]}")
        browser.close()
finally:
    server.terminate()
    try: server.wait(timeout=5)
    except subprocess.TimeoutExpired: server.kill()
