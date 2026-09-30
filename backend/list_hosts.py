import requests
from app.core.config import settings

url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/hosts"
headers = {"Authorization": f"Bearer {settings.FLEET_API_TOKEN}"}
res = requests.get(url, headers=headers).json()
for h in res.get("hosts", []):
    print(f"Host: {h['id']} - {h['hostname']} - {h['status']} - {h['os_version']}")
