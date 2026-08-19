import time
from fastapi.testclient import TestClient
from assetflow.api.app import create_app

def _wait(client, job_id, timeout=300.0):
    limite = time.time() + timeout
    while time.time() < limite:
        r = client.get(f"/api/generation/jobs/{job_id}").json()
        if r["status"] in ("succeeded", "failed", "cancelled"):
            return r
        time.sleep(0.2)
    return {"status": "TIMEOUT-DO-TESTE"}

def test_scratch(container):
    with TestClient(create_app(container=container)) as client:
        for n in (64, 128, 256):
            t0 = time.perf_counter()
            r = client.post("/api/generation/jobs", json={
                "project_id": "p1", "profile": "pixel_character_64",
                "prompt": "cavaleiro",
                "output": {"logical_width": n, "logical_height": n, "variations": 1},
            })
            print(f"\nPOST {n} -> {r.status_code}", flush=True)
            assert r.status_code == 202, r.text
            job = _wait(client, r.json()["job_id"])
            dt = time.perf_counter() - t0
            v = (job.get("asset") or {}).get("variants", [{}])[0] if job.get("asset") else {}
            print(f"HTTP {n}x{n}: {dt:.2f}s status={job['status']} logical={v.get('logical_width')}x{v.get('logical_height')}", flush=True)
