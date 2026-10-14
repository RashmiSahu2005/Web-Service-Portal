import requests
import sys
import time

BASE_URL = "http://localhost:8000"
APP_ID = "docker"
TARGET_IP = "192.168.10.53"

print(f"Triggering installation of {APP_ID} on {TARGET_IP}...")

# 1. Create the job
res = requests.post(f"{BASE_URL}/install/{APP_ID}?host={TARGET_IP}")
if res.status_code != 200:
    print(f"Failed to create job: {res.text}")
    sys.exit(1)

job_id = res.json().get("installation_id")
print(f"Created job: {job_id}")

# 2. Start the job
start_res = requests.post(f"{BASE_URL}/install/{job_id}/start", json={"host_id": TARGET_IP})
if start_res.status_code != 200:
    print(f"Failed to start job: {start_res.text}")
    sys.exit(1)

print(f"Job started successfully: {start_res.json()}")

# 3. Monitor the job
print("Monitoring job status...")
while True:
    status_res = requests.get(f"{BASE_URL}/install/{job_id}")
    if status_res.status_code != 200:
        print(f"Failed to get status: {status_res.text}")
        sys.exit(1)
        
    data = status_res.json()
    status = data.get("status")
    print(f"Status: {status} | Step: {data.get('step')} | Logs: {len(data.get('logs', []))} lines")
    
    if status in ["COMPLETED", "FAILED", "CANCELLED"]:
        print(f"\nFinal Status: {status}")
        print("\nLast few logs:")
        for log in data.get("logs", [])[-15:]:
            print(log)
        break
        
    time.sleep(5)
