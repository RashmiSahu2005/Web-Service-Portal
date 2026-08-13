import asyncio
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_identify_mocked():
    # Test identify host
    resp = client.post("/api/v1/hosts/identify", json={"ip_address": "192.168.8.175"})
    print("Identify Response:", resp.status_code, resp.json())
    
    # Test application catalog /install endpoint
    # Find an app first
    resp_app = client.get("/api/v1/applications")
    apps = resp_app.json()
    if not apps:
        print("No apps found")
        return
    app_id = apps[0]["id"]
    
    resp_job = client.post(f"/api/v1/install/{app_id}")
    job_id = resp_job.json()["installation_id"]
    print("Job created:", job_id)
    
    # Test starting job with host_id
    resp_start = client.post(f"/api/v1/install/{job_id}/start", json={"host_id": "191"})
    print("Start Job Response:", resp_start.status_code, resp_start.json())

if __name__ == "__main__":
    test_identify_mocked()
