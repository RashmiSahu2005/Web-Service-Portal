import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()
FLEET_URL = os.getenv("FLEET_BASE_URL", "https://mdm.apmosys.com")
FLEET_TOKEN = os.getenv("FLEET_API_TOKEN")

headers = {"Authorization": f"Bearer {FLEET_TOKEN}"}
resp = requests.get(f"{FLEET_URL}/api/v1/fleet/hosts", headers=headers)
if resp.status_code == 200:
    hosts = resp.json().get("hosts", [])
    print(f"Found {len(hosts)} hosts.")
    for h in hosts[:5]:
        print(f"ID: {h.get('id')}, Hostname: {h.get('hostname')}, IP: {h.get('primary_ip')}, Platform: {h.get('platform')}")
else:
    print(f"Failed: {resp.status_code}")
