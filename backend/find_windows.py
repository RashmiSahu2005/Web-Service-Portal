import requests, os
from dotenv import load_dotenv
load_dotenv()
resp = requests.get(
    f"{os.getenv('FLEET_BASE_URL')}/api/v1/fleet/hosts",
    headers={"Authorization": f"Bearer {os.getenv('FLEET_API_TOKEN')}"}
)
hosts = resp.json().get('hosts', [])
windows_hosts = [h for h in hosts if h.get('platform') == 'windows']
print(f"Found {len(windows_hosts)} Windows hosts.")
for h in windows_hosts[:5]:
    print(f"ID: {h.get('id')}, Hostname: {h.get('hostname')}, IP: {h.get('primary_ip')}")
