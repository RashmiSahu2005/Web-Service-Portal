import asyncio
from app.services.fleetdm_service import FleetDMService

async def main():
    fleet = FleetDMService()
    hosts = await fleet.list_hosts()
    for host in hosts:
        if host.get('primary_ip') == '192.168.13.106':
            print(f"Found host: ID={host.get('id')}, hostname={host.get('hostname')}, IP={host.get('primary_ip')}, OS={host.get('os_version')}")

if __name__ == "__main__":
    asyncio.run(main())
