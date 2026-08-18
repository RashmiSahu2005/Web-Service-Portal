import requests, os
from dotenv import load_dotenv
load_dotenv()
resp = requests.get(
    f"{os.getenv('FLEET_BASE_URL')}/api/v1/fleet/hosts",
    headers={"Authorization": f"Bearer {os.getenv('FLEET_API_TOKEN')}"}
)
hosts = resp.json().get('hosts', [])
found = [h for h in hosts if h.get('primary_ip') == '192.168.8.175']
print(found)
